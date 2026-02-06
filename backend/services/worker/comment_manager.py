"""
Comment templates and management for MRs.
DRY implementation for consistent messaging.
"""
import logging
from typing import List

logger = logging.getLogger(__name__)


class CommentManager:
    """Manages MR comments with templated messages."""
    
    def __init__(self, gitlab_client):
        """
        Initialize comment manager.
        
        Args:
            gitlab_client: GitLab unified client
        """
        self.gitlab = gitlab_client
    
    def _format_comment(self, message: str) -> str:
        """Add Merge Assist signature to comment."""
        return f"{message}\n\n---\n*Posted by Merge Assist* 🤖"
    
    async def add_not_ready_comment(
        self,
        project_id: int,
        mr_iid: int,
        reasons: List[str],
        rejection_count: int
    ) -> bool:
        """Add comment explaining why MR is not ready."""
        reasons_text = "\n".join([f"- {reason}" for reason in reasons])
        message = f"""## ⚠️ MR Not Ready for Merge

**Attempt {rejection_count}/3**

This merge request is not ready to be merged. Please address the following issues:

{reasons_text}

Once these issues are resolved, I will automatically attempt to merge again."""
        
        comment = self._format_comment(message)
        return await self.gitlab.add_comment(project_id, mr_iid, comment)
    
    async def add_rejected_comment(
        self,
        project_id: int,
        mr_iid: int,
        reasons: List[str]
    ) -> bool:
        """Add comment when MR is rejected after 3 strikes."""
       message = f"""## ❌ MR Rejected

This merge request has been rejected after 3 attempts due to persistent issues:

{chr(10).join([f'- {r}' for r in reasons])}

**Action Required**: Please fix the issues and reassign this MR to Merge Assist when ready."""
        
        comment = self._format_comment(message)
        return await self.gitlab.add_comment(project_id, mr_iid, comment)
    
    async def add_batch_status_comment(
        self,
        project_id: int,
        mr_iid: int,
        batch_mr_iid: int
    ) -> bool:
        """Add comment about batch merge in progress."""
        message = f"""## 🔄 Batch Merge in Progress

This MR is part of a batch merge operation. 

**Batch MR**: !{batch_mr_iid}

I'm waiting for the batch pipeline to complete. Once successful, this MR will be merged automatically."""
        
        comment = self._format_comment(message)
        return await self.gitlab.add_comment(project_id, mr_iid, comment)
    
    async def add_merge_success_comment(
        self,
        project_id: int,
        mr_iid: int,
        merge_type: str = "single"
    ) -> bool:
        """Add comment after successful merge."""
        if merge_type == "batch":
            message = "## ✅ Successfully Merged (Batch)\n\nThis MR has been merged as part of a batch merge operation."
        else:
            message = "## ✅ Successfully Merged\n\nThis MR has been automatically merged."
        
        comment = self._format_comment(message)
        return await self.gitlab.add_comment(project_id, mr_iid, comment)
    
    async def add_rebase_failed_comment(
        self,
        project_id: int,
        mr_iid: int,
        error_message: str
    ) -> bool:
        """Add comment when rebase fails."""
        message = f"""## ⚠️ Rebase Failed

Automatic rebase with the target branch failed.

**Error**: {error_message}

**Action Required**: Please manually rebase this MR with the target branch and reassign to Merge Assist."""
        
        comment = self._format_comment(message)
        return await self.gitlab.add_comment(project_id, mr_iid, comment)
    
    async def add_error_comment(
        self,
        project_id: int,
        mr_iid: int,
        error_message: str
    ) -> bool:
        """Add comment when an unexpected error occurs."""
        message = f"""## ⚠️ Error Occurred

An error occurred while processing this MR:

```
{error_message}
```

The tool admins have been notified. You can reassign this MR to Merge Assist to retry."""
        
        comment = self._format_comment(message)
        return await self.gitlab.add_comment(project_id, mr_iid, comment)
