"""
Integration of AI Assistant into Worker POD.
Enhances worker with intelligent insights.
"""
from backend.ai.ai_assistant import get_ai_assistant
import logging

logger = logging.getLogger(__name__)


class AIEnhancedWorker:
    """
    Worker POD enhanced with AI capabilities.
    
    Integrates AI assistant for:
    - Conflict analysis before rebase
    - Pipeline failure diagnosis
    - Batch optimization
    - Stuck MR troubleshooting
    """
    
    def __init__(self, worker_pod):
        """
        Wrap existing Worker POD with AI capabilities.
        
        Args:
            worker_pod: Original Worker POD instance
        """
        self.worker = worker_pod
        self.ai = get_ai_assistant()
    
    async def process_mr_with_ai_insights(self, mr_data: dict, db_session):
        """
        Process MR with AI-powered insights.
        
        Args:
            mr_data: MR data from GitLab
            db_session: Database session
        """
        mr_iid = mr_data['iid']
        
        # Check if MR has conflicts
        if mr_data.get('has_conflicts', False):
            logger.info(f"MR !{mr_iid} has conflicts, requesting AI analysis...")
            
            conflict_files = mr_data.get('conflicted_files', [])
            if self.ai.enabled:
                analysis = await self.ai.analyze_merge_conflict(
                    conflict_files=conflict_files,
                    source_branch=mr_data['source_branch'],
                    target_branch=mr_data['target_branch'],
                    mr_title=mr_data['title']
                )
                
                # Add AI insights as comment
                if not analysis.get('error'):
                    comment = self._format_conflict_analysis(analysis)
                    await self.worker.comment_manager.add_comment(
                        self.worker.project_id,
                        mr_iid,
                        comment
                    )
                    logger.info(f"Added AI conflict analysis to MR !{mr_iid}")
        
        # Continue with normal processing
        return await self.worker.process_mr(mr_data, db_session)
    
    async def handle_pipeline_failure_with_ai(
        self,
        mr_data: dict,
        pipeline_data: dict
    ):
        """
        Handle pipeline failure with AI diagnosis.
        
        Args:
            mr_data: MR data
            pipeline_data: Failed pipeline data
        """
        mr_iid = mr_data['iid']
        pipeline_id = pipeline_data['id']
        
        logger.info(f"Pipeline {pipeline_id} failed for MR !{mr_iid}, requesting AI diagnosis...")
        
        if self.ai.enabled:
            # Get failed jobs
            failed_jobs = [
                job for job in pipeline_data.get('jobs', [])
                if job.get('status') == 'failed'
            ]
            
            diagnosis = await self.ai.analyze_pipeline_failure(
                pipeline_id=pipeline_id,
                failed_jobs=failed_jobs,
                mr_title=mr_data['title']
            )
            
            if not diagnosis.get('error'):
                comment = self._format_pipeline_diagnosis(diagnosis, pipeline_id)
                await self.worker.comment_manager.add_comment(
                    self.worker.project_id,
                    mr_iid,
                    comment
                )
                logger.info(f"Added AI pipeline diagnosis to MR !{mr_iid}")
    
    async def optimize_batch_selection(self, ready_mrs: list) -> list:
        """
        Use AI to optimize batch selection.
        
        Args:
            ready_mrs: List of MRs ready for merge
        
        Returns:
            Optimized list of MR groups
        """
        if not self.ai.enabled or len(ready_mrs) < 3:
            # Fall back to simple grouping
            return [ready_mrs[:5]]  # Default: first 5
        
        logger.info(f"Requesting AI batch optimization for {len(ready_mrs)} MRs...")
        
        optimization = await self.ai.optimize_batch_grouping(ready_mrs)
        
        if optimization.get('error'):
            # Fallback to default
            return [ready_mrs[:5]]
        
        batches = optimization.get('recommended_batches', [])
        logger.info(f"AI recommended {len(batches)} batches: {batches}")
        
        # Convert IIDs to MR objects
        optimized_batches = []
        for batch_iids in batches:
            batch_mrs = [mr for mr in ready_mrs if mr['iid'] in batch_iids]
            optimized_batches.append(batch_mrs)
        
        return optimized_batches
    
    async def diagnose_stuck_mr(self, mr_data: dict, db_session):
        """
        Diagnose why MR is stuck using AI.
        
        Args:
            mr_data: MR data
            db_session: Database session
        """
        from backend.database.models import MRLog
        
        mr_iid = mr_data['iid']
        
        # Get status history from database
        status_history = db_session.query(MRLog).filter(
            MRLog.mr_id == str(mr_data['id'])
        ).order_by(MRLog.created_at.desc()).limit(20).all()
        
        history_data = [
            {
                'timestamp': log.created_at.isoformat(),
                'status': log.event_type,
                'message': log.message
            }
            for log in status_history
        ]
        
        if self.ai.enabled:
            logger.info(f"Diagnosing stuck MR !{mr_iid} with AI...")
            
            diagnosis = await self.ai.diagnose_stuck_mr(
                mr_data=mr_data,
                status_history=history_data
            )
            
            if not diagnosis.get('error'):
                comment = self._format_diagnostic_report(diagnosis)
                await self.worker.comment_manager.add_comment(
                    self.worker.project_id,
                    mr_iid,
                    comment
                )
                logger.info(f"Added AI diagnosis to stuck MR !{mr_iid}")
                
                return diagnosis
        
        return None
    
    async def generate_batch_summary(
        self,
        merged_mrs: list,
        target_branch: str
    ) -> str:
        """
        Generate AI summary of batch merge.
        
        Args:
            merged_mrs: List of merged MRs
            target_branch: Target branch
        
        Returns:
            Summary text
        """
        if self.ai.enabled:
            return await self.ai.generate_merge_summary(merged_mrs, target_branch)
        else:
            # Simple fallback
            return f"Merged {len(merged_mrs)} MRs into {target_branch}"
    
    def _format_conflict_analysis(self, analysis: dict) -> str:
        """Format AI conflict analysis as comment."""
        severity_emoji = {
            'low': '🟢',
            'medium': '🟡',
            'high': '🔴'
        }
        
        emoji = severity_emoji.get(analysis.get('severity', 'medium'), '🟡')
        
        comment = f"""
## {emoji} AI Conflict Analysis

**Severity:** {analysis.get('severity', 'medium').upper()}

### Analysis
{analysis.get('analysis', 'No analysis available')}

### Suggested Resolution Steps
"""
        for i, suggestion in enumerate(analysis.get('suggestions', []), 1):
            comment += f"{i}. {suggestion}\n"
        
        if analysis.get('auto_resolvable', False):
            comment += "\n✅ **Note:** These conflicts may be auto-resolvable.\n"
        else:
            comment += "\n⚠️ **Note:** Manual resolution required.\n"
        
        comment += "\n*This analysis was generated by Merge Assist AI.*"
        
        return comment
    
    def _format_pipeline_diagnosis(self, diagnosis: dict, pipeline_id: int) -> str:
        """Format AI pipeline diagnosis as comment."""
        comment = f"""
## 🔍 AI Pipeline Failure Diagnosis

**Pipeline ID:** {pipeline_id}

### Root Cause
{diagnosis.get('root_cause', 'Unable to determine')}

### Suggested Fixes
"""
        for i, fix in enumerate(diagnosis.get('fix_suggestions', []), 1):
            comment += f"{i}. {fix}\n"
        
        comment += f"\n**Estimated Fix Time:** {diagnosis.get('estimated_fix_time', 'Unknown')}\n"
        
        similar_issues = diagnosis.get('similar_issues', [])
        if similar_issues:
            comment += "\n### Related Issues\n"
            for issue in similar_issues:
                comment += f"- {issue}\n"
        
        comment += "\n*This diagnosis was generated by Merge Assist AI.*"
        
        return comment
    
    def _format_diagnostic_report(self, diagnosis: dict) -> str:
        """Format stuck MR diagnostic report."""
        comment = f"""
## 🔧 AI Diagnostic Report: Stuck MR

### Diagnosis
{diagnosis.get('diagnosis', 'Unable to diagnose')}

### Probable Causes
"""
        for i, cause in enumerate(diagnosis.get('probable_causes', []), 1):
            comment += f"{i}. {cause}\n"
        
        comment += "\n### Recommended Actions\n"
        for i, action in enumerate(diagnosis.get('recommended_actions', []), 1):
            comment += f"{i}. {action}\n"
        
        if diagnosis.get('manual_intervention_needed', False):
            comment += "\n⚠️ **Manual intervention required**\n"
        else:
            comment += "\n✅ **May be resolvable automatically**\n"
        
        comment += "\n*This diagnostic was generated by Merge Assist AI.*"
        
        return comment


def enhance_worker_with_ai(worker_pod):
    """
    Enhance an existing Worker POD with AI capabilities.
    
    Args:
        worker_pod: Original Worker POD instance
    
    Returns:
        AIEnhancedWorker instance
    """
    return AIEnhancedWorker(worker_pod)
