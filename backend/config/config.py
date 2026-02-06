"""
Configuration management system for Merge Assist.
Handles environment-based settings and project-specific configurations.
"""
import os
from typing import Optional, List, Dict, Any
from pydantic import BaseSettings, Field, validator
from pydantic_settings import BaseSettings as PydanticBaseSettings
import json


class Settings(PydanticBaseSettings):
    """Application-wide settings."""
    
    # Environment
    environment: str = Field(default="development", env="ENVIRONMENT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Database
    db_host: str = Field(env="DB_HOST")
    db_port: int = Field(default=5432, env="DB_PORT")
    db_user: str = Field(env="DB_USER")
    db_password: str = Field(env="DB_PASSWORD")
    db_name: str = Field(env="DB_NAME")
    
    # Redis
    redis_host: str = Field(env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_db: int = Field(default=0, env="REDIS_DB")
    
    # GitLab
    gitlab_url: str = Field(env="GITLAB_URL")
    gitlab_token: Optional[str] = Field(default=None, env="GITLAB_TOKEN")
    
    # JWT
    jwt_secret_key: str = Field(env="JWT_SECRET_KEY")
    access_token_expire_minutes: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    
    # Secrets Provider
    secrets_provider: str = Field(default="local", env="SECRETS_PROVIDER")
    aws_region: str = Field(default="us-east-1", env="AWS_REGION")
    
    # Watcher
    watcher_polling_interval: int = Field(default=300, env="WATCHER_POLLING_INTERVAL")
    
    # Worker
    default_batch_size: int = Field(default=5, env="DEFAULT_BATCH_SIZE")
    max_rejection_count: int = Field(default=3, env="MAX_REJECTION_COUNT")
    
    # Health Check
    health_check_interval: int = Field(default=60, env="HEALTH_CHECK_INTERVAL")
    alert_email: Optional[str] = Field(default=None, env="ALERT_EMAIL")
    
    # AI Assistant
    ai_enabled: bool = Field(default=False, env="AI_ENABLED")
    ai_api_key: Optional[str] = Field(default=None, env="AI_API_KEY")
    ai_model: str = Field(default="gpt-4", env="AI_MODEL")
    
    # Frontend
    frontend_url: str = Field(default="http://localhost:3000", env="FRONTEND_URL")
    api_url: str = Field(default="http://localhost:8000", env="API_URL")
    
    @property
    def database_url(self) -> str:
        """Construct database URL."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        password_part = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


class ProjectConfig:
    """Per-project configuration (stored in database)."""
    
    def __init__(self, config_dict: Dict[str, Any]):
        """
        Initialize project configuration from dictionary.
        
        Args:
            config_dict: Configuration dictionary from database
        """
        self.project_id: str = config_dict.get("project_id")
        self.target_branches: List[str] = config_dict.get("target_branches", [])
        self.batch_size: int = config_dict.get("batch_size", 5)
        self.polling_interval_seconds: int = config_dict.get("polling_interval_seconds", 300)
        self.labels: Dict[str, str] = config_dict.get("labels", {})
        self.webhook_enabled: bool = config_dict.get("webhook_enabled", True)
        self.ai_debug_enabled: bool = config_dict.get("ai_debug_enabled", False)
    
    def get_label(self, label_type: str) -> str:
        """
        Get label for a specific type.
        
        Args:
            label_type: Type of label (e.g., 'recognized', 'not_ready', 'rejected')
        
        Returns:
            Label text
        """
        default_labels = {
            "recognized": "Merge Assist: Recognised for Merge",
            "not_ready": "Merge Assist: Not Ready for Merge",
            "rejected": "Merge Assist: Rejected",
            "ready_to_merge": "Merge Assist: Ready to Merge",
            "batch_mr": "Merge Assist: Batch Merge Request"
        }
        
        return self.labels.get(label_type, default_labels.get(label_type, f"Merge Assist: {label_type}"))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "project_id": self.project_id,
            "target_branches": self.target_branches,
            "batch_size": self.batch_size,
            "polling_interval_seconds": self.polling_interval_seconds,
            "labels": self.labels,
            "webhook_enabled": self.webhook_enabled,
            "ai_debug_enabled": self.ai_debug_enabled
        }


class ConfigManager:
    """
    Configuration manager for accessing project-specific configurations.
    Singleton pattern for DRY.
    """
    
    _instance = None
    _settings: Optional[Settings] = None
    _project_configs: Dict[str, ProjectConfig] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance
    
    def initialize(self):
        """Load application settings."""
        if self._settings is None:
            self._settings = Settings()
    
    @property
    def settings(self) -> Settings:
        """Get application settings."""
        if self._settings is None:
            self.initialize()
        return self._settings
    
    def load_project_config(self, project_id: str, db_session) -> ProjectConfig:
        """
        Load project configuration from database.
        
        Args:
            project_id: Project UUID
            db_session: Database session
        
        Returns:
            ProjectConfig instance
        """
        from backend.database.models import ProjectConfig as ProjectConfigModel
        
        # Check cache first
        if project_id in self._project_configs:
            return self._project_configs[project_id]
        
        # Load from database
        config_model = db_session.query(ProjectConfigModel).filter(
            ProjectConfigModel.project_id == project_id
        ).first()
        
        if not config_model:
            raise ValueError(f"No configuration found for project {project_id}")
        
        config_dict = {
            "project_id": str(project_id),
            "target_branches": config_model.target_branches,
            "batch_size": config_model.batch_size,
            "polling_interval_seconds": config_model.polling_interval_seconds,
            "labels": config_model.labels,
            "webhook_enabled": config_model.webhook_enabled,
            "ai_debug_enabled": config_model.ai_debug_enabled
        }
        
        config = ProjectConfig(config_dict)
        self._project_configs[project_id] = config
        
        return config
    
    def update_project_config(self, project_id: str, updates: Dict[str, Any], db_session) -> ProjectConfig:
        """
        Update project configuration.
        
        Args:
            project_id: Project UUID
            updates: Dictionary of fields to update
            db_session: Database session
        
        Returns:
            Updated ProjectConfig instance
        """
        from backend.database.models import ProjectConfig as ProjectConfigModel
        
        config_model = db_session.query(ProjectConfigModel).filter(
            ProjectConfigModel.project_id == project_id
        ).first()
        
        if not config_model:
            raise ValueError(f"No configuration found for project {project_id}")
        
        # Update fields
        for key, value in updates.items():
            if hasattr(config_model, key):
                setattr(config_model, key, value)
        
        db_session.commit()
        
        # Invalidate cache
        if project_id in self._project_configs:
            del self._project_configs[project_id]
        
        # Reload and return
        return self.load_project_config(project_id, db_session)
    
    def clear_cache(self, project_id: Optional[str] = None):
        """
        Clear project configuration cache.
        
        Args:
            project_id: Specific project to clear, or None to clear all
        """
        if project_id:
            self._project_configs.pop(project_id, None)
        else:
            self._project_configs.clear()


# Global configuration manager instance
config_manager = ConfigManager()
