"""
Integration tests for Merge Assist services.
Tests service interactions and database operations.
"""
import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.models import Base, User, Role, UserRole, Project, MergeRequest
from backend.database.connection import Database
from backend.auth.auth import hash_password, create_access_token, verify_token
from backend.auth.rbac import has_permission, Permission, Role as RoleEnum
import os


# Test database URL
TEST_DB_URL = "postgresql://merge_assist:password@localhost:5432/merge_assist_test"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine."""
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Create database session for each test."""
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_user(db_session):
    """Create a sample user for testing."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=hash_password("testpass123")
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_admin(db_session):
    """Create an admin user for testing."""
    user = User(
        username="admin",
        email="admin@example.com",
        password_hash=hash_password("adminpass123")
    )
    db_session.add(user)
    db_session.flush()
    
    # Create admin role
    role = Role(name="admin", description="Administrator")
    db_session.add(role)
    db_session.flush()
    
    # Assign role
    user_role = UserRole(user_id=user.id, role_id=role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


@pytest.fixture
def sample_project(db_session):
    """Create a sample project."""
    project = Project(
        name="Test Project",
        gitlab_id=12345,
        gitlab_url="https://gitlab.com/test/project",
        is_active=True
    )
    db_session.add(project)
    db_session.commit()
    return project


class TestUserAuthentication:
    """Test user authentication flow."""
    
    def test_create_user(self, db_session):
        """Test creating a new user."""
        user = User(
            username="newuser",
            email="newuser@example.com",
            password_hash=hash_password("password123")
        )
        db_session.add(user)
        db_session.commit()
        
        # Verify user was created
        assert user.id is not None
        assert user.username == "newuser"
        assert user.email == "newuser@example.com"
        assert user.is_active is True
    
    def test_password_hashing(self):
        """Test password hashing and verification."""
        from backend.auth.auth import hash_password, verify_password
        
        password = "MySecurePassword123"
        hashed = hash_password(password)
        
        # Verify correct password
        assert verify_password(password, hashed) is True
        
        # Verify wrong password
        assert verify_password("WrongPassword", hashed) is False
    
    def test_jwt_token_creation(self, sample_user):
        """Test JWT token creation and verification."""
        # Create token
        token_data = {
            "user_id": str(sample_user.id),
            "username": sample_user.username,
            "email": sample_user.email
        }
        token = create_access_token(token_data)
        
        # Verify token
        payload = verify_token(token)
        assert payload is not None
        assert payload["username"] == sample_user.username
        assert payload["email"] == sample_user.email


class TestRBAC:
    """Test role-based access control."""
    
    def test_admin_permissions(self, db_session, sample_admin):
        """Test that admin has all permissions."""
        roles = [ur.role.name for ur in sample_admin.user_roles]
        
        # Admin should have all permissions
        assert has_permission(roles, Permission.MANAGE_USERS) is True
        assert has_permission(roles, Permission.VIEW_ALL_PROJECTS) is True
        assert has_permission(roles, Permission.FORCE_MERGE) is True
    
    def test_viewer_permissions(self, db_session):
        """Test that viewer has limited permissions."""
        # Create viewer user
        user = User(username="viewer", email="viewer@example.com", password_hash="hash")
        db_session.add(user)
        db_session.flush()
        
        role = Role(name="viewer", description="Read-only")
        db_session.add(role)
        db_session.flush()
        
        user_role = UserRole(user_id=user.id, role_id=role.id)
        db_session.add(user_role)
        db_session.commit()
        
        roles = [ur.role.name for ur in user.user_roles]
        
        # Viewer should have limited permissions
        assert has_permission(roles, Permission.VIEW_PROJECT) is True
        assert has_permission(roles, Permission.MANAGE_USERS) is False
        assert has_permission(roles, Permission.FORCE_MERGE) is False


class TestProjectManagement:
    """Test project management operations."""
    
    def test_create_project(self, db_session):
        """Test creating a new project."""
        project = Project(
            name="Integration Test Project",
            gitlab_id=99999,
            gitlab_url="https://gitlab.com/test/integration",
            is_active=True
        )
        db_session.add(project)
        db_session.commit()
        
        assert project.id is not None
        assert project.name == "Integration Test Project"
        assert project.is_active is True
    
    def test_project_mr_relationship(self, db_session, sample_project):
        """Test project to MR relationship."""
        # Create MRs for project
        mr1 = MergeRequest(
            project_id=str(sample_project.id),
            gitlab_mr_iid=1,
            title="Test MR 1",
            source_branch="feature-1",
            target_branch="main",
            status="ready"
        )
        mr2 = MergeRequest(
            project_id=str(sample_project.id),
            gitlab_mr_iid=2,
            title="Test MR 2",
            source_branch="feature-2",
            target_branch="main",
            status="pending"
        )
        db_session.add_all([mr1, mr2])
        db_session.commit()
        
        # Verify relationship
        mrs = db_session.query(MergeRequest).filter(
            MergeRequest.project_id == str(sample_project.id)
        ).all()
        
        assert len(mrs) == 2
        assert all(mr.project_id == str(sample_project.id) for mr in mrs)


class TestMergeRequestWorkflow:
    """Test MR workflow operations."""
    
    def test_mr_status_progression(self, db_session, sample_project):
        """Test MR status transitions."""
        mr = MergeRequest(
            project_id=str(sample_project.id),
            gitlab_mr_iid=100,
            title="Status Test MR",
            source_branch="feature",
            target_branch="main",
            status="recognized"
        )
        db_session.add(mr)
        db_session.commit()
        
        # Status: recognized -> ready
        mr.status = "ready"
        db_session.commit()
        
        assert mr.status == "ready"
        
        # Status: ready -> merged
        mr.status = "merged"
        db_session.commit()
        
        assert mr.status == "merged"
    
    def test_mr_rejection_count(self, db_session, sample_project):
        """Test MR rejection counting."""
        mr = MergeRequest(
            project_id=str(sample_project.id),
            gitlab_mr_iid=200,
            title="Rejection Test",
            source_branch="bugfix",
            target_branch="main",
            status="not_ready",
            rejection_count=0
        )
        db_session.add(mr)
        db_session.commit()
        
        # First rejection
        mr.rejection_count += 1
        db_session.commit()
        assert mr.rejection_count == 1
        
        # Second rejection
        mr.rejection_count += 1
        db_session.commit()
        assert mr.rejection_count == 2
        
        # Third rejection -> should be rejected
        mr.rejection_count += 1
        if mr.rejection_count >= 3:
            mr.status = "rejected"
        db_session.commit()
        
        assert mr.rejection_count == 3
        assert mr.status == "rejected"


@pytest.mark.asyncio
class TestDatabaseConnection:
    """Test database connection management."""
    
    async def test_connection_pool(self):
        """Test database connection pooling."""
        db = Database()
        db.initialize(TEST_DB_URL)
        
        # Test multiple sessions
        with db.get_session() as session1:
            users1 = session1.query(User).count()
        
        with db.get_session() as session2:
            users2 = session2.query(User).count()
        
        # Both should succeed
        assert users1 >= 0
        assert users2 >= 0
        
        db.close()
    
    async def test_session_rollback_on_error(self):
        """Test that sessions rollback on exceptions."""
        db = Database()
        db.initialize(TEST_DB_URL)
        
        try:
            with db.get_session() as session:
                # Create invalid user (missing required fields)
                user = User(username=None)  # Will fail validation
                session.add(user)
                session.commit()
        except Exception:
            pass  # Expected to fail
        
        # Verify no partial data was committed
        with db.get_session() as session:
            invalid_users = session.query(User).filter(User.username == None).count()
            assert invalid_users == 0
        
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
