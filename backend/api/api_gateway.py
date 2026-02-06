"""
API Gateway - main FastAPI application.
Serves frontend and provides authenticated endpoints.
"""
import logging
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from backend.config.config import config_manager
from backend.database.connection import db
from backend.database.models import User, Project, MergeRequest, Log
from backend.auth.auth import verify_password, create_access_token, create_refresh_token, verify_token
from backend.auth.middleware import get_current_active_user
from backend.auth.rbac import require_permission, Permission, Role

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Merge Assist API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config_manager.settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


# Pydantic models
class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ProjectResponse(BaseModel):
    id: str
    name: str
    gitlab_id: int
    is_active: bool


class MRResponse(BaseModel):
    id: str
    gitlab_mr_iid: int
    title: str
    status: str
    target_branch: str
    recognized_at: Optional[datetime]


# Auth endpoints
@app.post("/auth/login", response_model=LoginResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint."""
    with db.get_session() as session:
        user = session.query(User).filter(User.username == form_data.username).first()
        
        if not user or not verify_password(form_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not active"
            )
        
        # Get user roles
        roles = [ur.role.name for ur in user.user_roles]
        
        token_data = {
            "user_id": str(user.id),
            "username": user.username,
            "email": user.email,
            "roles": roles
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token
        )


@app.get("/auth/me")
async def get_current_user(current_user: dict = Depends(get_current_active_user)):
    """Get current user info."""
    return current_user


# Project endpoints
@app.get("/projects", response_model=List[ProjectResponse])
@require_permission(Permission.VIEW_PROJECTS)
async def list_projects(current_user: dict = Depends(get_current_active_user)):
    """List all projects."""
    with db.get_session() as session:
        projects = session.query(Project).all()
        return [
            ProjectResponse(
                id=str(p.id),
                name=p.name,
                gitlab_id=p.gitlab_id,
                is_active=p.is_active
            )
            for p in projects
        ]


@app.get("/projects/{project_id}/mrs", response_model=List[MRResponse])
@require_permission(Permission.VIEW_PROJECT)
async def list_project_mrs(
    project_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """List MRs for a project."""
    with db.get_session() as session:
        mrs = session.query(MergeRequest).filter(
            MergeRequest.project_id == project_id
        ).order_by(MergeRequest.recognized_at.desc()).all()
        
        return [
            MRResponse(
                id=str(mr.id),
                gitlab_mr_iid=mr.gitlab_mr_iid,
                title=mr.title,
                status=mr.status,
                target_branch=mr.target_branch,
                recognized_at=mr.recognized_at
            )
            for mr in mrs
        ]


@app.post("/mrs/{mr_id}/priority")
@require_permission(Permission.SET_MR_PRIORITY)
async def set_mr_priority(
    mr_id: str,
    new_priority: int,
    current_user: dict = Depends(get_current_active_user)
):
    """Change MR priority in queue."""
    with db.get_session() as session:
        mr = session.query(MergeRequest).filter(MergeRequest.id == mr_id).first()
        
        if not mr:
            raise HTTPException(status_code=404, detail="MR not found")
        
        mr.priority = new_priority
        session.commit()
        
        return {"status": "priority_updated", "mr_id": mr_id, "priority": new_priority}


@app.get("/logs")
@require_permission(Permission.VIEW_LOGS)
async def get_logs(
    project_id: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_active_user)
):
    """Get application logs."""
    with db.get_session() as session:
        query = session.query(Log)
        
        if project_id:
            query = query.filter(Log.project_id == project_id)
        
        logs = query.order_by(Log.created_at.desc()).limit(limit).all()
        
        return [
            {
                "id": str(log.id),
                "level": log.level,
                "message": log.message,
                "created_at": log.created_at
            }
            for log in logs
        ]


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "api-gateway"}


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    config = config_manager.settings
    db.initialize(config.database_url)
    logger.info("API Gateway started")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
