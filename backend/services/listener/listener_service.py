"""
Listener service - receives GitLab webhooks.
Scalable with HPA.
"""
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import redis.asyncio as aioredis

from backend.config.config import config_manager
from backend.database.connection import db
from backend.secrets.secrets_manager import SecretsManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Merge Assist Listener")

# Global state
redis_client: aioredis.Redis = None


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    global redis_client
    
    logger.info("Starting Listener Service")
    
    config = config_manager.settings
    
    # Initialize database
    db.initialize(config.database_url)
    
    # Initialize Redis
    redis_client = await aioredis.from_url(config.redis_url)
    
    logger.info("Listener Service ready")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global redis_client
    
    if redis_client:
        await redis_client.close()
    
    logger.info("Listener Service stopped")


@app.post("/webhook/gitlab")
async def gitlab_webhook(request: Request):
    """
    Receive GitLab webhook events.
    
    Supported events:
    - merge_request (opened, updated, assigned)
    - pipeline (success, failed)
    """
    try:
        # Get webhook payload
        payload = await request.json()
        event_type = payload.get('object_kind')
        
        logger.info(f"Received webhook: {event_type}")
        
        if event_type == 'merge_request':
            return await handle_merge_request_event(payload)
        elif event_type == 'pipeline':
            return await handle_pipeline_event(payload)
        else:
            logger.info(f"Ignoring event type: {event_type}")
            return JSONResponse({"status": "ignored"})
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_merge_request_event(payload: dict):
    """Handle merge request webhook events."""
    try:
        mr_data = payload.get('object_attributes', {})
        project = payload.get('project', {})
        
        mr_iid = mr_data.get('iid')
        project_id_gitlab = project.get('id')
        action = mr_data.get('action')
        
        logger.info(f"MR event: !{mr_iid} - {action}")
        
        # Get project from database
        with db.get_session() as session:
            from backend.database.models import Project, MergeRequest
            from datetime import datetime
            
            db_project = session.query(Project).filter(
                Project.gitlab_id == project_id_gitlab
            ).first()
            
            if not db_project:
                logger.warning(f"Project {project_id_gitlab} not found in database")
                return JSONResponse({"status": "project_not_found"})
            
            # Check if MR is assigned to Merge Assist
            assignees = payload.get('assignees', [])
            secrets = SecretsManager()
            merge_assist_user_id = int(secrets.get_secret('gitlab/merge_assist_user_id'))
            
            is_assigned = any(a.get('id') == merge_assist_user_id for a in assignees)
            
            if not is_assigned:
                logger.info(f"MR !{mr_iid} not assigned to Merge Assist, ignoring")
                return JSONResponse({"status": "not_assigned"})
            
            # Create or update MR in database
            db_mr = session.query(MergeRequest).filter(
                MergeRequest.project_id == str(db_project.id),
                MergeRequest.gitlab_mr_iid == mr_iid
            ).first()
            
            if not db_mr:
                logger.info(f"Creating new MR record for !{mr_iid}")
                db_mr = MergeRequest(
                    project_id=str(db_project.id),
                    gitlab_mr_iid=mr_iid,
                    title=mr_data.get('title'),
                    source_branch=mr_data.get('source_branch'),
                    target_branch=mr_data.get('target_branch'),
                    status='recognized',
                    recognized_at=datetime.utcnow()
                )
                session.add(db_mr)
            else:
                logger.info(f"Updating MR record for !{mr_iid}")
                db_mr.title = mr_data.get('title')
                db_mr.source_branch = mr_data.get('source_branch')
                db_mr.target_branch = mr_data.get('target_branch')
            
            session.commit()
            
            # Publish event to Redis for worker POD
            await redis_client.publish(
                f'project:{db_project.id}',
                str(mr_iid)
            )
            
            logger.info(f"Published event for MR !{mr_iid}")
        
        return JSONResponse({"status": "processed"})
    
    except Exception as e:
        logger.error(f"Error handling MR event: {e}")
        raise


async def handle_pipeline_event(payload: dict):
    """Handle pipeline webhook events."""
    try:
        pipeline_data = payload.get('object_attributes', {})
        project = payload.get('project', {})
        merge_requests = payload.get('merge_requests', [])
        
        pipeline_status = pipeline_data.get('status')
        
        logger.info(f"Pipeline event: {pipeline_status}")
        
        # If pipeline is for an MR and completed, notify worker
        if merge_requests and pipeline_status in ['success', 'failed', 'canceled']:
            with db.get_session() as session:
                from backend.database.models import Project
                
                project_id_gitlab = project.get('id')
                db_project = session.query(Project).filter(
                    Project.gitlab_id == project_id_gitlab
                ).first()
                
                if db_project:
                    for mr in merge_requests:
                        mr_iid = mr.get('iid')
                        # Publish event to trigger re-validation
                        await redis_client.publish(
                            f'project:{db_project.id}',
                            str(mr_iid)
                        )
        
        return JSONResponse({"status": "processed"})
    
    except Exception as e:
        logger.error(f"Error handling pipeline event: {e}")
        raise


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
