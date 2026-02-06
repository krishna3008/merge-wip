"""
MR validation logic for Worker POD.
DRY implementation of all validation checks.
"""
import logging
from typing import Dict, Any, Tuple
from backend.gitlab_integration.gitlab_models import GitLabMergeRequest

logger = logging.getLogger(__name__)


class MRValidator:
    """Validates merge requests against merge criteria."""
    
    def __init__(self, gitlab_client, merge_assist_user_id: int):
        """
        Initialize validator.
        
        Args:
            gitlab_client: GitLab unified client
            merge_assist_user_id: ID of the Merge Assist user in GitLab
        """
        self.gitlab = gitlab_client
        self.merge_assist_user_id = merge_assist_user_id
    
    async def is_pipeline_successful(self, mr_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if MR pipeline is successful.
        
        Returns:
            (success: bool, reason: str)
        """
        pipeline = mr_data.get('pipeline')
        if not pipeline:
            return False, "No pipeline found"
        
        status = pipeline.get('status')
        if status == 'success':
            return True, "Pipeline successful"
        elif status in ['running', 'pending', 'created']:
            return False, f"Pipeline still {status}"
        else:
            return False, f"Pipeline {status}"
    
    def is_approved(self, mr_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if MR has required approvals.
        
        Returns:
            (approved: bool, reason: str)
        """
        # Check if discussions are resolved
        if not mr_data.get('blocking_discussions_resolved', True):
            return False, "Blocking discussions not resolved"
        
        # Check merge status
        merge_status = mr_data.get('merge_status')
        if merge_status != 'can_be_merged':
            return False, f"Merge status: {merge_status}"
        
        return True, "MR is approved"
    
    def is_assigned_to_merge_assist(self, mr_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if MR is assigned to Merge Assist user.
        
        Returns:
            (assigned: bool, reason: str)
        """
        assignees = mr_data.get('assignees', [])
        reviewers = mr_data.get('reviewers', [])
        
        # Check if Merge Assist is assignee or reviewer
        assignee_ids = [a.get('id') for a in assignees]
        reviewer_ids = [r.get('id') for r in reviewers]
        
        if self.merge_assist_user_id in assignee_ids:
            return True, "Assigned as assignee"
        elif self.merge_assist_user_id in reviewer_ids:
            return True, "Assigned as reviewer"
        else:
            return False, "Not assigned to Merge Assist"
    
    def has_conflicts(self, mr_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if MR has conflicts.
        
        Returns:
            (has_conflicts: bool, reason: str)
        """
        if mr_data.get('has_conflicts', False):
            return True, "MR has conflicts"
        return False, "No conflicts"
    
    def is_work_in_progress(self, mr_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if MR is marked as WIP or Draft.
        
        Returns:
            (is_wip: bool, reason: str)
        """
        if mr_data.get('work_in_progress', False) or mr_data.get('draft', False):
            return True, "MR is WIP/Draft"
        return False, "MR is not WIP"
    
    async def is_ready_to_merge(self, mr_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Comprehensive check if MR is ready to merge.
        
        Returns:
            (ready: bool, reasons: List[str])
        """
        reasons = []
        
        # Check assignment
        assigned, reason = self.is_assigned_to_merge_assist(mr_data)
        if not assigned:
            reasons.append(reason)
        
        # Check WIP/Draft
        is_wip, reason = self.is_work_in_progress(mr_data)
        if is_wip:
            reasons.append(reason)
        
        # Check conflicts
        has_conf, reason = self.has_conflicts(mr_data)
        if has_conf:
            reasons.append(reason)
        
        # Check approval
        approved, reason = self.is_approved(mr_data)
        if not approved:
            reasons.append(reason)
        
        # Check pipeline
        pipeline_ok, reason = await self.is_pipeline_successful(mr_data)
        if not pipeline_ok:
            reasons.append(reason)
        
        is_ready = len(reasons) == 0
        return is_ready, reasons
