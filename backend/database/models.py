"""
SQLAlchemy ORM models for Merge Assist database.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text,
    BigInteger, ForeignKey, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid

Base = declarative_base()


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(Base, TimestampMixin):
    """User accounts for authentication."""
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True, index=True)

    # Relationships
    user_roles = relationship('UserRole', back_populates='user', cascade='all, delete-orphan')
    project_permissions = relationship('ProjectPermission', back_populates='user', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<User(username='{self.username}', email='{self.email}')>"


class Role(Base):
    """Role definitions for RBAC."""
    __tablename__ = 'roles'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    user_roles = relationship('UserRole', back_populates='role', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Role(name='{self.name}')>"


class UserRole(Base):
    """User-Role mapping."""
    __tablename__ = 'user_roles'
    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', name='uq_user_role'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship('User', back_populates='user_roles')
    role = relationship('Role', back_populates='user_roles')

    def __repr__(self):
        return f"<UserRole(user_id='{self.user_id}', role_id='{self.role_id}')>"


class Project(Base, TimestampMixin):
    """GitLab projects onboarded to Merge Assist."""
    __tablename__ = 'projects'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gitlab_project_id = Column(BigInteger, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    gitlab_url = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, index=True)

    # Relationships
    config = relationship('ProjectConfig', back_populates='project', uselist=False, cascade='all, delete-orphan')
    merge_requests = relationship('MergeRequest', back_populates='project', cascade='all, delete-orphan')
    batch_operations = relationship('BatchOperation', back_populates='project', cascade='all, delete-orphan')
    permissions = relationship('ProjectPermission', back_populates='project', cascade='all, delete-orphan')
    logs = relationship('Log', back_populates='project', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Project(name='{self.name}', gitlab_id={self.gitlab_project_id})>"


class ProjectPermission(Base):
    """User permissions for projects."""
    __tablename__ = 'project_permissions'
    __table_args__ = (
        UniqueConstraint('user_id', 'project_id', name='uq_user_project'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    can_manage = Column(Boolean, default=False)
    can_set_priority = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship('User', back_populates='project_permissions')
    project = relationship('Project', back_populates='permissions')

    def __repr__(self):
        return f"<ProjectPermission(user_id='{self.user_id}', project_id='{self.project_id}')>"


class ProjectConfig(Base, TimestampMixin):
    """Per-project configuration."""
    __tablename__ = 'project_config'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    target_branches = Column(JSON, nullable=False, default=list)  # List of target branch names
    batch_size = Column(Integer, nullable=False, default=5)
    polling_interval_seconds = Column(Integer, default=300)
    labels = Column(JSON, nullable=False, default=dict)  # Custom labels configuration
    webhook_enabled = Column(Boolean, default=True)
    ai_debug_enabled = Column(Boolean, default=False)

    # Relationships
    project = relationship('Project', back_populates='config')

    def __repr__(self):
        return f"<ProjectConfig(project_id='{self.project_id}', batch_size={self.batch_size})>"


class MergeRequest(Base, TimestampMixin):
    """Tracked merge requests."""
    __tablename__ = 'merge_requests'
    __table_args__ = (
        UniqueConstraint('project_id', 'gitlab_mr_iid', name='uq_project_mr_iid'),
        Index('idx_mrs_priority', 'priority', postgresql_using='btree', postgresql_ops={'priority': 'DESC'}),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    gitlab_mr_iid = Column(BigInteger, nullable=False, index=True)
    gitlab_mr_id = Column(BigInteger, nullable=False)
    title = Column(Text, nullable=False)
    source_branch = Column(String(255), nullable=False)
    target_branch = Column(String(255), nullable=False, index=True)
    author = Column(String(255))
    status = Column(String(50), nullable=False, index=True)  # recognized, not_ready, ready_to_merge, merging, merged, rejected, failed
    rejection_count = Column(Integer, default=0)
    rejection_reason = Column(Text)
    priority = Column(Integer, default=0)
    pipeline_status = Column(String(50))
    is_approved = Column(Boolean, default=False)
    is_assigned = Column(Boolean, default=False)
    labels = Column(JSON, default=list)
    recognized_at = Column(DateTime(timezone=True), index=True)
    merged_at = Column(DateTime(timezone=True))

    # Relationships
    project = relationship('Project', back_populates='merge_requests')
    history = relationship('MergeHistory', back_populates='merge_request', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<MergeRequest(iid={self.gitlab_mr_iid}, title='{self.title[:30]}...', status='{self.status}')>"


class BatchOperation(Base):
    """Batch merge operations tracking."""
    __tablename__ = 'batch_operations'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    target_branch = Column(String(255), nullable=False)
    batch_branch = Column(String(255), nullable=False)
    batch_mr_iid = Column(BigInteger)
    batch_mr_id = Column(BigInteger)
    mr_ids = Column(JSON, nullable=False)  # Array of MR UUIDs
    status = Column(String(50), nullable=False, index=True)  # pending, pipeline_running, pipeline_success, pipeline_failed, merging, completed, failed
    pipeline_status = Column(String(50))
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship('Project', back_populates='batch_operations')
    history = relationship('MergeHistory', back_populates='batch_operation')

    def __repr__(self):
        return f"<BatchOperation(id='{self.id}', status='{self.status}', mr_count={len(self.mr_ids) if self.mr_ids else 0})>"


class MergeHistory(Base):
    """Audit log of MR actions."""
    __tablename__ = 'merge_history'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mr_id = Column(UUID(as_uuid=True), ForeignKey('merge_requests.id', ondelete='CASCADE'), nullable=False, index=True)
    batch_operation_id = Column(UUID(as_uuid=True), ForeignKey('batch_operations.id', ondelete='SET NULL'))
    action = Column(String(50), nullable=False, index=True)  # recognized, rejected, merged, failed, priority_set, label_added
    details = Column(JSON)
    performed_by = Column(String(255), default='merge-assist')
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    merge_request = relationship('MergeRequest', back_populates='history')
    batch_operation = relationship('BatchOperation', back_populates='history')

    def __repr__(self):
        return f"<MergeHistory(action='{self.action}', mr_id='{self.mr_id}')>"


class Log(Base):
    """Application logs from all services."""
    __tablename__ = 'logs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    worker_pod_id = Column(String(255), index=True)
    level = Column(String(20), nullable=False, index=True)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message = Column(Text, nullable=False)
    metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    project = relationship('Project', back_populates='logs')

    def __repr__(self):
        return f"<Log(level='{self.level}', message='{self.message[:50]}...')>"
