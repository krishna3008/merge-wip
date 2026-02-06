# Merge Assist - Testing Guide

## Complete Testing Documentation

This guide covers all testing strategies, how to run tests, and how to create new tests.

---

## Table of Contents

1. [Test Types Overview](#test-types-overview)
2. [Running Tests](#running-tests)
3. [Unit Tests](#unit-tests)
4. [Integration Tests](#integration-tests)
5. [End-to-End Tests](#end-to-end-tests)
6. [Writing New Tests](#writing-new-tests)
7. [Test Coverage](#test-coverage)
8. [CI/CD Integration](#cicd-integration)

---

## Test Types Overview

### Test Pyramid

```
        ┌───────────┐
        │    E2E    │  ← Slow, expensive, few tests
        │  (10%)    │     Complete workflows
        ├───────────┤
        │Integration│  ← Medium speed, moderate tests
        │  (30%)    │     Service interactions
        ├───────────┤
        │   Unit    │  ← Fast, cheap, many tests
        │  (60%)    │     Individual functions
        └───────────┘
```

**Unit Tests** (`tests/unit/`):
- Test individual functions and classes
- No external dependencies (mock everything)
- Fast execution (milliseconds)
- High volume

**Integration Tests** (`tests/integration/`):
- Test service interactions
- Real database (test instance)
- Real Redis connections
- Medium execution (seconds)

**End-to-End Tests** (`tests/e2e/`):
- Test complete workflows
- Real HTTP requests
- All services running
- Slow execution (minutes)

---

## Running Tests

### Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov aiohttp

# Start test database and Redis
docker-compose up -d postgres redis
```

### Run All Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=backend --cov-report=html

# With verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Run Specific Test Types

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# E2E tests only
pytest tests/e2e/

# Specific test file
pytest tests/unit/test_auth.py

# Specific test function
pytest tests/unit/test_auth.py::TestAuthentication::test_password_hashing
```

### Run Tests with Markers

```bash
# Run only fast tests
pytest -m fast

# Run only slow tests
pytest -m slow

# Skip slow tests
pytest -m "not slow"
```

---

## Unit Tests

### Location
`tests/unit/test_auth.py` (authentication)  
`tests/unit/test_rbac.py` (RBAC - to be created)  
`tests/unit/test_validators.py` (MR validators - to be created)

### Example: Testing Authentication

**File**: `tests/unit/test_auth.py`

```python
import pytest
from backend.auth.auth import hash_password, verify_password, create_access_token, verify_token


class TestPasswordHashing:
    """Test password hashing functions."""
    
    def test_hash_password(self):
        """Test that passwords are hashed."""
        password = "SecurePassword123"
        hashed = hash_password(password)
        
        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt identifier
    
    def test_verify_correct_password(self):
        """Test verifying correct password."""
        password = "SecurePassword123"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_incorrect_password(self):
        """Test rejecting incorrect password."""
        password = "SecurePassword123"
        hashed = hash_password(password)
        
        assert verify_password("WrongPassword", hashed) is False
    
    def test_different_hashes_for_same_password(self):
        """Test that same password produces different hashes (salt)."""
        password = "SecurePassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        assert hash1 != hash2  # Different due to salt
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWTTokens:
    """Test JWT token creation and verification."""
    
    def test_create_token(self):
        """Test creating access token."""
        data = {"user_id": "123", "username": "testuser"}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_verify_valid_token(self):
        """Test verifying valid token."""
        data = {"user_id": "123", "username": "testuser"}
        token = create_access_token(data)
        
        payload = verify_token(token)
        
        assert payload is not None
        assert payload["username"] == "testuser"
        assert payload["user_id"] == "123"
        assert "exp" in payload  # Expiration
    
    def test_verify_invalid_token(self):
        """Test rejecting invalid token."""
        invalid_token = "not.a.valid.token"
        
        payload = verify_token(invalid_token)
        
        assert payload is None
```

### Running Unit Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=backend.auth --cov-report=term-missing

# Output:
# Name                      Stmts   Miss  Cover   Missing
# -------------------------------------------------------
# backend/auth/auth.py         45      2    96%   78-79
# backend/auth/rbac.py         32      0   100%
```

---

## Integration Tests

### Location
`tests/integration/test_integration.py`

### Setup

Integration tests use a test database:

**File**: `tests/conftest.py` (shared fixtures)

```python
import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.models import Base

TEST_DB_URL = "postgresql://merge_assist:password@localhost:5432/merge_assist_test"


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
```

### Example: Testing Database Operations

```python
class TestUserAuthentication:
    """Test user authentication flow."""
    
    def test_create_user(self, db_session):
        """Test creating a new user."""
        from backend.database.models import User
        
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=hash_password("password123")
        )
        db_session.add(user)
        db_session.commit()
        
        # Verify
        assert user.id is not None
        assert user.username == "testuser"
        assert user.is_active is True
    
    def test_user_roles(self, db_session):
        """Test assigning roles to users."""
        from backend.database.models import User, Role, UserRole
        
        # Create user
        user = User(username="admin", email="admin@example.com", password_hash="hash")
        db_session.add(user)
        db_session.flush()
        
        # Create role
        role = Role(name="admin", description="Administrator")
        db_session.add(role)
        db_session.flush()
        
        # Assign role
        user_role = UserRole(user_id=user.id, role_id=role.id)
        db_session.add(user_role)
        db_session.commit()
        
        # Verify
        assert len(user.user_roles) == 1
        assert user.user_roles[0].role.name == "admin"
```

### Running Integration Tests

```bash
# Ensure test database exists
psql -h localhost -U merge_assist -c "CREATE DATABASE merge_assist_test;"

# Run integration tests  
pytest tests/integration/ -v

# With slower timeouts for DB operations
pytest tests/integration/ --timeout=60
```

---

## End-to-End Tests

### Location
`tests/e2e/test_e2e.py`

### Setup

E2E tests require all services running:

```bash
# Start all services
docker-compose up -d

# Wait for services to be healthy
sleep 10

# Run E2E tests
pytest tests/e2e/ -v
```

### Example: Testing Complete Workflow

```python
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
            "http://localhost:8000/auth/login",
            data=login_data
        ) as response:
            assert response.status == 200
            
            data = await response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"
    
    async def test_protected_endpoint_with_auth(self, api_client, auth_token):
        """Test accessing protected endpoint with valid token."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        async with api_client.get(
            "http://localhost:8000/projects",
            headers=headers
        ) as response:
            assert response.status == 200
            projects = await response.json()
            assert isinstance(projects, list)
```

### Running E2E Tests

```bash
# Ensure all services are running
docker-compose ps

# Run E2E tests
pytest tests/e2e/ -v -s

# With detailed logging
pytest tests/e2e/ -v -s --log-cli-level=DEBUG
```

---

## Writing New Tests

### Test Structure

```python
# tests/unit/test_feature.py
import pytest


class TestFeatureName:
    """Test suite for Feature X."""
    
    def test_basic_functionality(self):
        """Test description: what behavior is tested."""
        # Arrange: Set up test data
        input_data = "test"
        
        # Act: Execute the function
        result = function_under_test(input_data)
        
        # Assert: Verify the result
        assert result == expected_output
    
    def test_edge_case(self):
        """Test edge case: empty input."""
        result = function_under_test("")
        
        assert result is None
    
    def test_error_handling(self):
        """Test that function raises error for invalid input."""
        with pytest.raises(ValueError):
            function_under_test(invalid_input)
```

### Async Tests

```python
@pytest.mark.asyncio
class TestAsyncFeature:
    """Test async functions."""
    
    async def test_async_function(self):
        """Test async function."""
        result = await async_function()
        
        assert result is not None
```

### Using Fixtures

```python
@pytest.fixture
def sample_data():
    """Provide sample data for tests."""
    return {
        "name": "Test Project",
        "gitlab_id": 12345
    }


class TestWithFixture:
    def test_using_fixture(self, sample_data):
        """Test uses fixture data."""
        assert sample_data["name"] == "Test Project"
```

### Mocking External Services

```python
from unittest.mock import Mock, patch


class TestGitLabIntegration:
    """Test GitLab API integration."""
    
    @patch('backend.gitlab_integration.gitlab_custom_client.aiohttp.ClientSession')
    async def test_api_call(self, mock_session):
        """Test API call with mocked response."""
        # Mock response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = Mock(return_value={"id": 123})
        
        mock_session.return_value.__aenter__.return_value = mock_response
        
        # Test
        client = GitLabCustomClient("https://gitlab.com", "token")
        result = await client.get_merge_request(12345, 1)
        
        assert result["id"] == 123
```

---

## Test Coverage

### Generate Coverage Report

```bash
# HTML report
pytest --cov=backend --cov-report=html

# Open report
open htmlcov/index.html

# Terminal report
pytest --cov=backend --cov-report=term-missing

# Output:
# Name                                         Stmts   Miss  Cover   Missing
# --------------------------------------------------------------------------
# backend/__init__.py                             0      0   100%
# backend/auth/auth.py                           45      2    96%   78-79
# backend/auth/rbac.py                           32      0   100%
# backend/database/connection.py                 28      1    96%   45
# backend/database/models.py                    102      5    95%   23, 67-71
# --------------------------------------------------------------------------
# TOTAL                                        207      8    96%
```

### Coverage Goals

- **Overall**: >80% coverage
- **Critical paths** (auth, merge logic): >95%
- **Utilities**: >70%

---

## CI/CD Integration

### GitHub Actions Example

**File**: `.github/workflows/test.yml`

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_USER: merge_assist
          POSTGRES_PASSWORD: password
          POSTGRES_DB: merge_assist_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio
      
      - name: Run unit tests
        run: pytest tests/unit/ -v --cov=backend
      
      - name: Run integration tests
        run: pytest tests/integration/ -v
        env:
          DB_HOST: localhost
          DB_PORT: 5432
          REDIS_HOST: localhost
          REDIS_PORT: 6379
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

---

## Test Data Management

### Fixtures for Common Data

**File**: `tests/fixtures/sample_data.py`

```python
"""Sample data for tests."""

SAMPLE_USER = {
    "username": "testuser",
    "email": "test@example.com",
    "password": "SecurePassword123"
}

SAMPLE_PROJECT = {
    "name": "Test Project",
    "gitlab_id": 12345,
    "gitlab_url": "https://gitlab.com/test/project",
    "is_active": True
}

SAMPLE_MR = {
    "gitlab_mr_iid": 1,
    "title": "Test MR",
    "source_branch": "feature-test",
    "target_branch": "main",
    "status": "ready"
}
```

### Database Seeding for Tests

```python
@pytest.fixture
def seed_database(db_session):
    """Seed database with test data."""
    from backend.database.models import User, Project, MergeRequest
    
    # Create user
    user = User(**SAMPLE_USER)
    db_session.add(user)
    db_session.flush()
    
    # Create project
    project = Project(**SAMPLE_PROJECT)
    db_session.add(project)
    db_session.flush()
    
    # Create MRs
    for i in range(5):
        mr = MergeRequest(
            project_id=str(project.id),
            gitlab_mr_iid=i+1,
            title=f"Test MR {i+1}",
            source_branch=f"feature-{i}",
            target_branch="main",
            status="ready"
        )
        db_session.add(mr)
    
    db_session.commit()
    
    return {
        "user": user,
        "project": project
    }
```

---

## Best Practices

### 1. Test Naming

```python
# Good: Descriptive names
def test_user_login_with_valid_credentials_returns_token():
    pass

# Bad: Vague names
def test_login():
    pass
```

### 2. One Assert Per Test (when possible)

```python
# Good: Focused test
def test_user_has_username():
    user = create_user()
    assert user.username == "testuser"

def test_user_has_email():
    user = create_user()
    assert user.email == "test@example.com"

# Acceptable: Related asserts
def test_user_creation():
    user = create_user()
    assert user.id is not None
    assert user.is_active is True
```

### 3. Test Independence

```python
# Good: Each test is independent
def test_feature_a(db_session):
    # Fresh database session
    result = function_a()
    assert result is True

def test_feature_b(db_session):
    # Fresh database session (rollback from previous test)
    result = function_b()
    assert result is True
```

### 4. Use Meaningful Test Data

```python
# Good: Clear intent
user = User(username="admin_user", email="admin@company.com")

# Bad: Meaningless data
user = User(username="user1", email="a@b.com")
```

---

## Troubleshooting Tests

### Tests Hanging

```bash
# Add timeout
pytest --timeout=30

# Identify slow tests
pytest --durations=10
```

### Database Errors

```bash
# Check test database exists
psql -h localhost -U merge_assist -l | grep merge_assist_test

# Recreate test database
dropdb -h localhost -U merge_assist merge_assist_test
createdb -h localhost -U merge_assist merge_assist_test
```

### Import Errors

```bash
# Ensure packages are installed
pip install -r requirements.txt

# Check PYTHONPATH
export PYTHONPATH=.
pytest
```

---

## Summary

**Test Organization**:
- Unit tests: `tests/unit/` (fast, isolated)
- Integration tests: `tests/integration/` (database + Redis)
- E2E tests: `tests/e2e/` (full system)

**Running Tests**:
```bash
pytest                    # All tests
pytest tests/unit/        # Unit only
pytest --cov=backend      # With coverage
pytest -v -s              # Verbose with output
```

**Coverage Goal**: >80% overall, >95% critical paths

**CI/CD**: GitHub Actions runs all tests on every push

---

*For implementation details, see the actual test files in `tests/` directory.*
