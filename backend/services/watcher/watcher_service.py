"""
Watcher service - polls GitLab for assigned MRs.
Runs as a single POD.
"""
import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import redis.asyncio as aioredis

from backend.config.config import config_manager
from backend.database.connection import db
from backend.secrets.secrets_manager import SecretsManager
from backend.gitlab_integration.gitlab_unified import GitLabUnified

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WatcherService:
    """
    Watches GitLab for MRs assigned to Merge Assist.
    Polls all active projects on a schedule.
    """
    
    def __init__(self):
        """Initialize watcher service."""
        self.config = config_manager.settings
        self.secrets = SecretsManager()
        self.db = db
        self.scheduler = AsyncIOScheduler()
        self.redis_client: aioredis.Redis = None
        self.merge_assist_user_id: int = None
    
    async def initialize(self):
        """Initialize connections."""
        logger.info("Initializing Watcher Service")
        
        # Initialize database
        self.db.initialize(self.config.database_url)
        
        # Initialize Redis
        self.redis_client = await aioredis.from_url(self.config.redis_url)
        
        # Get Merge Assist user ID
        self.merge_assist_user_id = int(self.secrets.get_secret('gitlab/merge_assist_user_id'))
        
        logger.info("Watcher Service initialized")
    
    async def poll_projects(self):
        """Poll all active projects for MRs."""
        try:
            logger.info("Polling projects for MRs")
            
            with self.db.get_session() as session:
                from backend.database.models import Project
                
                # Get all active projects
                projects = session.query(Project).filter(Project.is_active == True).all()
                
                for project in projects:
                    await self.poll_project(project, session)
        
        except Exception as e:
            logger.error(f"Error polling projects: {e}")
    
    async def poll_project(self, project, session):
        """
        Poll a specific project for MRs.
        
        Args:
            project: Project model instance
            session: Database session
        """
        try:
            logger.info(f"Polling project {project.name} (GitLab ID: {project.gitlab_id})")
            
            # Get GitLab token for this project
            gitlab_token = self.secrets.get_gitlab_token(str(project.gitlab_id))
            
            # Initialize GitLab client
            gitlab = GitLabUnified(self.config.gitlab_url, gitlab_token)
            
            # Get MRs assigned to Merge Assist
            mrs = await gitlab.get_merge_requests(
                project.gitlab_id,
                state="opened",
                assignee_id=self.merge_assist_user_id
            )
            
            logger.info(f"Found {len(mrs)} MRs assigned to Merge Assist")
            
            # Process each MR
            for mr_data in mrs:
                await self.process_mr(project, mr_data, session)
            
            await gitlab.close()
        
        except Exception as e:
            logger.error(f"Error polling project {project.name}: {e}")
    
    async def process_mr(self, project, mr_data: dict, session):
        """
        Process an MR found by polling.
        
        Args:
            project: Project model instance
            mr_data: MR data from GitLab
            session: Database session
        """
        try:
            from backend.database.models import MergeRequest
            from datetime import datetime
            
            mr_iid = mr_data['iid']
            
            # Check if MR exists in database
            db_mr = session.query(MergeRequest).filter(
                MergeRequest.project_id == str(project.id),
                MergeRequest.gitlab_mr_iid == mr_iid
            ).first()
            
            if not db_mr:
                # New MR - create record
                logger.info(f"New MR discovered: !{mr_iid}")
                db_mr = MergeRequest(
                    project_id=str(project.id),
                    gitlab_mr_iid=mr_iid,
                    title=mr_data['title'],
                    source_branch=mr_data['source_branch'],
                    target_branch=mr_data['target_branch'],
                    status='recognized',
                    recognized_at=datetime.utcnow()
                )
                session.add(db_mr)
                session.commit()
                
                # Publish event to Redis for worker POD
                await self.redis_client.publish(
                    f'project:{project.id}',
                    str(mr_iid)
                )
            else:
                # Existing MR - update if needed
                db_mr.title = mr_data['title']
                db_mr.source_branch = mr_data['source_branch']
                db_mr.target_branch = mr_data['target_branch']
                session.commit()
        
        except Exception as e:
            logger.error(f"Error processing MR !{mr_data.get('iid')}: {e}")
    
    def start(self):
        """Start the watcher service."""
        logger.info("Starting Watcher Service")
        
        # Schedule polling job
        polling_interval = self.config.watcher_polling_interval
        self.scheduler.add_job(
            self.poll_projects,
            'interval',
            seconds=polling_interval,
            id='poll_projects'
        )
        
        # Start scheduler
        self.scheduler.start()
        
        logger.info(f"Watcher scheduled to poll every {polling_interval} seconds")
    
    async def run(self):
        """Run the watcher service."""
        await self.initialize()
        self.start()
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            self.scheduler.shutdown()
            await self.redis_client.close()


async def main():
    """Main entry point."""
    watcher = WatcherService()
    await watcher.run()


if __name__ == "__main__":
    asyncio.run(main())
