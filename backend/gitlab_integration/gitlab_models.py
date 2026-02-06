"""
Pydantic models for GitLab entities.
Data validation and serialization for GitLab API responses.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class GitLabUser(BaseModel):
    """GitLab user model."""
    id: int
    username: str
    name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None


class GitLabPipeline(BaseModel):
    """GitLab pipeline model."""
    id: int
    project_id: int
    status: str  # created, waiting_for_resource, preparing, pending, running, success, failed, canceled, skipped
    ref: str
    sha: str
    web_url: str
    created_at: datetime
    updated_at: datetime
    
    def is_successful(self) -> bool:
        """Check if pipeline is successful."""
        return self.status == "success"
    
    def is_running(self) -> bool:
        """Check if pipeline is currently running."""
        return self.status in ["created", "waiting_for_resource", "preparing", "pending", "running"]
    
    def is_failed(self) -> bool:
        """Check if pipeline failed."""
        return self.status in ["failed", "canceled"]


class GitLabMergeRequest(BaseModel):
    """GitLab merge request model."""
    id: int
    iid: int
    project_id: int
    title: str
    description: Optional[str] = None
    state: str  # opened, closed, locked, merged
    created_at: datetime
    updated_at: datetime
    merged_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    target_branch: str
    source_branch: str
    author: GitLabUser
    assignees: List[GitLabUser] = []
    reviewers: List[GitLabUser] = []
    labels: List[str] = []
    web_url: str
    sha: str
    merge_commit_sha: Optional[str] = None
    squash_commit_sha: Optional[str] = None
    merge_status: str  # can_be_merged, cannot_be_merged, checking, unchecked
    has_conflicts: bool = False
    blocking_discussions_resolved: bool = True
    work_in_progress: bool = False
    draft: bool = False
    pipeline: Optional[GitLabPipeline] = None
    
    def is_mergeable(self) -> bool:
        """Check if MR can be merged."""
        return (
            self.state == "opened"
            and self.merge_status == "can_be_merged"
            and not self.has_conflicts
            and self.blocking_discussions_resolved
            and not self.work_in_progress
            and not self.draft
        )
    
    def has_label(self, label: str) -> bool:
        """Check if MR has a specific label."""
        return label in self.labels


class GitLabProject(BaseModel):
    """GitLab project model."""
    id: int
    name: str
    path: str
    path_with_namespace: str
    web_url: str
    default_branch: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None


class GitLabComment(BaseModel):
    """GitLab comment/note model."""
    id: int
    body: str
    author: GitLabUser
    created_at: datetime
    updated_at: datetime
    system: bool = False
    noteable_type: str
    noteable_id: int


class GitLabLabel(BaseModel):
    """GitLab label model."""
    id: int
    name: str
    color: str
    description: Optional[str] = None
