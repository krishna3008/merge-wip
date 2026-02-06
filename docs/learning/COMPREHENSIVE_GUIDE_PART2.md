# Merge Assist - Comprehensive Guide Part 2
## RBAC, Secrets Management, and Configuration

*Continuation from Part 1*

---

## 3.3: Role-Based Access Control (RBAC)

### Learning Objectives
- Understand permission-based security
- Implement decorators for endpoint protection
- Design scalable role systems

### 3.3.1: Why RBAC?

**Simple auth** (all or nothing):
```python
@app.get("/projects")
def list_projects(user: User):
    if not user:
        raise HTTPException(403)
    return projects  # Any logged-in user can access!
```

**Problems**:
- ❌ Can't differentiate between admin and viewer
- ❌ All users have same permissions
- ❌ Hard to add new roles

**RBAC** (granular permissions):
```python
@app.get("/projects")
@require_permission(Permission.VIEW_PROJECTS)
def list_projects(user: User):
    return projects  # Only users with VIEW_PROJECTS can access
```

**Benefits**:
- ✅ Fine-grained control
- ✅ Easy to add roles/permissions
-✅ Principle of least privilege

### 3.3.2: Design Permission System

Create `backend/auth/rbac.py`:

```python
"""
Role-Based Access Control (RBAC) system.
"""
from enum import Enum
from functools import wraps
from fastapi import HTTPException
from typing import Set, Callable


class Role(str, Enum):
    """
    User roles in the system.
    
    Why an Enum?
    - Type safety: Can't typo role names
    - Autocomplete: IDE suggests valid roles
    - Centralized: All roles defined in one place
    """
    ADMIN = "admin"
    PROJECT_OWNER = "project_owner"
    PRIORITY_MANAGER = "priority_manager"
    VIEWER = "viewer"


class Permission(str, Enum):
    """
    Granular permissions.
    
    Naming convention:
    - VERB_NOUN: CREATE_PROJECT, DELETE_USER, VIEW_LOGS
    - Specific: Better than broad "ADMIN" permission
    """
    # Global permissions
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    VIEW_ALL_PROJECTS = "view_all_projects"
    
    # Project permissions
    CREATE_PROJECT = "create_project"
    DELETE_PROJECT = "delete_project"
    VIEW_PROJECT = "view_project"
    CONFIGURE_PROJECT = "configure_project"
    
    # MR permissions
    SET_MR_PRIORITY = "set_mr_priority"
    FORCE_MERGE = "force_merge"
    
    # System permissions
    VIEW_LOGS = "view_logs"
    VIEW_HEALTH = "view_health"


# Role-Permission mapping
ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.ADMIN: {
        # Admins can do everything
        Permission.MANAGE_USERS,
        Permission.MANAGE_ROLES,
        Permission.VIEW_ALL_PROJECTS,
        Permission.CREATE_PROJECT,
        Permission.DELETE_PROJECT,
        Permission.VIEW_PROJECT,
        Permission.CONFIGURE_PROJECT,
        Permission.SET_MR_PRIORITY,
        Permission.FORCE_MERGE,
        Permission.VIEW_LOGS,
        Permission.VIEW_HEALTH,
    },
    Role.PROJECT_OWNER: {
        # Can manage owned projects
        Permission.VIEW_PROJECT,
        Permission.CONFIGURE_PROJECT,
        Permission.VIEW_LOGS,
    },
    Role.PRIORITY_MANAGER: {
        # Can adjust MR priorities
        Permission.VIEW_PROJECT,
        Permission.SET_MR_PRIORITY,
    },
    Role.VIEWER: {
        # Read-only access
        Permission.VIEW_PROJECT,
        Permission.VIEW_HEALTH,
    },
}


def has_permission(user_roles: list[str], permission: Permission) -> bool:
    """
    Check if user has a specific permission.
    
    Args:
        user_roles: List of role names (e.g., ["admin", "viewer"])
        permission: Permission to check
    
    Returns:
        True if user has permission via any role
    
    Example:
        >>> has_permission(["admin"], Permission.MANAGE_USERS)
        True
        >>> has_permission(["viewer"], Permission.MANAGE_USERS)
        False
    """
    for role_name in user_roles:
        try:
            role = Role(role_name)
            if permission in ROLE_PERMISSIONS[role]:
                return True
        except ValueError:
            # Invalid role name, skip
            continue
    
    return False


def require_permission(permission: Permission):
    """
    Decorator to protect FastAPI endpoints with permissions.
    
    Usage:
        @app.get("/users")
        @require_permission(Permission.MANAGE_USERS)
        async def list_users(current_user: dict = Depends(get_current_user)):
            # Only users with MANAGE_USERS permission can reach here
            return users
    
    How it works:
    1. Decorator wraps the endpoint function
    2. Extracts current_user from function arguments
    3. Checks if user has required permission
    4. If yes: Calls original function
    5. If no: Raises 403 Forbidden exception
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs
            current_user = kwargs.get('current_user')
            
            if not current_user:
                raise HTTPException(
                    status_code=401,
                    detail="Not authenticated"
                )
            
            # Check permission
            user_roles = current_user.get('roles', [])
            if not has_permission(user_roles, permission):
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission denied: {permission.value} required"
                )
            
            # Permission granted, call original function
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_role(role: Role):
    """
    Decorator to require specific role.
    
    Usage:
        @app.delete("/users/{user_id}")
        @require_role(Role.ADMIN)
        async def delete_user(user_id: str):
            # Only admins can reach here
            delete_user_from_db(user_id)
    
    Note: Prefer require_permission() over this for better granularity
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            
            if not current_user:
                raise HTTPException(status_code=401, detail="Not authenticated")
            
            user_roles = current_user.get('roles', [])
            if role.value not in user_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Role {role.value} required"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
```

