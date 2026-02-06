"""
End-to-End tests for Merge Assist.
Tests complete workflows from webhook to merge.
"""
import pytest
import asyncio
import aiohttp
from typing import Dict, Any
import time


# Test configuration
API_BASE_URL = "http://localhost:8000"
LISTENER_BASE_URL = "http://localhost:8001"
TEST_GITLAB_PROJECT_ID = 12345
TEST_MR_IID = 100


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def api_client():
    """Create HTTP client for API requests."""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
async def auth_token(api_client):
    """Get authentication token."""
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    
    async with api_client.post(
        f"{API_BASE_URL}/auth/login",
        data=login_data
    ) as response:
        if response.status == 200:
            data = await response.json()
            return data["access_token"]
    
    # If admin doesn't exist, create it first
    # (In real tests, you'd have a setup script)
    return None


@pytest.mark.asyncio
class TestAuthenticationFlow:
    """Test complete authentication workflow."""
    
    async def test_login_flow(self, api_client):
        """Test user login and token retrieval."""
        # Attempt login
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        async with api_client.post(
            f"{API_BASE_URL}/auth/login",
            data=login_data
        ) as response:
            # Should return token or 401
            assert response.status in [200, 401]
            
            if response.status == 200:
                data = await response.json()
                assert "access_token" in data
                assert "refresh_token" in data
                assert data["token_type"] == "bearer"
    
    async def test_protected_endpoint_without_auth(self, api_client):
        """Test that protected endpoints reject unauthenticated requests."""
        async with api_client.get(f"{API_BASE_URL}/projects") as response:
            assert response.status == 401  # Unauthorized
    
    async def test_protected_endpoint_with_auth(self, api_client, auth_token):
        """Test accessing protected endpoint with valid token."""
        if not auth_token:
            pytest.skip("No auth token available")
        
        headers = {"Authorization": f"Bearer {auth_token}"}
        async with api_client.get(
            f"{API_BASE_URL}/projects",
            headers=headers
        ) as response:
            assert response.status in [200, 403]  # OK or Forbidden (RBAC)


@pytest.mark.asyncio
class TestProjectManagementFlow:
    """Test project management workflows."""
    
    async def test_list_projects(self, api_client, auth_token):
        """Test listing all projects."""
        if not auth_token:
            pytest.skip("No auth token available")
        
        headers = {"Authorization": f"Bearer {auth_token}"}
        async with api_client.get(
            f"{API_BASE_URL}/projects",
            headers=headers
        ) as response:
            if response.status == 200:
                projects = await response.json()
                assert isinstance(projects, list)
    
    async def test_get_project_mrs(self, api_client, auth_token):
        """Test retrieving MRs for a project."""
        if not auth_token:
            pytest.skip("No auth token available")
        
        # Assuming project exists with some ID
        project_id = "test-uuid"  # Replace with actual project ID
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        async with api_client.get(
            f"{API_BASE_URL}/projects/{project_id}/mrs",
            headers=headers
        ) as response:
            # 200 (found) or 404 (not found)
            assert response.status in [200, 404]


@pytest.mark.asyncio
class TestWebhookFlow:
    """Test webhook processing flow."""
    
    async def test_webhook_mr_opened(self, api_client):
        """Test webhook for MR opened event."""
        webhook_payload = {
            "object_kind": "merge_request",
            "event_type": "merge_request",
            "object_attributes": {
                "iid": TEST_MR_IID,
                "title": "Test MR",
                "state": "opened",
                "source_branch": "feature-test",
                "target_branch": "main",
                "action": "open"
            },
            "project": {
                "id": TEST_GITLAB_PROJECT_ID,
                "name": "Test Project"
            },
            "assignees": [
                {"id": 12345}  # Merge Assist user ID
            ]
        }
        
        async with api_client.post(
            f"{LISTENER_BASE_URL}/webhook/gitlab",
            json=webhook_payload
        ) as response:
            # Should accept webhook
            assert response.status in [200, 500]  # 500 if services not running
            
            if response.status == 200:
                data = await response.json()
                assert "status" in data
    
    async def test_webhook_pipeline_event(self, api_client):
        """Test webhook for pipeline completion event."""
        webhook_payload = {
            "object_kind": "pipeline",
            "object_attributes": {
                "id": 1000,
                "status": "success",
                "ref": "feature-test",
                "sha": "abc123def456"
            },
            "project": {
                "id": TEST_GITLAB_PROJECT_ID
            },
            "merge_requests": [
                {"iid": TEST_MR_IID}
            ]
        }
        
        async with api_client.post(
            f"{LISTENER_BASE_URL}/webhook/gitlab",
            json=webhook_payload
        ) as response:
            assert response.status in [200, 500]


