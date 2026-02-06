"""
Label management for merge requests.
Centralized label operations following DRY principles.
"""
import logging
from typing import List

logger = logging.getLogger(__name__)


class LabelManager:
    """Manages GitLab MR labels with consistent naming."""
    
    def __init__(self, gitlab_client, project_config):
        """
        Initialize label manager.
        
        Args:
            gitlab_client: GitLab unified client
            project_config: ProjectConfig instance
        """
        self.gitlab = gitlab_client
        self.config = project_config
    
    async def add_recognized_label(self, project_id: int, mr_iid: int) -> bool:
        """Add 'Recognised for Merge' label."""
        label = self.config.get_label('recognized')
        return await self.gitlab.add_label(project_id, mr_iid, [label])
    
    async def add_not_ready_label(self, project_id: int, mr_iid: int) -> bool:
        """Add 'Not Ready for Merge' label."""
        label = self.config.get_label('not_ready')
        return await self.gitlab.add_label(project_id, mr_iid, [label])
    
    async def add_rejected_label(self, project_id: int, mr_iid: int) -> bool:
        """Add 'Rejected' label."""
        label = self.config.get_label('rejected')
        # Remove not_ready label if present
        not_ready_label = self.config.get_label('not_ready')
        await self.gitlab.remove_label(project_id, mr_iid, [not_ready_label])
        return await self.gitlab.add_label(project_id, mr_iid, [label])
    
    async def add_ready_to_merge_label(self, project_id: int, mr_iid: int) -> bool:
        """Add 'Ready to Merge' label."""
        label = self.config.get_label('ready_to_merge')
        return await self.gitlab.add_label(project_id, mr_iid, [label])
    
    async def add_batch_mr_label(self, project_id: int, mr_iid: int) -> bool:
        """Add 'Batch Merge Request' label."""
        label = self.config.get_label('batch_mr')
        return await self.gitlab.add_label(project_id, mr_iid, [label])
    
    async def remove_recognized_label(self, project_id: int, mr_iid: int) -> bool:
        """Remove 'Recognised for Merge' label."""
        label = self.config.get_label('recognized')
        return await self.gitlab.remove_label(project_id, mr_iid, [label])
    
    async def remove_not_ready_label(self, project_id: int, mr_iid: int) -> bool:
        """Remove 'Not Ready for Merge' label."""
        label = self.config.get_label('not_ready')
        return await self.gitlab.remove_label(project_id, mr_iid, [label])
    
    async def remove_ready_to_merge_label(self, project_id: int, mr_iid: int) -> bool:
        """Remove 'Ready to Merge' label."""
        label = self.config.get_label('ready_to_merge')
        return await self.gitlab.remove_label(project_id, mr_iid, [label])
    
    async def cleanup_merge_assist_labels(self, project_id: int, mr_iid: int) -> bool:
        """Remove all Merge Assist labels after successful merge."""
        labels_to_remove = [
            self.config.get_label('recognized'),
            self.config.get_label('ready_to_merge'),
            self.config.get_label('not_ready')
        ]
        return await self.gitlab.remove_label(project_id, mr_iid, labels_to_remove)