**Why decorators?**

**Without decorator** (manual checks everywhere ❌):
```python
@app.get("/users")
def list_users(current_user: dict):
    # Repeat this in EVERY endpoint!
    if not has_permission(current_user['roles'], Permission.MANAGE_USERS):
        raise HTTPException(403)
    
    return users
```

**With decorator** (DRY ✅):
```python
@app.get("/users")
@require_permission(Permission.MANAGE_USERS)
def list_users(current_user: dict):
    return users  # Permission check is automatic!
```

### 3.3.3: Project-Level Permissions

Some permissions are project-specific. For example, "User A can manage Project X, but not Project Y."

Create project permission checker:

```python
def check_project_permission(
    user_id: str,
    project_id: str,
    permission: Permission,
    db_session
) -> bool:
    """
    Check if user has permission for a specific project.
    
    Logic:
    1. If user is admin → Always allowed
    2. If user is project owner → Check project_permissions table
    3. Otherwise → Check via role permissions
    """
    from backend.database.models import User, ProjectPermission
    
    # Get user with roles
    user = db_session.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    
    user_roles = [ur.role.name for ur in user.user_roles]
    
    # Admin can do anything
    if 'admin' in user_roles:
        return True
    
    # Check project-specific permission
    project_perm = db_session.query(ProjectPermission).filter(
        ProjectPermission.user_id == user_id,
        ProjectPermission.project_id == project_id
    ).first()
    
    if project_perm:
        # User has explicit permission for this project
        return has_permission(user_roles, permission)
    
    return False
```

---

## 4. Part 3: Secrets Management

### Learning Objectives
- Understand why secrets can't be in code
- Implement provider pattern for flexibility
- Use AWS Secrets Manager and local encryption

### 4.1: Why Secrets Management?

**Bad practice** (secrets in code ❌):
```python
# DON'T DO THIS!
GITLAB_TOKEN = "glpat-1234567890abcdef"
DB_PASSWORD = "my_password_123"
JWT_SECRET = "super_secret_key"
```

**Problems**:
- ❌ Exposed in Git history (even if deleted later)
- ❌ Visible to anyone with code access
- ❌ Hard to rotate (must change code and redeploy)
- ❌ Same secrets in dev/staging/production

**Good practice** (secrets manager ✅):
```python
from secrets_manager import get_gitlab_token
token = get_gitlab_token(project_id)  # Fetched securely
```

**Benefits**:
- ✅ Secrets never in code
- ✅ Different secrets per environment
- ✅ Easy rotation without redeployment
- ✅ Audit trail (who accessed which secret)

### 4.2: Provider Pattern

**Challenge**: Support multiple secret backends
- Development: Local encrypted file
- Production: AWS Secrets Manager

**Solution**: Abstract provider interface

```
                    ┌─────────────────┐
                    │ SecretsManager  │
                    │   (Singleton)   │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼────────┐  ┌────────▼────────┐  ┌───────▼────────┐
│ AWSProvider    │  │ LocalProvider   │  │ GCPProvider    │
│ (Production)   │  │ (Development)   │  │  (Future)      │
└────────────────┘  └─────────────────┘  └────────────────┘
```

### 4.3: Implement Secrets Manager

#### Step 4.3.1: Create Provider Interface

Create `backend/secrets/secrets_manager.py`:

