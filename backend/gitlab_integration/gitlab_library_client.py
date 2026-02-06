"""
GitLab library client using python-gitlab official library.
Provides fallback and convenience for complex operations.
"""
import gitlab
import logging
from typing import Optional, List,  Dict, Any

logger = logging.getLogger(__name__)


class GitLabLibraryClient:
    """
    GitLab client using the official python-gitlab library.
    Useful as a fallback and for complex operations.
    """
    
    def __init__(self, api_url: str, token: str):
        """
        Initialize GitLab library client.
        
        Args:
            api_url: GitLab URL (e.g., https://gitlab.com)
            token: GitLab private token
        """
        self.gl = gitlab.Gitlab(api_url, private_token=token)
        self.gl.auth()
    
    def get_project(self, project_id: int):
        """Get project object."""
        return self.gl.projects.get(project_id)
    
    def get_merge_requests(self, project_id: int, **kwargs) -> List:
        """Get merge requests for a project."""
        project = self.get_project(project_id)
        return project.mergerequests.list(**kwargs)
    
    def get_merge_request(self, project_id: int, mr_iid: int):
        """Get a specific merge request."""
        project = self.get_project(project_id)
        return project.mergerequests.get(mr_iid)
    
    def rebase_merge_request(self, project_id: int, mr_iid: int) -> bool:
        """Rebase a merge request."""
        try:
            mr = self.get_merge_request(project_id, mr_iid)
            mr.rebase()
            return True
        except gitlab.GitlabError as e:
            logger.error(f"Rebase failed: {e}")
            return False
    
    def merge_merge_request(
        self,
        project_id: int,
        mr_iid: int,
        merge_commit_message: Optional[str] = None,
        should_remove_source_branch: bool = True
    ) -> bool:
        """Merge a merge request."""
        try:
            mr = self.get_merge_request(project_id, mr_iid)
            mr.merge(
                merge_commit_message=merge_commit_message,
                should_remove_source_branch=should_remove_source_branch
            )
            return True
        except gitlab.GitlabError as e:
            logger.error(f"Merge failed: {e}")
            return False
    
    def add_label(self, project_id: int, mr_iid: int, labels: List[str]) -> bool:
        """Add labels to MR."""
        try:
            mr = self.get_merge_request(project_id, mr_iid)
            current_labels = mr.labels
            new_labels = list(set(current_labels + labels))
            mr.labels = new_labels
            mr.save()
            return True
        except gitlab.GitlabError as e:
            logger.error(f"Add label failed: {e}")
            return False
    
    def remove_label(self, project_id: int, mr_iid: int, labels: List[str]) -> bool:
        """Remove labels from MR."""
        try:
            mr = self.get_merge_request(project_id, mr_iid)
            current_labels = mr.labels
            new_labels = [l for l in current_labels if l not in labels]
            mr.labels = new_labels
            mr.save()
            return True
        except gitlab.GitlabError as e:
            logger.error(f"Remove label failed: {e}")
            return False
    
    def add_comment(self, project_id: int, mr_iid: int, comment: str) -> bool:
        """Add comment to MR."""
        try:
            mr = self.get_merge_request(project_id, mr_iid)
            mr.notes.create({'body': comment})
            return True
        except gitlab.GitlabError as e:
            logger.error(f"Add comment failed: {e}")
            return False
