"""
Unified GitLab client facade providing both custom and library-based approaches.
"""
import logging
from typing import Optional, List, Dict, Any

from .gitlab_custom_client import GitLabCustomClient
from .gitlab_library_client import GitLabLibraryClient

logger = logging.getLogger(__name__)


class GitLabUnified:
    """
    Unified GitLab client with automatic fallback between custom and library clients.
    Provides DRY interface for all GitLab operations.
    """
    
    def __init__(self, api_url: str, token: str):
        """
        Initialize unified GitLab client.
        
        Args:
            api_url: GitLab API URL
            token: GitLab private token
        """
        self.custom = GitLabCustomClient(api_url, token)
        self.library = GitLabLibraryClient(api_url, token)
    
    async def get_merge_requests(
        self,
        project_id: int,
        state: str = "opened",
        assignee_id: Optional[int] = None,
        reviewer_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get merge requests with custom client."""
        try:
            return await self.custom.get_merge_requests(project_id, state, assignee_id, reviewer_id)
        except Exception as e:
            logger.warning(f"Custom client failed, using library client: {e}")
            mrs = self.library.get_merge_requests(
                project_id,
                state=state,
                assignee_id=assignee_id,
                reviewer_id=reviewer_id
            )
            return [mr.asdict() for mr in mrs]
    
    async def get_merge_request(self, project_id: int, mr_iid: int) -> Dict[str, Any]:
        """Get specific MR with custom client."""
        try:
            return await self.custom.get_merge_request(project_id, mr_iid)
        except Exception as e:
            logger.warning(f"Custom client failed, using library client: {e}")
            mr = self.library.get_merge_request(project_id, mr_iid)
            return mr.asdict()
    
    async def rebase_merge_request(self, project_id: int, mr_iid: int) -> bool:
        """Rebase MR."""
        try:
            await self.custom.rebase_merge_request(project_id, mr_iid)
            return True
        except Exception as e:
            logger.warning(f"Custom client rebase failed, using library client: {e}")
            return self.library.rebase_merge_request(project_id, mr_iid)
    
    async def merge_merge_request(
        self,
        project_id: int,
        mr_iid: int,
        merge_commit_message: Optional[str] = None,
        should_remove_source_branch: bool = True
    ) -> bool:
        """Merge MR."""
        try:
            await self.custom.merge_merge_request(
                project_id, mr_iid, merge_commit_message, should_remove_source_branch
            )
            return True
        except Exception as e:
            logger.warning(f"Custom client merge failed, using library client: {e}")
            return self.library.merge_merge_request(
                project_id, mr_iid, merge_commit_message, should_remove_source_branch
            )
    
    async def add_label(self, project_id: int, mr_iid: int, labels: List[str]) -> bool:
        """Add labels to MR."""
        try:
            await self.custom.add_label(project_id, mr_iid, labels)
            return True
        except Exception as e:
            logger.warning(f"Custom client add_label failed, using library client: {e}")
            return self.library.add_label(project_id, mr_iid, labels)
    
    async def remove_label(self, project_id: int, mr_iid: int, labels: List[str]) -> bool:
        """Remove labels from MR."""
        try:
            await self.custom.remove_label(project_id, mr_iid, labels)
            return True
        except Exception as e:
            logger.warning(f"Custom client remove_label failed, using library client: {e}")
            return self.library.remove_label(project_id, mr_iid, labels)
    
    async def add_comment(self, project_id: int, mr_iid: int, comment: str) -> bool:
        """Add comment to MR."""
        try:
            await self.custom.add_comment(project_id, mr_iid, comment)
            return True
        except Exception as e:
            logger.warning(f"Custom client add_comment failed, using library client: {e}")
            return self.library.add_comment(project_id, mr_iid, comment)
    
    async def get_pipeline_status(self, project_id: int, pipeline_id: int) -> Dict[str, Any]:
        """Get pipeline status."""
        return await self.custom.get_pipeline_status(project_id, pipeline_id)
    
    async def create_branch(self, project_id: int, branch_name: str, ref: str) -> Dict[str, Any]:
        """Create a new branch."""
        return await self.custom.create_branch(project_id, branch_name, ref)
    
    async def delete_branch(self, project_id: int, branch_name: str):
        """Delete a branch."""
        await self.custom.delete_branch(project_id, branch_name)
    
    async def create_merge_request(
        self,
        project_id: int,
        source_branch: str,
        target_branch: str,
        title: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new MR."""
        return await self.custom.create_merge_request(
            project_id, source_branch, target_branch, title, description
        )
    
    async def close_merge_request(self, project_id: int, mr_iid: int) -> Dict[str, Any]:
        """Close an MR."""
        return await self.custom.close_merge_request(project_id, mr_iid)
    
    async def close(self):
        """Close all client connections."""
        await self.custom.close()