```python
"""
Unified secrets management with provider pattern.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import os
import json


class SecretsProvider(ABC):
    """
    Abstract base class for secret providers.
    
    Why abstract class?
    - Defines interface all providers must implement
    - Enables polymorphism (swap providers without changing code)
    - Type safety (mypy can check interface compliance)
    """
    
    @abstractmethod
    def get_secret(self, secret_name: str) -> Dict[str, Any]:
        """
        Retrieve a secret.
        
        Args:
            secret_name: Identifier for the secret
        
        Returns:
            Dictionary containing secret data
        
        Raises:
            SecretNotFoundError: If secret doesn't exist
        """
        pass
    
    @abstractmethod
    def set_secret(self, secret_name: str, secret_value: Dict[str, Any]) -> bool:
        """
        Store or update a secret.
        
        Args:
            secret_name: Identifier for the secret
            secret_value: Dictionary containing secret data
        
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def delete_secret(self, secret_name: str) -> bool:
        """Delete a secret."""
        pass
```

**What is polymorphism?**

Same interface, different implementations:

```python
# Development
manager = SecretsManager(provider=LocalProvider())
token = manager.get_secret("gitlab_token")  # Reads from file

# Production
manager = SecretsManager(provider=AWSProvider())
token = manager.get_secret("gitlab_token")  # Reads from AWS

# Same code, different behavior!
```

#### Step 4.3.2: AWS Secrets Manager Provider

```python
import boto3
from botocore.exceptions import ClientError


class AWSSecretsProvider(SecretsProvider):
    """
    AWS Secrets Manager provider for production.
    
    Why AWS Secrets Manager?
    - Automatic rotation
    - Fine-grained IAM permissions
    - Audit logging via CloudTrail
    - Encryption at rest (KMS)
    """
    
    def __init__(self, region_name: str = 'us-east-1'):
        """
        Initialize AWS Secrets Manager client.
        
        Authentication:
        - Uses IAM role (EC2, EKS, Lambda)
        - Or AWS credentials from environment
        """
        self.client = boto3.client(
            'secretsmanager',
            region_name=region_name
        )
    
    def get_secret(self, secret_name: str) -> Dict[str, Any]:
        """
        Get secret from AWS Secrets Manager.
        
        Example secret_name: "merge-assist/gitlab/project/12345"
        """
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
        except ClientError as e:
            error_code = e.response['Error']['Code']
           
            if error_code == 'ResourceNotFoundException':
                raise ValueError(f"Secret {secret_name} not found")
            elif error_code == 'InvalidRequestException':
                raise ValueError(f"Invalid request for {secret_name}")
            elif error_code == 'InvalidParameterException':
                raise ValueError(f"Invalid parameter for {secret_name}")
            else:
                raise
    
    def set_secret(self, secret_name: str, secret_value: Dict[str, Any]) -> bool:
        """Create or update secret in AWS."""
        secret_string = json.dumps(secret_value)
        
        try:
            # Try to update existing secret
            self.client.update_secret(
                SecretId=secret_name,
                SecretString=secret_string
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Secret doesn't exist, create it
                self.client.create_secret(
                    Name=secret_name,
                    SecretString=secret_string
                )
                return True
            raise
    
    def delete_secret(self, secret_name: str) -> bool:
        """Delete secret from AWS."""
        try:
            self.client.delete_secret(
                SecretId=secret_name,
                ForceDeleteWithoutRecovery=True
            )
            return True
        except ClientError:
            return False
```

#### Step 4.3.3: Local Encrypted Provider

For development, store secrets in an encrypted local file:

Create `backend/secrets/encryption.py`:

```python
"""
AES-256 encryption for local secrets.
"""
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
import base64
import os


def derive_key_from_password(password: str, salt: bytes) -> bytes:
    """
    Derive encryption key from password using PBKDF2.
    
    Why PBKDF2?
    - Converts weak password → Strong encryption key
    - Slow by design (prevents brute force)
    - Uses salt (prevents rainbow tables)
    
    Parameters:
    - iterations=100,000: Balance security vs. performance
    - Higher = more secure but slower
    """
    kdf = PBKDF2(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bits
        salt=salt,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key


class SecretEncryption:
    """AES-256 encryption for secrets."""
    
    def __init__(self, master_password: str, salt: str = "merge-assist-salt"):
        """
        Initialize encryption with master password.
        
        Master password:
        - Stored in environment variable (not in code!)
        - Used to derive encryption key
        - Should be long and random (>= 16 characters)
        """
        key = derive_key_from_password(master_password, salt.encode())
        self.cipher = Fernet(key)
    
    def encrypt(self, data: str) -> bytes:
        """Encrypt string data."""
        return self.cipher.encrypt(data.encode())
    
    def decrypt(self, encrypted_data: bytes) -> str:
        """Decrypt to string."""
        return self.cipher.decrypt(encrypted_data).decode()
    
    def encrypt_file(self, filepath: str, data: dict):
        """Encrypt and write JSON data to file."""
        json_str = json.dumps(data)
        encrypted = self.encrypt(json_str)
        
        with open(filepath, 'wb') as f:
            f.write(encrypted)
    
    def decrypt_file(self, filepath: str) -> dict:
        """Read and decrypt JSON file."""
        with open(filepath, 'rb') as f:
            encrypted = f.read()
        
        decrypted = self.decrypt(encrypted)
        return json.loads(decrypted)
```

