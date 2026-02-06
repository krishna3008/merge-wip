"""
Role-Based Access Control (RBAC) system.
"""
from enum import Enum
from typing import List, Set, Optional
from functools import wraps
from fastapi import HTTPException, status


class RoleEnum(str, Enum):
    """Role enumeration matching database roles."""
    ADMIN = "admin"
    PROJECT_OWNER = "project_owner"
    PRIORITY_MANAGER = "priority_manager"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Permission types."""
    # Global permissions
    MANAGE_USERS = "manage_users"
    MANAGE_ALL_PROJECTS = "manage_all_projects"
    VIEW_ALL_LOGS = "view_all_logs"
    
    # Project-specific permissions
    MANAGE_PROJECT = "manage_project"
    VIEW_PROJECT = "view_project"
    SET_PRIORITY = "set_priority"
    VIEW_LOGS = "view_logs"
    UPDATE_CONFIG = "update_config"


# Role-Permission mapping
ROLE_PERMISSIONS: dict[RoleEnum, Set[Permission]] = {
    RoleEnum.ADMIN: {
        Permission.MANAGE_USERS,
        Permission.MANAGE_ALL_PROJECTS,
        Permission.VIEW_ALL_LOGS,
        Permission.MANAGE_PROJECT,
        Permission.VIEW_PROJECT,
        Permission.SET_PRIORITY,
        Permission.VIEW_LOGS,
        Permission.UPDATE_CONFIG,
    },
    RoleEnum.PROJECT_OWNER: {
        Permission.MANAGE_PROJECT,
        Permission.VIEW_PROJECT,
        Permission.VIEW_LOGS,
        Permission.UPDATE_CONFIG,
    },
    RoleEnum.PRIORITY_MANAGER: {
        Permission.VIEW_PROJECT,
        Permission.SET_PRIORITY,
    },
    RoleEnum.VIEWER: {
        Permission.VIEW_PROJECT,
    },
}


def has_permission(user_roles: List[str], required_permission: Permission) -> bool:
    """
    Check if user has a specific permission based on their roles.
    
    Args:
        user_roles: List of role names assigned to user
        required_permission: Required permission to check
    
    Returns:
        True if user has the permission, False otherwise
    """
    for role_name in user_roles:
        try:
            role = RoleEnum(role_name)
            if required_permission in ROLE_PERMISSIONS[role]:
                return True
        except ValueError:
            continue
    return False


def has_any_role(user_roles: List[str], required_roles: List[RoleEnum]) -> bool:
    """
    Check if user has any of the required roles.
    
    Args:
        user_roles: List of role names assigned to user
        required_roles: List of required roles
    
    Returns:
        True if user has any of the required roles
    """
    role_set = {RoleEnum(r) for r in user_roles if r in [role.value for role in RoleEnum]}
    required_set = set(required_roles)
    return bool(role_set & required_set)


def require_permission(permission: Permission):
    """
    Decorator to enforce permission checks on API endpoints.
    
    Usage:
        @require_permission(Permission.MANAGE_PROJECT)
        async def my_endpoint(current_user: dict):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs (injected by auth middleware)
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )
            
            user_roles = current_user.get('roles', [])
            if not has_permission(user_roles, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: requires {permission.value}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_role(*roles: RoleEnum):
    """
    Decorator to enforce role checks on API endpoints.
    
    Usage:
        @require_role(RoleEnum.ADMIN, RoleEnum.PROJECT_OWNER)
        async def my_endpoint(current_user: dict):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )
            
            user_roles = current_user.get('roles', [])
            if not has_any_role(user_roles, list(roles)):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: requires one of {[r.value for r in roles]}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def check_project_permission(user_id: str, project_id: str, permission: Permission, db_session) -> bool:
    """
    Check if user has specific permission for a project.
    
    Args:
        user_id: User UUID
        project_id: Project UUID
        permission: Required permission
        db_session: Database session
    
    Returns:
        True if user has permission, False otherwise
    """
    from backend.database.models import User, ProjectPermission
    
    # Get user with roles
    user = db_session.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    
    # Check if user has global permission (admin or global role)
    user_role_names = [ur.role.name for ur in user.user_roles]
    if has_permission(user_role_names, permission):
        # Check if it's a global permission
        if permission in [Permission.MANAGE_ALL_PROJECTS, Permission.VIEW_ALL_LOGS, Permission.MANAGE_USERS]:
            return True
    
    # Check project-specific permissions
    project_perm = db_session.query(ProjectPermission).filter(
        ProjectPermission.user_id == user_id,
        ProjectPermission.project_id == project_id
    ).first()
    
    if not project_perm:
        return False
    
    # Map permission to project permission fields
    if permission == Permission.MANAGE_PROJECT and project_perm.can_manage:
        return True
    if permission == Permission.SET_PRIORITY and project_perm.can_set_priority:
        return True
    
    return False
