"""
Worker POD main service - orchestrates MR processing.
One instance per project.
"""
import logging
import asyncio
import redis.asyncio as aioredis
from typing import Optional

from backend.config.config import config_manager
from backend.database.connection import db
from backend.secrets.secrets_manager import SecretsManager
from backend.gitlab_integration.gitlab_unified import GitLabUnified
from .validators import MRValidator
from .label_manager import LabelManager
from .comment_manager import CommentManager
from .merger import Merger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkerPOD:
    """
    Worker POD for a specific GitLab project.
    Processes MRs and handles merge operations.
    """
    
    def __init__(self, project_id: str):
        """
        Initialize Worker POD for a project.
        
        Args:
            project_id: UUID of project from database
        """
        self.project_id = project_id
        self.gitlab_project_id: Optional[int] = None
        self.running = False
        
        # Initialize components
        self.config = config_manager.settings
        self.secrets = SecretsManager()
        self.db = db
        self.redis_client: Optional[aioredis.Redis] = None
        self.gitlab: Optional[GitLabUnified] = None
        
        # Worker components
        self.validator: Optional[MRValidator] = None
        self.label_manager: Optional[LabelManager] = None
        self.comment_manager: Optional[CommentManager] = None
        self.merger: Optional[Merger] = None
    
    async def initialize(self):
        """Initialize all connections and components."""
        logger.info(f"Initializing Worker POD for project {self.project_id}")
        
        # Initialize database
        self.db.initialize(self.config.database_url)
        
        # Load project from database
        from backend.database.models import Project
        with self.db.get_session() as session:
            project = session.query(Project).filter(Project.id == self.project_id).first()
            if not project:
                raise ValueError(f"Project {self.project_id} not found")
            
            self.gitlab_project_id = project.gitlab_id
            
            # Load project config
            project_config = config_manager.load_project_config(self.project_id, session)
        
        # Get GitLab token from secrets
        gitlab_token = self.secrets.get_gitlab_token(str(self.gitlab_project_id))
        
        # Initialize GitLab client
        self.gitlab = GitLabUnified(self.config.gitlab_url, gitlab_token)
        
        # Initialize Redis
        self.redis_client = await aioredis.from_url(self.config.redis_url)
        
        # Initialize worker components
        merge_assist_user_id = int(self.secrets.get_secret('gitlab/merge_assist_user_id'))
        
        self.validator = MRValidator(self.gitlab, merge_assist_user_id)
        self.label_manager = LabelManager(self.gitlab, project_config)
        self.comment_manager = CommentManager(self.gitlab)
        self.merger = Merger(
            self.gitlab,
            self.validator,
            self.label_manager,
            self.comment_manager,
            project_config
        )
        
        logger.info(f"Worker POD initialized for GitLab project {self.gitlab_project_id}")
    
    async def start(self):
        """Start the worker POD."""
        self.running = True
        logger.info(f"Starting Worker POD for project {self.project_id}")
        
        # Subscribe to Redis channel for this project
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(f'project:{self.project_id}')
        
        # Main event loop
        while self.running:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message and message['type'] == 'message':
                    mr_id = message['data'].decode('utf-8')
                    logger.info(f"Received event for MR {mr_id}")
                    await self.process_mr(int(mr_id))
                
                # Also periodically check for ready MRs
                await self.check_ready_mrs()
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                await asyncio.sleep(5)
    
    async def process_mr(self, mr_iid: int):
        """
        Process a single MR.
        
        Args:
            mr_iid: GitLab MR internal ID
        """
        try:
            logger.info(f"Processing MR !{mr_iid}")
            
            # Fetch MR from GitLab
            mr_data = await self.gitlab.get_merge_request(self.gitlab_project_id, mr_iid)
            
            # Validate MR
            is_ready, reasons = await self.validator.is_ready_to_merge(mr_data)
            
            with self.db.get_session() as session:
                from backend.database.models import MergeRequest
                
                # Get or create MR in database
                db_mr = session.query(MergeRequest).filter(
                    MergeRequest.gitlab_mr_iid == mr_iid,
                    MergeRequest.project_id == self.project_id
                ).first()
                
                if not db_mr:
                    # Create new MR record
                    db_mr = MergeRequest(
                        project_id=self.project_id,
                        gitlab_mr_iid=mr_iid,
                        title=mr_data['title'],
                        source_branch=mr_data['source_branch'],
                        target_branch=mr_data['target_branch'],
                        status='recognized'
                    )
                    session.add(db_mr)
                    session.commit()
                
                if is_ready:
                    # MR is ready to merge
                    logger.info(f"MR !{mr_iid} is ready to merge")
                    db_mr.status = 'ready'
                    db_mr.rejection_count = 0
                    session.commit()
                    
                    await self.label_manager.add_ready_to_merge_label(self.gitlab_project_id, mr_iid)
                else:
                    # MR is not ready
                    logger.info(f"MR !{mr_iid} is not ready: {reasons}")
                    db_mr.rejection_count += 1
                    db_mr.status = 'not_ready'
                    session.commit()
                    
                    await self.label_manager.add_not_ready_label(self.gitlab_project_id, mr_iid)
                    await self.comment_manager.add_not_ready_comment(
                        self.gitlab_project_id,
                        mr_iid,
                        reasons,
                        db_mr.rejection_count
                    )
                    
                    # Check if should reject (3 strikes)
                    if db_mr.rejection_count >= 3:
                        logger.info(f"Rejecting MR !{mr_iid} after 3 attempts")
                        db_mr.status = 'rejected'
                        session.commit()
                        
                        await self.label_manager.add_rejected_label(self.gitlab_project_id, mr_iid)
                        await self.comment_manager.add_rejected_comment(
                            self.gitlab_project_id,
                            mr_iid,
                            reasons
                        )
        
        except Exception as e:
            logger.error(f"Error processing MR !{mr_iid}: {e}")
    
    async def check_ready_mrs(self):
        """Check for MRs that are ready to merge and initiate merge."""
        try:
            with self.db.get_session() as session:
                from backend.database.models import MergeRequest, ProjectConfig
                
                # Get project config
                project_config = session.query(ProjectConfig).filter(
                    ProjectConfig.project_id == self.project_id
                ).first()
                
                if not project_config:
                    return
                
                batch_size = project_config.batch_size
                
                # Get ready MRs
                ready_mrs = session.query(MergeRequest).filter(
                    MergeRequest.project_id == self.project_id,
                    MergeRequest.status == 'ready'
                ).order_by(MergeRequest.recognized_at).all()
                
                if not ready_mrs:
                    return
                
                logger.info(f"Found {len(ready_mrs)} ready MRs")
                
                # Decide single vs batch merge
                if len(ready_mrs) >= batch_size and batch_size > 1:
                    # Batch merge
                    logger.info(f"Initiating batch merge for {batch_size} MRs")
                    mr_data_list = []
                    for db_mr in ready_mrs[:batch_size]:
                        mr_data = await self.gitlab.get_merge_request(
                            self.gitlab_project_id,
                            db_mr.gitlab_mr_iid
                        )
                        mr_data['recognized_at'] = db_mr.recognized_at
                        mr_data_list.append(mr_data)
                    
                    target_branch = ready_mrs[0].target_branch
                    await self.merger.merge_batch(
                        self.gitlab_project_id,
                        target_branch,
                        mr_data_list,
                        session
                    )
                else:
                    # Single merge
                    for db_mr in ready_mrs[:1]:  # Process one at a time
                        logger.info(f"Initiating single merge for MR !{db_mr.gitlab_mr_iid}")
                        mr_data = await self.gitlab.get_merge_request(
                            self.gitlab_project_id,
                            db_mr.gitlab_mr_iid
                        )
                        await self.merger.merge_single_mr(
                            self.gitlab_project_id,
                            mr_data,
                            session
                        )
        
        except Exception as e:
            logger.error(f"Error checking ready MRs: {e}")
    
    async def stop(self):
        """Stop the worker POD."""
        logger.info(f"Stopping Worker POD for project {self.project_id}")
        self.running = False
        
        if self.gitlab:
            await self.gitlab.close()
        
        if self.redis_client:
            await self.redis_client.close()


async def main(project_id: str):
    """Main entry point for worker POD."""
    worker = WorkerPOD(project_id)
    await worker.initialize()
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await worker.stop()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python worker_pod.py <project_id>")
        sys.exit(1)
    
    project_id = sys.argv[1]
    asyncio.run(main(project_id))
