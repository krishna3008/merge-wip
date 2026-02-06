"""
Configuration file for pytest.
"""
import pytest
import os
import sys

# Add backend to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))


@pytest.fixture(scope="session")
def test_database_url():
    """Provide test database URL."""
    return "postgresql://merge_assist:password@localhost:5432/merge_assist_test"


@pytest.fixture(scope="session")
def test_redis_url():
    """Provide test Redis URL."""
    return "redis://localhost:6379/1"


@pytest.fixture(scope="function")
def clean_database(test_database_url):
    """Clean database before each test."""
    from backend.database.connection import db
    
    db.initialize(test_database_url)
    db.create_all()
    
    yield
    
    # Cleanup
    db.drop_all()
    db.close()


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)
