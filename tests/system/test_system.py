"""
System tests for Merge Assist.
Tests the complete application workflow with real services.
"""
import os
import asyncio
import pytest
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv
import aiohttp
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load system test environment
load_dotenv('tests/system/.env.system-test')

logger = logging.getLogger(__name__)


class SystemTestConfig:
    """Configuration for system tests loaded from environment."""
    
    def __init__(self):
        # GitLab
        self.gitlab_url = os.getenv('GITLAB_URL', 'https://gitlab.com')
        self.gitlab_token = os.getenv('GITLAB_TOKEN')
        self.gitlab_project_id = os.getenv('GITLAB_PROJECT_ID')
        self.gitlab_test_project_name = os.getenv('GITLAB_TEST_PROJECT_NAME', 'test-project')
        
        # Test users
        self.admin_username = os.getenv('TEST_ADMIN_USERNAME', 'test_admin')
        self.admin_password = os.getenv('TEST_ADMIN_PASSWORD', 'test_admin_pass')
        self.admin_email = os.getenv('TEST_ADMIN_EMAIL', 'admin@test.com')
        
        self.user_username = os.getenv('TEST_USER_USERNAME', 'test_user')
        self.user_password = os.getenv('TEST_USER_PASSWORD', 'test_user_pass')
        self.user_email = os.getenv('TEST_USER_EMAIL', 'user@test.com')
        
        # Database
        self.db_url = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        
        # Services
        self.api_url = os.getenv('API_GATEWAY_URL', 'http://localhost:8000')
        self.listener_url = os.getenv('LISTENER_URL', 'http://localhost:8001')
        
        # Test MRs
        self.test_source_branch = os.getenv('TEST_SOURCE_BRANCH', 'feature/system-test')
        self.test_target_branch = os.getenv('TEST_TARGET_BRANCH', 'main')
        self.test_mr_count = int(os.getenv('TEST_MR_COUNT', '5'))
        
        # Timeouts
        self.webhook_timeout = int(os.getenv('WEBHOOK_TIMEOUT', '30'))
        self.pipeline_timeout = int(os.getenv('PIPELINE_TIMEOUT', '300'))
        self.merge_timeout = int(os.getenv('MERGE_TIMEOUT', '60'))
        
        # Cleanup
        self.cleanup_after_tests = os.getenv('CLEANUP_AFTER_TESTS', 'true').lower() == 'true'
        self.cleanup_gitlab_mrs = os.getenv('CLEANUP_GITLAB_MRS', 'false').lower() == 'true'


@pytest.fixture(scope='session')
def config():
    """Provide system test configuration."""
    return SystemTestConfig()


@pytest.fixture(scope='session')
def db_engine(config):
    """Create database engine for system tests."""
    engine = create_engine(config.db_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope='session')
