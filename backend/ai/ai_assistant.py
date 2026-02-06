"""
AI Debugging Assistant for Merge Assist.
Uses OpenAI API to provide intelligent insights for merge requests.
"""
import os
import logging
from typing import Dict, Any, List, Optional
import openai
from backend.secrets.secrets_manager import SecretsManager

logger = logging.getLogger(__name__)


class AIDebugAssistant:
    """
    AI-powered debugging assistant for merge requests.
    
    Features:
    - Analyzes merge conflicts and suggests resolutions
    - Reviews pipeline failures and suggests fixes
    - Provides code review insights
    - Recommends optimal batch merge groupings
    - Troubleshoots common GitLab issues
    """
    
    def __init__(self):
        """Initialize AI assistant with OpenAI API."""
        self.secrets_manager = SecretsManager()
        self.secrets_manager.initialize()
        
        # Get OpenAI API key from secrets
        try:
            openai_secret = self.secrets_manager.get_secret('openai/api_key')
            self.api_key = openai_secret.get('api_key')
            openai.api_key = self.api_key
            self.model = "gpt-4"  # Use GPT-4 for better reasoning
            self.enabled = True
        except Exception as e:
            logger.warning(f"OpenAI API key not found, AI assistant disabled: {e}")
            self.enabled = False
    
    async def analyze_merge_conflict(
        self,
        conflict_files: List[str],
        source_branch: str,
        target_branch: str,
        mr_title: str
    ) -> Dict[str, Any]:
        """
        Analyze merge conflicts and suggest resolution strategies.
        
        Args:
            conflict_files: List of conflicting file paths
            source_branch: MR source branch
            target_branch: MR target branch
            mr_title: MR title for context
        
        Returns:
            {
                'analysis': str,
                'suggestions': List[str],
                'severity': 'low'|'medium'|'high',
                'auto_resolvable': bool
            }
        """
        if not self.enabled:
            return self._disabled_response()
        
        try:
            prompt = f"""
You are a GitLab merge conflict expert. Analyze this merge conflict:

MR Title: {mr_title}
Source Branch: {source_branch}
Target Branch: {target_branch}
Conflicting Files: {', '.join(conflict_files)}

Provide:
1. Analysis of what likely caused the conflicts
2. Step-by-step resolution suggestions
3. Severity assessment (low/medium/high)
4. Whether conflicts appear auto-resolvable

Format response as JSON with keys: analysis, suggestions (array), severity, auto_resolvable (boolean).
"""
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert DevOps engineer specializing in Git merge conflicts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent technical advice
                max_tokens=1000
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            logger.info(f"AI analyzed conflict for {len(conflict_files)} files")
            return result
            
        except Exception as e:
            logger.error(f"AI conflict analysis failed: {e}")
            return self._error_response(str(e))
    
    async def analyze_pipeline_failure(
        self,
        pipeline_id: int,
        failed_jobs: List[Dict[str, Any]],
        mr_title: str
    ) -> Dict[str, Any]:
        """
        Analyze pipeline failures and suggest fixes.
        
        Args:
            pipeline_id: GitLab pipeline ID
            failed_jobs: List of failed job details
            mr_title: MR title
        
        Returns:
            {
                'root_cause': str,
                'fix_suggestions': List[str],
                'estimated_fix_time': str,
                'similar_issues': List[str]
            }
        """
        if not self.enabled:
            return self._disabled_response()
        
        try:
            # Extract job details
            job_summaries = []
            for job in failed_jobs:
                job_summaries.append(f"- {job.get('name', 'Unknown')}: {job.get('failure_reason', 'Unknown error')}")
            
            prompt = f"""
You are a CI/CD expert. Analyze this pipeline failure:

MR Title: {mr_title}
Pipeline ID: {pipeline_id}
Failed Jobs:
{chr(10).join(job_summaries)}

Provide:
1. Root cause analysis
2. Step-by-step fix suggestions
3. Estimated time to fix (quick/moderate/complex)
4. Links to similar known issues

Format response as JSON with keys: root_cause, fix_suggestions (array), estimated_fix_time, similar_issues (array).
"""
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert in CI/CD pipelines and debugging build failures."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            logger.info(f"AI analyzed pipeline {pipeline_id} failure")
            return result
            
        except Exception as e:
            logger.error(f"AI pipeline analysis failed: {e}")
            return self._error_response(str(e))
    
    async def suggest_code_review_focus(
        self,
        mr_description: str,
        changed_files: List[str],
        lines_added: int,
        lines_deleted: int
    ) -> Dict[str, Any]:
        """
        Suggest areas to focus on during code review.
        
        Args:
            mr_description: MR description
            changed_files: List of modified file paths
            lines_added: Total lines added
            lines_deleted: Total lines deleted
        
        Returns:
            {
                'focus_areas': List[str],
                'risk_assessment': str,
                'review_time_estimate': str,
                'automated_checks': List[str]
            }
        """
        if not self.enabled:
            return self._disabled_response()
        
        try:
            # Categorize files by type
            file_types = {}
            for file_path in changed_files:
                ext = file_path.split('.')[-1] if '.' in file_path else 'other'
                file_types[ext] = file_types.get(ext, 0) + 1
            
            prompt = f"""
You are a senior code reviewer. Analyze this merge request:

Description: {mr_description}
Changed Files: {len(changed_files)} files
File Types: {', '.join(f"{k}: {v}" for k, v in file_types.items())}
Lines Added: {lines_added}
Lines Deleted: {lines_deleted}

Provide:
1. Key areas reviewers should focus on
2. Risk assessment (low/medium/high)
3. Estimated review time
4. Automated checks that should be added

Format response as JSON with keys: focus_areas (array), risk_assessment, review_time_estimate, automated_checks (array).
"""
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert code reviewer with years of experience in software quality."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            logger.info(f"AI suggested review focus for {len(changed_files)} files")
            return result
            
        except Exception as e:
            logger.error(f"AI review suggestion failed: {e}")
            return self._error_response(str(e))
    
    async def optimize_batch_grouping(
        self,
        ready_mrs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Suggest optimal grouping for batch merge.
        
        Args:
            ready_mrs: List of MRs ready for merge
        
        Returns:
            {
                'recommended_batches': List[List[int]],  # MR IIDs grouped
                'reasoning': str,
                'estimated_success_rate': float
            }
        """
        if not self.enabled:
            return self._disabled_response()
        
        try:
            # Prepare MR summaries
            mr_summaries = []
            for mr in ready_mrs:
                summary = (
                    f"!{mr['iid']}: {mr['title']} "
                    f"(files: {mr.get('changes_count', 0)}, "
                    f"author: {mr.get('author', {}).get('username', 'unknown')})"
                )
                mr_summaries.append(summary)
            
            prompt = f"""
You are a merge optimization expert. Optimize batch grouping for these {len(ready_mrs)} MRs:

{chr(10).join(mr_summaries)}

Provide:
1. Recommended batches (groups of MR IIDs, max 5 per batch)
2. Reasoning for groupings (e.g., similar areas, dependencies, risk)
3. Estimated success rate for each batch

Consider:
- Minimize conflicts between MRs in same batch
- Group related changes together
- Balance batch sizes
- Prioritize high-impact MRs

Format response as JSON with keys: recommended_batches (array of arrays), reasoning, estimated_success_rate.
"""
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert in optimizing CI/CD workflows and merge strategies."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,  # Slightly higher for creative grouping
                max_tokens=1000
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            logger.info(f"AI optimized batching for {len(ready_mrs)} MRs")
            return result
            
        except Exception as e:
            logger.error(f"AI batch optimization failed: {e}")
            return self._error_response(str(e))
    
    async def diagnose_stuck_mr(
        self,
        mr_data: Dict[str, Any],
        status_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Diagnose why an MR is stuck and suggest actions.
        
        Args:
            mr_data: Complete MR data
            status_history: History of status changes
        
        Returns:
            {
                'diagnosis': str,
                'probable_causes': List[str],
                'recommended_actions': List[str],
                'manual_intervention_needed': bool
            }
        """
        if not self.enabled:
            return self._disabled_response()
        
        try:
            # Prepare status timeline
            timeline = []
            for event in status_history[-10:]:  # Last 10 events
                timeline.append(f"{event.get('timestamp', 'unknown')}: {event.get('status', 'unknown')}")
            
            prompt = f"""
You are a DevOps troubleshooting expert. Diagnose this stuck MR:

MR !{mr_data.get('iid', 'unknown')}: {mr_data.get('title', 'Unknown')}
Current Status: {mr_data.get('status', 'unknown')}
Pipeline Status: {mr_data.get('pipeline', {}).get('status', 'unknown')}
Has Conflicts: {mr_data.get('has_conflicts', False)}
WIP: {mr_data.get('work_in_progress', False)}

Status Timeline (recent):
{chr(10).join(timeline)}

Provide:
1. Diagnosis of why MR is stuck
2. Probable root causes
3. Recommended actions to unstuck it
4. Whether manual intervention is needed

Format response as JSON with keys: diagnosis, probable_causes (array), recommended_actions (array), manual_intervention_needed (boolean).
"""
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at diagnosing and resolving merge request issues."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            logger.info(f"AI diagnosed stuck MR !{mr_data.get('iid', 'unknown')}")
            return result
            
        except Exception as e:
            logger.error(f"AI diagnosis failed: {e}")
            return self._error_response(str(e))
    
    def _disabled_response(self) -> Dict[str, Any]:
        """Return response when AI is disabled."""
        return {
            'enabled': False,
            'message': 'AI assistant is not enabled. Configure OpenAI API key in secrets manager.'
        }
    
    def _error_response(self, error: str) -> Dict[str, Any]:
        """Return error response."""
        return {
            'error': True,
            'message': f'AI assistant encountered an error: {error}',
            'fallback_advice': 'Please review manually or consult documentation.'
        }
    
    async def generate_merge_summary(
        self,
        merged_mrs: List[Dict[str, Any]],
        target_branch: str
    ) -> str:
        """
        Generate a human-readable summary of merged MRs.
        
        Args:
            merged_mrs: List of merged MR data
            target_branch: Target branch name
        
        Returns:
            Formatted summary text
        """
        if not self.enabled:
            return "AI summary not available. AI assistant is disabled."
        
        try:
            mr_list = []
            for mr in merged_mrs:
                mr_list.append(f"- !{mr['iid']}: {mr['title']} by @{mr.get('author', {}).get('username', 'unknown')}")
            
            prompt = f"""
Generate a concise, professional summary for this batch merge into {target_branch}:

Merged MRs:
{chr(10).join(mr_list)}

Create a summary that:
1. Highlights key features/fixes
2. Groups related changes
3. Notes any breaking changes
4. Is suitable for release notes or team notifications

Keep it under 200 words.
"""
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a technical writer creating release notes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=400
            )
            
            summary = response.choices[0].message.content.strip()
            
            logger.info(f"AI generated merge summary for {len(merged_mrs)} MRs")
            return summary
            
        except Exception as e:
            logger.error(f"AI summary generation failed: {e}")
            return f"Merged {len(merged_mrs)} MRs into {target_branch}. AI summary unavailable."


# Singleton instance
_ai_assistant = None


def get_ai_assistant() -> AIDebugAssistant:
    """Get singleton AI assistant instance."""
    global _ai_assistant
    if _ai_assistant is None:
        _ai_assistant = AIDebugAssistant()
    return _ai_assistant
