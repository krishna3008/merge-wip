"""
Tests for AI Debugging Assistant.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from backend.ai.ai_assistant import AIDebugAssistant, get_ai_assistant


@pytest.fixture
def mock_openai():
    """Mock OpenAI API responses."""
    with patch('backend.ai.ai_assistant.openai') as mock:
        yield mock


@pytest.fixture
def ai_assistant(mock_openai):
    """Create AI assistant with mocked OpenAI."""
    with patch('backend.ai.ai_assistant.SecretsManager') as mock_secrets:
        # Mock secrets manager to return API key
        mock_instance = Mock()
        mock_instance.get_secret.return_value = {'api_key': 'test-key'}
        mock_secrets.return_value = mock_instance
        
        assistant = AIDebugAssistant()
        return assistant


class TestAIDebugAssistant:
    """Test AI debugging assistant features."""
    
    @pytest.mark.asyncio
    async def test_analyze_merge_conflict(self, ai_assistant, mock_openai):
        """Test AI conflict analysis."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '''{
            "analysis": "Conflicts in database models suggest parallel feature development",
            "suggestions": [
                "Review both changes carefully",
                "Merge manually with care",
                "Test thoroughly after resolution"
            ],
            "severity": "medium",
            "auto_resolvable": false
        }'''
        mock_openai.ChatCompletion.create = AsyncMock(return_value=mock_response)
        
        # Test
        result = await ai_assistant.analyze_merge_conflict(
            conflict_files=['backend/database/models.py', 'backend/api/routes.py'],
            source_branch='feature-new-model',
            target_branch='main',
            mr_title='Add new database model'
        )
        
        # Verify
        assert 'analysis' in result
        assert 'suggestions' in result
        assert result['severity'] == 'medium'
        assert result['auto_resolvable'] is False
        assert len(result['suggestions']) == 3
    
    @pytest.mark.asyncio
    async def test_analyze_pipeline_failure(self, ai_assistant, mock_openai):
        """Test pipeline failure analysis."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '''{
            "root_cause": "Test failure in authentication module",
            "fix_suggestions": [
                "Update test fixtures",
                "Check environment variables",
                "Verify database migrations"
            ],
            "estimated_fix_time": "quick",
            "similar_issues": [
                "Issue #123: Similar test failure",
                "Stack Overflow: Common pytest issue"
            ]
        }'''
        mock_openai.ChatCompletion.create = AsyncMock(return_value=mock_response)
        
        # Test
        failed_jobs = [
            {'name': 'test:integration', 'failure_reason': 'Test failed'},
            {'name': 'test:unit', 'failure_reason': 'AssertionError'}
        ]
        
        result = await ai_assistant.analyze_pipeline_failure(
            pipeline_id=12345,
            failed_jobs=failed_jobs,
            mr_title='Update authentication'
        )
        
        # Verify
        assert 'root_cause' in result
        assert 'fix_suggestions' in result
        assert result['estimated_fix_time'] == 'quick'
        assert len(result['similar_issues']) == 2
    
    @pytest.mark.asyncio
    async def test_optimize_batch_grouping(self, ai_assistant, mock_openai):
        """Test batch optimization."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '''{
            "recommended_batches": [[1, 2, 3], [4, 5]],
            "reasoning": "First batch: Related API changes. Second batch: Database migrations",
            "estimated_success_rate": 0.95
        }'''
        mock_openai.ChatCompletion.create = AsyncMock(return_value=mock_response)
        
        # Test
        ready_mrs = [
            {'iid': 1, 'title': 'API: Add endpoint', 'changes_count': 5, 'author': {'username': 'dev1'}},
            {'iid': 2, 'title': 'API: Update route', 'changes_count': 3, 'author': {'username': 'dev2'}},
            {'iid': 3, 'title': 'API: Fix bug', 'changes_count': 2, 'author': {'username': 'dev1'}},
            {'iid': 4, 'title': 'DB: Migration', 'changes_count': 10, 'author': {'username': 'dev3'}},
            {'iid': 5, 'title': 'DB: Schema update', 'changes_count': 8, 'author': {'username': 'dev3'}}
        ]
        
        result = await ai_assistant.optimize_batch_grouping(ready_mrs)
        
        # Verify
        assert 'recommended_batches' in result
        assert len(result['recommended_batches']) == 2
        assert result['recommended_batches'][0] == [1, 2, 3]
        assert result['estimated_success_rate'] == 0.95
    
    @pytest.mark.asyncio
    async def test_diagnose_stuck_mr(self, ai_assistant, mock_openai):
        """Test stuck MR diagnosis."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '''{
            "diagnosis": "MR is stuck due to failed pipeline that was not retriggered",
            "probable_causes": [
                "Pipeline failed due to transient error",
                "No automatic retry configured",
                "Waiting for manual intervention"
            ],
            "recommended_actions": [
                "Retrigger the pipeline",
                "Check pipeline logs",
                "Verify pipeline configuration"
            ],
            "manual_intervention_needed": true
        }'''
        mock_openai.ChatCompletion.create = AsyncMock(return_value=mock_response)
        
        # Test
        mr_data = {
            'iid': 123,
            'title': 'Feature: New component',
            'status': 'ready',
            'pipeline': {'status': 'failed'},
            'has_conflicts': False,
            'work_in_progress': False
        }
        
        status_history = [
            {'timestamp': '2024-01-15T10:00:00', 'status': 'recognized'},
            {'timestamp': '2024-01-15T10:05:00', 'status': 'ready'},
            {'timestamp': '2024-01-15T10:10:00', 'status': 'ready'}  # Stuck
        ]
        
        result = await ai_assistant.diagnose_stuck_mr(mr_data, status_history)
        
        # Verify
        assert 'diagnosis' in result
        assert 'probable_causes' in result
        assert 'recommended_actions' in result
        assert result['manual_intervention_needed'] is True
        assert len(result['probable_causes']) == 3
    
    @pytest.mark.asyncio
    async def test_generate_merge_summary(self, ai_assistant, mock_openai):
        """Test merge summary generation."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = """
Merged 3 features into main branch:

**New Features:**
- Authentication improvements (!101)
- Database schema updates (!102)

**Bug Fixes:**
- Fixed login issue (!103)

All changes tested and verified.
"""
        mock_openai.ChatCompletion.create = AsyncMock(return_value=mock_response)
        
        # Test
        merged_mrs = [
            {'iid': 101, 'title': 'Auth improvements', 'author': {'username': 'dev1'}},
            {'iid': 102, 'title': 'DB schema update', 'author': {'username': 'dev2'}},
            {'iid': 103, 'title': 'Fix login bug', 'author': {'username': 'dev1'}}
        ]
        
        summary = await ai_assistant.generate_merge_summary(merged_mrs, 'main')
        
        # Verify
        assert 'Merged 3 features' in summary
        assert '!101' in summary
        assert 'Authentication improvements' in summary
    
    def test_disabled_assistant(self):
        """Test behavior when AI is disabled."""
        with patch('backend.ai.ai_assistant.SecretsManager') as mock_secrets:
            # Mock secrets manager to raise exception (no API key)
            mock_instance = Mock()
            mock_instance.get_secret.side_effect = Exception("Secret not found")
            mock_secrets.return_value = mock_instance
            
            assistant = AIDebugAssistant()
            
            # Verify assistant is disabled
            assert assistant.enabled is False
    
    @pytest.mark.asyncio
    async def test_error_handling(self, ai_assistant, mock_openai):
        """Test error handling in AI calls."""
        # Mock OpenAI to raise exception
        mock_openai.ChatCompletion.create = AsyncMock(side_effect=Exception("API error"))
        
        # Test
        result = await ai_assistant.analyze_merge_conflict(
            conflict_files=['file.py'],
            source_branch='feature',
            target_branch='main',
            mr_title='Test'
        )
        
        # Verify error response
        assert result['error'] is True
        assert 'API error' in result['message']
    
    def test_singleton_pattern(self):
        """Test that get_ai_assistant() returns singleton."""
        with patch('backend.ai.ai_assistant.SecretsManager'):
            assistant1 = get_ai_assistant()
            assistant2 = get_ai_assistant()
            
            assert assistant1 is assistant2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