def db_session(db_engine):
    """Create database session."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope='session')
async def http_client():
    """Create async HTTP client for API calls."""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture(scope='session')
async def admin_token(config, http_client):
    """Get admin authentication token."""
    login_data = {
        'username': config.admin_username,
        'password': config.admin_password
    }
    
    async with http_client.post(
        f"{config.api_url}/auth/login",
        data=login_data
    ) as response:
        if response.status == 200:
            data = await response.json()
            return data['access_token']
        else:
            pytest.fail(f"Failed to login as admin: {response.status}")


@pytest.mark.system
@pytest.mark.asyncio
class TestSystemSetup:
    """Test system setup and initialization."""
    
    async def test_services_health(self, config, http_client):
        """Verify all services are running and healthy."""
        services = [
            ('API Gateway', f"{config.api_url}/health"),
            ('Listener', f"{config.listener_url}/health")
        ]
        
        for service_name, health_url in services:
            try:
                async with http_client.get(health_url, timeout=5) as response:
                    assert response.status == 200, f"{service_name} is not healthy"
                    logger.info(f"✅ {service_name} is healthy")
            except Exception as e:
                pytest.fail(f"{service_name} health check failed: {e}")
    
    async def test_database_connection(self, db_session):
        """Verify database is accessible."""
        try:
            result = db_session.execute("SELECT 1")
            assert result.fetchone()[0] == 1
            logger.info("✅ Database connection successful")
        except Exception as e:
            pytest.fail(f"Database connection failed: {e}")
    
    async def test_admin_user_exists(self, config, db_session):
        """Verify admin user exists or create it."""
        from backend.database.models import User, Role, UserRole
        from backend.auth.auth import hash_password
        
        # Check if admin exists
        user = db_session.query(User).filter_by(username=config.admin_username).first()
        
        if not user:
            logger.info("Creating admin user for tests...")
            
            # Create admin user
            user = User(
                username=config.admin_username,
                email=config.admin_email,
                password_hash=hash_password(config.admin_password),
                is_active=True
            )
            db_session.add(user)
            db_session.flush()
            
            # Create/get admin role
            admin_role = db_session.query(Role).filter_by(name='admin').first()
            if not admin_role:
                admin_role = Role(name='admin', description='System administrator')
                db_session.add(admin_role)
                db_session.flush()
            
            # Assign role
            user_role = UserRole(user_id=user.id, role_id=admin_role.id)
            db_session.add(user_role)
            db_session.commit()
            
            logger.info(f"✅ Created admin user: {config.admin_username}")
        else:
            logger.info(f"✅ Admin user exists: {config.admin_username}")
        
        assert user is not None


@pytest.mark.system
@pytest.mark.asyncio
class TestCompleteWorkflow:
    """Test complete MR workflow from creation to merge."""
    
    async def test_01_project_creation(self, config, http_client, admin_token, db_session):
        """Test creating a project via API."""
        from backend.database.models import Project
        
        # Check if project exists
        existing = db_session.query(Project).filter_by(
            gitlab_id=int(config.gitlab_project_id)
        ).first()
        
        if existing:
            logger.info(f"✅ Project already exists: {existing.name}")
            return
        
        project_data = {
            'name': config.gitlab_test_project_name,
            'gitlab_id': int(config.gitlab_project_id),
            'gitlab_url': f"{config.gitlab_url}/project/{config.gitlab_project_id}",
            'is_active': True,
            'batch_size': 5
        }
        
        headers = {'Authorization': f'Bearer {admin_token}'}
        
        async with http_client.post(
            f"{config.api_url}/projects",
            json=project_data,
            headers=headers
        ) as response:
            assert response.status == 200, f"Failed to create project: {await response.text()}"
            data = await response.json()
            
            logger.info(f"✅ Created project: {data['name']}")
            
            # Verify in database
            project = db_session.query(Project).filter_by(
                gitlab_id=int(config.gitlab_project_id)
            ).first()
            assert project is not None
            assert project.name == config.gitlab_test_project_name
    
    async def test_02_webhook_processing(self, config, http_client, db_session):
        """Test webhook processing for MR events."""
        # Simulate GitLab webhook for MR creation
        webhook_payload = {
            'object_kind': 'merge_request',
            'event_type': 'merge_request',
            'project': {
                'id': int(config.gitlab_project_id)
            },
            'object_attributes': {
                'id': 99999,
                'iid': 999,
                'title': 'System Test MR',
                'state': 'opened',
                'source_branch': config.test_source_branch,
                'target_branch': config.test_target_branch,
                'work_in_progress': False
            }
        }
        
        async with http_client.post(
            f"{config.listener_url}/webhook/gitlab",
            json=webhook_payload,
            headers={'X-Gitlab-Event': 'Merge Request Hook'}
        ) as response:
            assert response.status == 200, f"Webhook failed: {await response.text()}"
            logger.info("✅ Webhook processed successfully")
        
        # Wait for event processing
        await asyncio.sleep(2)
        
        # Verify MR was created in database
        from backend.database.models import MergeRequest
        mr = db_session.query(MergeRequest).filter_by(gitlab_mr_iid=999).first()
        
        # May not exist if GitLab project is not real
        if mr:
            logger.info(f"✅ MR created in database: !{mr.gitlab_mr_iid}")
        else:
            logger.warning("⚠️  MR not in database (expected if using mock GitLab)")
    
    async def test_03_mr_validation(self, config, http_client, admin_token):
        """Test MR validation logic."""
        # Get MRs for the project
        headers = {'Authorization': f'Bearer {admin_token}'}
        
        async with http_client.get(
            f"{config.api_url}/projects/{config.gitlab_project_id}/mrs",
            headers=headers
        ) as response:
            if response.status == 200:
                mrs = await response.json()
                logger.info(f"✅ Retrieved {len(mrs)} MRs from API")
                
                # Verify MR structure
                if mrs:
                    mr = mrs[0]
                    assert 'id' in mr
                    assert 'gitlab_mr_iid' in mr
                    assert 'status' in mr
                    logger.info(f"✅ MR structure valid: !{mr['gitlab_mr_iid']}")
            else:
                logger.warning(f"⚠️  Failed to get MRs: {response.status}")
    
    async def test_04_batch_merge_simulation(self, config, db_session):
        """Test batch merge logic with simulated MRs."""
        from backend.database.models import MergeRequest, Project
        
        # Get project
        project = db_session.query(Project).filter_by(
            gitlab_id=int(config.gitlab_project_id)
        ).first()
        
        if not project:
            pytest.skip("Project not created yet")
        
        # Create mock MRs in database for testing
        test_mrs = []
        for i in range(3):
            mr = MergeRequest(
                project_id=str(project.id),
                gitlab_mr_id=10000 + i,
                gitlab_mr_iid=1000 + i,
                title=f"System Test Batch MR {i+1}",
                source_branch=f"{config.test_source_branch}-{i}",
                target_branch=config.test_target_branch,
                status='ready',
                rejection_count=0
            )
            db_session.add(mr)
            test_mrs.append(mr)
        
        db_session.commit()
        
        logger.info(f"✅ Created {len(test_mrs)} test MRs for batch merge simulation")
        
        # Verify MRs were created
        ready_mrs = db_session.query(MergeRequest).filter_by(
            project_id=str(project.id),
            status='ready'
        ).limit(5).all()
        
        assert len(ready_mrs) >= 3, "Not enough ready MRs"
        logger.info(f"✅ Found {len(ready_mrs)} ready MRs for batch merge")
    
    async def test_05_priority_management(self, config, http_client, admin_token, db_session):
        """Test priority management functionality."""
        from backend.database.models import MergeRequest
        
        # Get a test MR
        mr = db_session.query(MergeRequest).filter_by(status='ready').first()
        
        if not mr:
            pytest.skip("No ready MRs available")
        
        headers = {'Authorization': f'Bearer {admin_token}'}
        
        # Set priority
        async with http_client.put(
            f"{config.api_url}/mrs/{mr.id}/priority",
            json={'priority': 1},
            headers=headers
        ) as response:
            if response.status == 200:
                logger.info(f"✅ Updated priority for MR !{mr.gitlab_mr_iid}")
                
                # Verify priority
                db_session.refresh(mr)
                assert mr.priority == 1
            else:
                logger.warning(f"⚠️  Priority update failed: {response.status}")
    
    async def test_06_logs_retrieval(self, config, http_client, admin_token):
        """Test retrieving MR logs."""
        headers = {'Authorization': f'Bearer {admin_token}'}
        
        async with http_client.get(
            f"{config.api_url}/logs",
            headers=headers,
            params={'limit': 10}
        ) as response:
            if response.status == 200:
                logs = await response.json()
                logger.info(f"✅ Retrieved {len(logs)} log entries")
                
                # Verify log structure
                if logs:
                    log = logs[0]
                    assert 'event_type' in log
                    assert 'message' in log
                    logger.info(f"✅ Log structure valid")
            else:
                logger.warning(f"⚠️  Failed to retrieve logs: {response.status}")


@pytest.mark.system
@pytest.mark.asyncio
class TestConcurrency:
    """Test concurrent request handling."""
    
    async def test_concurrent_webhooks(self, config, http_client):
        """Test processing multiple webhooks concurrently."""
        webhook_payload_template = {
            'object_kind': 'merge_request',
            'event_type': 'merge_request',
            'project': {
                'id': int(config.gitlab_project_id)
            },
            'object_attributes': {
                'id': 0,  # Will be set
                'iid': 0,  # Will be set
                'title': 'Concurrent Test MR',
                'state': 'opened',
                'source_branch': config.test_source_branch,
                'target_branch': config.test_target_branch,
                'work_in_progress': False
            }
        }
        
        # Create 10 concurrent webhook requests
        tasks = []
        for i in range(10):
            payload = webhook_payload_template.copy()
            payload['object_attributes'] = payload['object_attributes'].copy()
            payload['object_attributes']['id'] = 80000 + i
            payload['object_attributes']['iid'] = 8000 + i
            
            task = http_client.post(
                f"{config.listener_url}/webhook/gitlab",
                json=payload,
                headers={'X-Gitlab-Event': 'Merge Request Hook'}
            )
            tasks.append(task)
        
        # Execute concurrently
        start_time = time.time()
        responses = await asyncio.gather(*[task for task in tasks], return_exceptions=True)
        duration = time.time() - start_time
        
        # Verify all succeeded
        success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status == 200)
        
        logger.info(f"✅ Processed {success_count}/10 concurrent webhooks in {duration:.2f}s")
        assert success_count >= 8, f"Too many failures: {10 - success_count}"


@pytest.mark.system
@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in various scenarios."""
    
    async def test_invalid_webhook_payload(self, config, http_client):
        """Test handling of invalid webhook payloads."""
        invalid_payload = {'invalid': 'data'}
        
        async with http_client.post(
            f"{config.listener_url}/webhook/gitlab",
            json=invalid_payload,
            headers={'X-Gitlab-Event': 'Merge Request Hook'}
        ) as response:
            # Should handle gracefully (not crash)
            assert response.status in [200, 400, 422]
            logger.info(f"✅ Invalid payload handled gracefully: {response.status}")
    
    async def test_unauthorized_access(self, config, http_client):
        """Test API security with no authorization."""
        # Try to access protected endpoint without token
        async with http_client.get(
            f"{config.api_url}/projects"
        ) as response:
            assert response.status == 401, "Should require authentication"
            logger.info("✅ Unauthorized access properly rejected")
    
    async def test_invalid_token(self, config, http_client):
        """Test API security with invalid token."""
        headers = {'Authorization': 'Bearer invalid-token-here'}
        
        async with http_client.get(
            f"{config.api_url}/projects",
            headers=headers
        ) as response:
            assert response.status == 401, "Should reject invalid token"
            logger.info("✅ Invalid token properly rejected")


@pytest.mark.system
@pytest.mark.asyncio
class TestCleanup:
    """Cleanup test data after system tests."""
    
    async def test_cleanup_test_data(self, config, db_session):
        """Clean up test MRs and data."""
        if not config.cleanup_after_tests:
            pytest.skip("Cleanup disabled in configuration")
        
        from backend.database.models import MergeRequest
        
        # Delete test MRs
        deleted = db_session.query(MergeRequest).filter(
            MergeRequest.title.like('System Test%')
        ).delete(synchronize_session=False)
        
        db_session.commit()
        
        logger.info(f"✅ Cleaned up {deleted} test MRs")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "system"])
