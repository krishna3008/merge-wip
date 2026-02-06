"""
FastAPI authentication middleware for JWT token validation.
"""
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import logging

from .auth import verify_token

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials) -> Dict[str, Any]:
    """
    Extract and validate JWT token from request headers.
    
    Args:
        credentials: HTTP Authorization credentials
    
    Returns:
        User data from token payload
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    payload = verify_token(token, token_type="access")
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return payload


async def get_current_active_user(current_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that the user is marked as active.
    
    Args:
        current_user: User data from token
    
    Returns:
        User data if active
    
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


async def get_optional_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Extract user from token if present, but don't require it.
    Used for endpoints that have optional authentication.
    
    Args:
        request: FastAPI request object
    
    Returns:
        User data if authenticated, None otherwise
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header.replace("Bearer ", "")
    payload = verify_token(token, token_type="access")
    return payload


class AuthMiddleware:
    """
    Middleware for automatic JWT authentication on all requests.
    Can be configured to exclude certain paths.
    """
    
    def __init__(self, app, exclude_paths: list[str] = None):
        """
        Initialize auth middleware.
        
        Args:
            app: FastAPI app instance
            exclude_paths: List of paths to exclude from authentication
        """
        self.app = app
        self.exclude_paths = exclude_paths or [
            "/auth/login",
            "/auth/refresh",
            "/docs",
            "/openapi.json",
            "/health",
        ]
    
    async def __call__(self, request: Request, call_next):
        """Process request with authentication check."""
        # Skip authentication for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        # Extract and verify token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = auth_header.replace("Bearer ", "")
        payload = verify_token(token, token_type="access")
        
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Inject user info into request state
        request.state.user = payload
        
        response = await call_next(request)
        return response