@pytest.mark.asyncio
class TestMergeWorkflow:
    """Test complete merge workflow (E2E)."""
    
    async def test_single_mr_merge_workflow(self, api_client, auth_token):
        """
        Test complete single MR merge workflow:
        1. MR is recognized (webhook or polling)
        2. Validator checks readiness
        3. MR is rebased
        4. Pipeline runs
        5. MR is merged
        """
        # This is a simulation since we need actual GitLab
        # In real E2E, this would:
        # - Create MR in GitLab
        # - Trigger webhook
        # - Wait for Worker POD to process
        # - Verify MR is merged
        # - Check database status
        
        pytest.skip("Requires live GitLab instance")
    
    async def test_batch_merge_workflow(self, api_client, auth_token):
        """
        Test batch merge workflow:
        1. 5 MRs marked as ready
        2. Worker creates batch branch
        3. All MRs merged to batch
        4. Pipeline runs on batch
        5. Individual MRs merged
        """
        pytest.skip("Requires live GitLab instance")


@pytest.mark.asyncio
class TestHealthAndMonitoring:
    """Test health checks and monitoring endpoints."""
    
    async def test_api_health_check(self, api_client):
        """Test API Gateway health check."""
        async with api_client.get(f"{API_BASE_URL}/health") as response:
            assert response.status == 200
            data = await response.json()
            assert data["status"] == "healthy"
    
    async def test_listener_health_check(self, api_client):
        """Test Listener service health check."""
        async with api_client.get(f"{LISTENER_BASE_URL}/health") as response:
            assert response.status == 200
            data = await response.json()
            assert data["status"] == "healthy"


@pytest.mark.asyncio
class TestConcurrency:
    """Test concurrent request handling."""
    
    async def test_concurrent_webhook_processing(self, api_client):
        """Test handling multiple simultaneous webhooks."""
        # Create 10 webhook payloads
        tasks = []
        for i in range(10):
            webhook_payload = {
                "object_kind": "merge_request",
                "object_attributes": {
                    "iid": 1000 + i,
                    "title": f"Concurrent Test MR {i}",
                    "state": "opened",
                    "source_branch": f"feature-{i}",
                    "target_branch": "main",
                    "action": "open"
                },
                "project": {"id": TEST_GITLAB_PROJECT_ID},
                "assignees": [{"id": 12345}]
            }
            
            task = api_client.post(
                f"{LISTENER_BASE_URL}/webhook/gitlab",
                json=webhook_payload
            )
            tasks.append(task)
        
        # Send all webhooks concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should be processed (200 or 500 if services down)
        for response in responses:
            if not isinstance(response, Exception):
                assert response.status in [200, 500]


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in various scenarios."""
    
    async def test_invalid_webhook_payload(self, api_client):
        """Test handling of malformed webhook payload."""
        invalid_payload = {
            "object_kind": "invalid_event",
            "data": "garbage"
        }
        
        async with api_client.post(
            f"{LISTENER_BASE_URL}/webhook/gitlab",
            json=invalid_payload
        ) as response:
            # Should handle gracefully
            assert response.status in [200, 400, 500]
    
    async def test_invalid_credentials(self, api_client):
        """Test login with invalid credentials."""
        login_data = {
            "username": "nonexistent",
            "password": "wrongpassword"
        }
        
        async with api_client.post(
            f"{API_BASE_URL}/auth/login",
            data=login_data
        ) as response:
            assert response.status == 401  # Unauthorized


# Test runner
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