**Why AES-256?**
- Industry standard symmetric encryption
- Fast and secure
- 256-bit key = 2^256 possible keys (impossible to brute force)

**Symmetric vs. Asymmetric encryption**:

**Symmetric** (AES):
- Same key encrypts and decrypts
- Fast
- Good for encrypting data at rest

**Asymmetric** (RSA):
- Public key encrypts, private key decrypts
- Slower
- Good for key exchange and digital signatures

For local secret storage, AES is perfect.

#### Step 4.3.4: Complete SecretsManager

```python
class LocalSecretsProvider(SecretsProvider):
    """Local file-based encrypted secrets for development."""
    
    def __init__(self, secrets_file: str, master_password: str):
        """
        Initialize local secrets provider.
        
        Args:
            secrets_file: Path to encrypted secrets file
            master_password: Password for encryption/decryption
        """
        self.secrets_file = secrets_file
        self.encryption = SecretEncryption(master_password)
        
        # Create file if doesn't exist
        if not os.path.exists(secrets_file):
            self.encryption.encrypt_file(secrets_file, {})
    
    def get_secret(self, secret_name: str) -> Dict[str, Any]:
        """Get secret from local encrypted file."""
        secrets = self.encryption.decrypt_file(self.secrets_file)
        
        if secret_name not in secrets:
            raise ValueError(f"Secret {secret_name} not found")
        
        return secrets[secret_name]
    
    def set_secret(self, secret_name: str, secret_value: Dict[str, Any]) -> bool:
        """Store secret in local encrypted file."""
        secrets = self.encryption.decrypt_file(self.secrets_file)
        secrets[secret_name] = secret_value
        self.encryption.encrypt_file(self.secrets_file, secrets)
        return True
    
    def delete_secret(self, secret_name: str) -> bool:
        """Delete secret from local file."""
        secrets = self.encryption.decrypt_file(self.secrets_file)
        if secret_name in secrets:
            del secrets[secret_name]
            self.encryption.encrypt_file(self.secrets_file, secrets)
            return True
        return False


class SecretsManager:
    """
    Unified secrets manager (Singleton).
    
    Auto-selects provider based on environment.
    """
    _instance = None
    _provider: Optional[SecretsProvider] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(self):
        """Initialize with appropriate provider."""
        if self._provider is not None:
            return  # Already initialized
        
        provider_type = os.getenv('SECRETS_PROVIDER', 'local')
        
        if provider_type == 'aws':
            region = os.getenv('AWS_REGION', 'us-east-1')
            self._provider = AWSSecretsProvider(region)
        else:  # local
            secrets_file = os.getenv('SECRETS_FILE', '/app/secrets/local_secrets.enc')
            master_password = os.getenv('MASTER_PASSWORD', 'dev-password')
            self._provider = LocalSecretsProvider(secrets_file, master_password)
    
    def get_secret(self, secret_name: str) -> Dict[str, Any]:
        """Get a secret."""
        if self._provider is None:
            self.initialize()
        return self._provider.get_secret(secret_name)
    
    # Convenience methods for common secrets
    def get_gitlab_token(self, project_id: str) -> str:
        """Get GitLab token for a project."""
        secret = self.get_secret(f'gitlab/project/{project_id}')
        return secret['token']
    
    def get_database_credentials(self) -> Dict[str, str]:
        """Get database credentials."""
        return self.get_secret('database/credentials')
    
    def get_jwt_secret(self) -> str:
        """Get JWT secret key."""
        secret = self.get_secret('jwt/secret')
        return secret['key']
```

**Learning Exercise**: Test secrets

Create `backend/secrets/test_secrets.py`:

```python
from secrets_manager import SecretsManager
import os

# Set environment for local provider
os.environ['SECRETS_PROVIDER'] = 'local'
os.environ['SECRETS_FILE'] = '/tmp/test_secrets.enc'
os.environ['MASTER_PASSWORD'] = 'test-password-123'

# Initialize manager
manager = SecretsManager()

# Store a secret
manager._provider.set_secret('test/secret', {
    'api_key': 'abc123',
    'url': 'https://api.example.com'
})

# Retrieve secret
secret = manager.get_secret('test/secret')
print(f"Retrieved secret: {secret}")

# Check file is encrypted
with open('/tmp/test_secrets.enc', 'rb') as f:
    contents = f.read()
    print(f"\nEncrypted file contents (first 50 bytes):")
    print(contents[:50])
    print("\n⚠️ Notice: Can't read plaintext! File is encrypted.")
```

---

This guide continues for ALL components. Would you like me to continue with more parts covering GitLab integration, services, frontend, and deployment?
