"""
Unit tests for authentication module.
Example test file to demonstrate testing approach.
"""
import pytest
from backend.auth.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token
)


class TestPasswordHashing:
    """Test password hashing functionality."""
    
    def test_hash_password_creates_different_hashes(self):
        """Same password should create different hashes due to salt."""
        password = "test123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)
    
    def test_verify_password_success(self):
        """Correct password should verify successfully."""
        password = "my_secure_password"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_password_failure(self):
        """Wrong password should fail verification."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)
        
        assert verify_password(wrong_password, hashed) is False


class TestJWTTokens:
    """Test JWT token creation and verification."""
    
    def test_create_access_token(self):
        """Access token should be created with correct payload."""
        data = {"user_id": "123", "username": "testuser"}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Verify token can be decoded
        payload = verify_token(token, token_type="access")
        assert payload is not None
        assert payload["user_id"] == "123"
        assert payload["username"] == "testuser"
        assert "exp" in payload
        assert payload["type"] == "access"
    
    def test_create_refresh_token(self):
        """Refresh token should be created with longer expiration."""
        data = {"user_id": "123"}
        token = create_refresh_token(data)
        
        assert isinstance(token, str)
        
        payload = verify_token(token, token_type="refresh")
        assert payload is not None
        assert payload["type"] == "refresh"
    
    def test_verify_token_wrong_type(self):
        """Verifying token with wrong type should fail."""
        data = {"user_id": "123"}
        access_token = create_access_token(data)
        
        # Try to verify access token as refresh token
        payload = verify_token(access_token, token_type="refresh")
        assert payload is None
    
    def test_verify_invalid_token(self):
        """Invalid token should return None."""
        invalid_token = "this.is.not.a.valid.jwt.token"
        
        payload = verify_token(invalid_token)
        assert payload is None


@pytest.fixture
def sample_user_data():
    """Fixture providing sample user data for tests."""
    return {
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "username": "john_doe",
        "email": "john@example.com",
        "roles": ["project_owner"]
    }


class TestTokenPayload:
    """Test token payload handling."""
    
    def test_token_contains_all_user_data(self, sample_user_data):
        """Token should preserve all user data fields."""
        token = create_access_token(sample_user_data)
        payload = verify_token(token)
        
        assert payload["user_id"] == sample_user_data["user_id"]
        assert payload["username"] == sample_user_data["username"]
        assert payload["email"] == sample_user_data["email"]
        assert payload["roles"] == sample_user_data["roles"]


# Run with: pytest tests/unit/test_auth.py -v
