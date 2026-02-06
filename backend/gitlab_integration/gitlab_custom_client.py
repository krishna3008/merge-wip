"""
Custom GitLab API client using aiohttp for fine-grained control.
"""
import aiohttp
import asyncio
import logging
from typing import Optional, List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

from .gitlab_models import GitLabMergeRequest, GitLabPipeline, GitLabProject

logger = logging.getLogger(__name__)


class GitLabCustomClient:
    """
    Custom GitLab API client with retry logic and rate limiting.
    Uses direct HTTP requests for maximum control.
    """
    
    def __init__(self, api_url: str, token: str, timeout: int = 30):
        """
        Initialize GitLab custom client.
        
        Args:
            api_url: GitLab API URL (e.g., https://gitlab.com/api/v4)
            token: GitLab private token
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip('/')
        if not self.api_url.endswith('/api/v4'):
            self.api_url = f"{self.api_url}/api/v4"
        
        self.headers = {
            'PRIVATE-TOKEN': token,
            'Content-Type': 'application/json'
        }
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=self.timeout
            )
        return self.session
    
    async def close(self):
        """Close aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint
            **kwargs: Additional arguments for aiohttp request
        
        Returns:
            Response JSON data
        """
        session = await self._get_session()
        url = f"{self.api_url}{endpoint}"
        
        try:
            async with session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"GitLab API request failed: {method} {url} - {e}")
            raise
    
    async def get_merge_requests(
        self,
        project_id: int,
        state: str = "opened",
        assignee_id: Optional[int] = None,
        reviewer_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get merge requests for a project.
        
        Args:
            project_id: GitLab project ID
            state: MR state filter (opened, closed, merged, all)
            assignee_id: Filter by assignee user ID
            reviewer_id: Filter by reviewer user ID
        
        Returns:
            List of MR dictionaries
        """
        params = {"state": state}
        if assignee_id:
            params["assignee_id"] = assignee_id
        if reviewer_id:
            params["reviewer_id"] = reviewer_id
        
        endpoint = f"/projects/{project_id}/merge_requests"
        return await self._request("GET", endpoint, params=params)
    
    async def get_merge_request(
        self,
        project_id: int,
        mr_iid: int
    ) -> Dict[str, Any]:
        """Get a specific merge request."""
        endpoint = f"/projects/{project_id}/merge_requests/{mr_iid}"
        return await self._request("GET", endpoint)
    
    async def get_pipeline_status(
        self,
        project_id: int,
        pipeline_id: int
    ) -> Dict[str, Any]:
        """Get pipeline status."""
        endpoint = f"/projects/{project_id}/pipelines/{pipeline_id}"
        return await self._request("GET", endpoint)
    
    async def rebase_merge_request(
        self,
        project_id: int,
        mr_iid: int
    ) -> Dict[str, Any]:
        """
        Rebase a merge request.
        
        Args:
            project_id: GitLab project ID
            mr_iid: MR internal ID
        
        Returns:
            Response data
        """
        endpoint = f"/projects/{project_id}/merge_requests/{mr_iid}/rebase"
        return await self._request("PUT", endpoint)
    
    async def merge_merge_request(
        self,
        project_id: int,
        mr_iid: int,
        merge_commit_message: Optional[str] = None,
        should_remove_source_branch: bool = True
    ) -> Dict[str, Any]:
        """
        Merge a merge request.
        
        Args:
            project_id: GitLab project ID
            mr_iid: MR internal ID
            merge_commit_message: Custom merge commit message
            should_remove_source_branch: Remove source branch after merge
        
        Returns:
            Merged MR data
        """
        endpoint = f"/projects/{project_id}/merge_requests/{mr_iid}/merge"
        data = {
            "should_remove_source_branch": should_remove_source_branch
        }
        if merge_commit_message:
            data["merge_commit_message"] = merge_commit_message
        
        return await self._request("PUT", endpoint, json=data)
    
    async def add_label(
        self,
        project_id: int,
        mr_iid: int,
        labels: List[str]
    ) -> Dict[str, Any]:
        """
        Add labels to a merge request.
        
        Args:
            project_id: GitLab project ID
            mr_iid: MR internal ID
            labels: List of label names to add
        
        Returns:
            Updated MR data
        """
        endpoint = f"/projects/{project_id}/merge_requests/{mr_iid}"
        data = {"add_labels": ",".join(labels)}
        return await self._request("PUT", endpoint, json=data)
    
    async def remove_label(
        self,
        project_id: int,
        mr_iid: int,
        labels: List[str]
    ) -> Dict[str, Any]:
        """Remove labels from a merge request."""
        endpoint = f"/projects/{project_id}/merge_requests/{mr_iid}"
        data = {"remove_labels": ",".join(labels)}
        return await self._request("PUT", endpoint, json=data)
    
    async def add_comment(
        self,
        project_id: int,
        mr_iid: int,
        comment: str
    ) -> Dict[str, Any]:
        """
        Add a comment to a merge request.
        
        Args:
            project_id: GitLab project ID
            mr_iid: MR internal ID
            comment: Comment text
        
        Returns:
            Created comment data
        """
        endpoint = f"/projects/{project_id}/merge_requests/{mr_iid}/notes"
        data = {"body": comment}
        return await self._request("POST", endpoint, json=data)
    
    async def get_project(self, project_id: int) -> Dict[str, Any]:
        """Get project information."""
        endpoint = f"/projects/{project_id}"
        return await self._request("GET", endpoint)
    
    async def create_branch(
        self,
        project_id: int,
        branch_name: str,
        ref: str
    ) -> Dict[str, Any]:
        """
        Create a new branch.
        
        Args:
            project_id: GitLab project ID
            branch_name: Name of new branch
            ref: Reference to create branch from (branch name, commit SHA)
        
        Returns:
            Created branch data
        """
        endpoint = f"/projects/{project_id}/repository/branches"
        data = {"branch": branch_name, "ref": ref}
        return await self._request("POST", endpoint, json=data)
    
    async def delete_branch(
        self,
        project_id: int,
        branch_name: str
    ) -> None:
        """Delete a branch."""
        endpoint = f"/projects/{project_id}/repository/branches/{branch_name}"
        await self._request("DELETE", endpoint)
    
    async def create_merge_request(
        self,
        project_id: int,
        source_branch: str,
        target_branch: str,
        title: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new merge request.
        
        Args:
            project_id: GitLab project ID
            source_branch: Source branch name
            target_branch: Target branch name
            title: MR title
            description: MR description
        
        Returns:
            Created MR data
        """
        endpoint = f"/projects/{project_id}/merge_requests"
        data = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title
        }
        if description:
            data["description"] = description
        
        return await self._request("POST", endpoint, json=data)
    
    async def close_merge_request(
        self,
        project_id: int,
        mr_iid: int
    ) -> Dict[str, Any]:
        """Close a merge request."""
        endpoint = f"/projects/{project_id}/merge_requests/{mr_iid}"
        data = {"state_event": "close"}
        return await self._request("PUT", endpoint, json=data)
