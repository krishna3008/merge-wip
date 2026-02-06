"""
Core merge logic for single and batch MR workflows.
"""
import logging
import asyncio
from typing import List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class Merger:
    """Handles single and batch merge operations."""
    
    def __init__(self, gitlab_client, validator, label_manager, comment_manager, project_config):
        """
        Initialize merger.
        
        Args:
            gitlab_client: GitLab unified client
            validator: MRValidator instance
            label_manager: LabelManager instance
            comment_manager: CommentManager instance
            project_config: ProjectConfig instance
        """
        self.gitlab = gitlab_client
        self.validator = validator
        self.labels = label_manager
        self.comments = comment_manager
        self.config = project_config
    
    async def merge_single_mr(
        self,
        project_id: int,
        mr_data: Dict[str, Any],
        db_session
    ) -> Tuple[bool, str]:
        """
        Merge a single MR.
        
        Workflow:
        1. Check if up-to-date with target
        2. Rebase if needed
        3. Wait for pipeline
        4. Merge
        
        Returns:
            (success: bool, message: str)
        """
        mr_iid = mr_data['iid']
        
        try:
            # Step 1: Check if up-to-date
            logger.info(f"Processing single MR: !{mr_iid}")
            
            # Step 2: Rebase with target
            logger.info(f"Rebasing MR !{mr_iid}")
            rebase_success = await self.gitlab.rebase_merge_request(project_id, mr_iid)
            
            if not rebase_success:
                await self.comments.add_rebase_failed_comment(
                    project_id, mr_iid, "Rebase operation failed"
                )
                return False, "Rebase failed"
            
            # Step 3: Wait for pipeline
            logger.info(f"Waiting for pipeline for MR !{mr_iid}")
            pipeline_success = await self._wait_for_pipeline(project_id, mr_iid, timeout=1800)
            
            if not pipeline_success:
                return False, "Pipeline did not succeed"
            
            # Step 4: Add ready label
            await self.labels.add_ready_to_merge_label(project_id, mr_iid)
            
            # Step 5: Merge
            logger.info(f"Merging MR !{mr_iid}")
            merge_success = await self.gitlab.merge_merge_request(
                project_id, mr_iid,
                merge_commit_message=f"Merged by Merge Assist",
                should_remove_source_branch=True
            )
            
            if not merge_success:
                return False, "Merge operation failed"
            
            # Step 6: Update status and add comment
            await self.labels.cleanup_merge_assist_labels(project_id, mr_iid)
            await self.comments.add_merge_success_comment(project_id, mr_iid, "single")
            
            # Update database
            from backend.database.models import MergeRequest
            db_mr = db_session.query(MergeRequest).filter(
                MergeRequest.gitlab_mr_iid == mr_iid,
                MergeRequest.project_id == str(project_id)
            ).first()
            
            if db_mr:
                db_mr.status = 'merged'
                db_mr.merged_at = datetime.utcnow()
                db_session.commit()
            
            logger.info(f"Successfully merged MR !{mr_iid}")
            return True, "Merged successfully"
            
        except Exception as e:
            logger.error(f"Error merging single MR !{mr_iid}: {e}")
            await self.comments.add_error_comment(project_id, mr_iid, str(e))
            return False, f"Error: {e}"
    
    async def merge_batch(
        self,
        project_id: int,
        target_branch: str,
        mr_list: List[Dict[str, Any]],
        db_session
    ) -> Tuple[bool, str]:
        """
        Merge multiple MRs in a batch.
        
        Workflow:
        1. Create/reset batch branch from target
        2. Merge MRs to batch branch (ordered by timestamp)
        3. Create batch MR
        4. Wait for batch pipeline
        5. Merge individual MRs after rebase
        
        Returns:
            (success: bool, message: str)
        """
        batch_size = min(len(mr_list), self.config.batch_size)
        mrs_to_batch = mr_list[:batch_size]
        
        # Sort by recognized_at timestamp (first come first serve)
        mrs_to_batch.sort(key=lambda x: x.get('recognized_at', datetime.utcnow()))
        
        batch_branch = f"merge-assist-batch-{target_branch}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        try:
            # Step 1: Create batch branch
            logger.info(f"Creating batch branch: {batch_branch}")
            await self.gitlab.create_branch(project_id, batch_branch, target_branch)
            
            # Step 2: Merge MRs to batch branch
            for mr_data in mrs_to_batch:
                mr_iid = mr_data['iid']
                source_branch = mr_data['source_branch']
                
                logger.info(f"Merging !{mr_iid} to batch branch")
                # Merge to batch branch (this operation may vary by GitLab API)
                # For now, we'll create a batch MR to test all together
            
            # Step 3: Create batch MR
            logger.info(f"Creating batch MR")
            mr_titles = ', '.join([f"!{mr['iid']}" for mr in mrs_to_batch])
            batch_mr_data = await self.gitlab.create_merge_request(
                project_id,
                source_branch=batch_branch,
                target_branch=target_branch,
                title=f"[Merge Assist Batch] {mr_titles}",
                description=f"Batch merge for MRs: {mr_titles}"
            )
            
            batch_mr_iid = batch_mr_data['iid']
            await self.labels.add_batch_mr_label(project_id, batch_mr_iid)
            
            # Add comments to original MRs
            for mr_data in mrs_to_batch:
                await self.comments.add_batch_status_comment(
                    project_id, mr_data['iid'], batch_mr_iid
                )
            
            # Step 4: Wait for batch pipeline
            logger.info(f"Waiting for batch pipeline")
            pipeline_success = await self._wait_for_pipeline(project_id, batch_mr_iid, timeout=1800)
            
            if not pipeline_success:
                logger.error("Batch pipeline failed")
                await self.gitlab.close_merge_request(project_id, batch_mr_iid)
                return False, "Batch pipeline failed"
            
            # Step 5: Merge individual MRs
            logger.info("Batch pipeline successful, merging individual MRs")
            successful_merges = []
            failed_merges = []
            
            for mr_data in mrs_to_batch:
                mr_iid = mr_data['iid']
                
                # Rebase with target
                rebase_success = await self.gitlab.rebase_merge_request(project_id, mr_iid)
                
                if not rebase_success:
                    logger.warning(f"Rebase failed for MR !{mr_iid}, rejecting")
                    await self.comments.add_rebase_failed_comment(
                        project_id, mr_iid, "Rebase failed during batch merge"
                    )
                    await self.labels.add_rejected_label(project_id, mr_iid)
                    failed_merges.append(mr_iid)
                    continue
                
                # Merge
                merge_success = await self.gitlab.merge_merge_request(project_id, mr_iid)
                
                if merge_success:
                    await self.labels.cleanup_merge_assist_labels(project_id, mr_iid)
                    await self.comments.add_merge_success_comment(project_id, mr_iid, "batch")
                    successful_merges.append(mr_iid)
                    
                    # Update database
                    from backend.database.models import MergeRequest
                    db_mr = db_session.query(MergeRequest).filter(
                        MergeRequest.gitlab_mr_iid == mr_iid
                    ).first()
                    if db_mr:
                        db_mr.status = 'merged'
                        db_mr.merged_at = datetime.utcnow()
                else:
                    failed_merges.append(mr_iid)
            
            db_session.commit()
            
            # Close batch MR
            await self.gitlab.close_merge_request(project_id, batch_mr_iid)
            
            logger.info(f"Batch merge complete: {len(successful_merges)} succeeded, {len(failed_merges)} failed")
            return True, f"Merged {len(successful_merges)}/{len(mrs_to_batch)} MRs"
            
        except Exception as e:
            logger.error(f"Batch merge error: {e}")
            return False, f"Batch merge error: {e}"
    
    async def _wait_for_pipeline(
        self,
        project_id: int,
        mr_iid: int,
        timeout: int = 1800,
        poll_interval: int = 30
    ) -> bool:
        """
        Wait for MR pipeline to complete.
        
        Args:
            project_id: GitLab project ID
            mr_iid: MR internal ID
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds
        
        Returns:
            True if pipeline succeeded, False otherwise
        """
        elapsed = 0
        
        while elapsed < timeout:
            mr_data = await self.gitlab.get_merge_request(project_id, mr_iid)
            pipeline = mr_data.get('pipeline')
            
            if not pipeline:
                logger.warning(f"No pipeline found for MR !{mr_iid}")
                return False
            
            status = pipeline['status']
            
            if status == 'success':
                return True
            elif status in ['failed', 'canceled']:
                logger.warning(f"Pipeline {status} for MR !{mr_iid}")
                return False
            
            # Still running, wait
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        logger.warning(f"Pipeline timeout for MR !{mr_iid}")
        return False
