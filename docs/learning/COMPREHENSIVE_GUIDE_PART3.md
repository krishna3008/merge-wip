# Merge Assist - Comprehensive Guide Part 3
## Configuration, GitLab Integration, and API Patterns

*Continuation from Part 2*

---

## 5. Part 4: Configuration Management

### Learning Objectives
- Understand configuration vs. secrets
- Implement environment-based config
- Use Pydantic for validation

### 5.1: Why Pydantic for Configuration?

**Traditional config** (error-prone ❌):
```python
import os

DB_HOST = os.getenv('DB_HOST')  # Could be None!
DB_PORT = int(os.getenv('DB_PORT'))  # Crashes if not set!
BATCH_SIZE = os.getenv('BATCH_SIZE', '5')  # String, not int!
```

**Problems**:
- ❌ No type validation
- ❌ Errors discovered at runtime
- ❌ No default values (or string defaults for int fields)
- ❌ Missing required fields go unnoticed

**Pydantic config** (type-safe ✅):
```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    db_host: str  # Required, must be string
    db_port: int = 5432  # Optional, defaults to 5432
    batch_size: int = 5  # Auto-converted from string "5"
```

**Benefits**:
- ✅ Type validation at startup
- ✅ Clear defaults
- ✅ IDE autocomplete
- ✅ Fails fast if config is invalid

**Example error catching**:

```python
# .env file
DB_PORT=abc  # Invalid!

# Pydantic raises error at startup:
ValidationError: value is not a valid integer
```

### 5.2: Implement Configuration System

Create `backend/config/config.py`:

```python
"""
Configuration management with Pydantic.
"""
from pydantic import BaseSettings, Field, validator
from typing import Optional, List
import os


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    Pydantic automatically:
    - Reads from environment variables
    - Converts types (string "5432" → int 5432)
    - Validates values
    - Provides defaults
    """
    
    # Database configuration
    database_url: Optional[str] = None
    db_host: str = Field(default='localhost', env='DB_HOST')
    db_port: int = Field(default=5432, env='DB_PORT')
    db_user: str = Field(default='merge_assist', env='DB_USER')
    db_password: str = Field(default='password', env='DB_PASSWORD')
    db_name: str = Field(..., env='DB_NAME')  # ... means required!
    
    # Redis configuration
    redis_url: Optional[str] = None
    redis_host: str = 'localhost'
    redis_port: int = 6379
    redis_password: Optional[str] = None
    
    # GitLab configuration
    gitlab_url: str = 'https://gitlab.com'
    gitlab_api_version: str = 'v4'
    
    # Application configuration
    app_name: str = 'Merge Assist'
    debug: bool = False
    log_level: str = 'INFO'
    
    # Service configuration
    watcher_polling_interval: int = 300  # 5 minutes in seconds
    listener_port: int = 8000
    worker_check_interval: int = 60  # 1 minute
    
    # Batch merge configuration
    default_batch_size: int = 5
    max_batch_size: int = 10
    
    # JWT configuration
    jwt_secret_key: str = Field(..., env='JWT_SECRET_KEY')  # Required!
    jwt_algorithm: str = 'HS256'
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Frontend configuration
    frontend_url: str = 'http://localhost:3000'
    
    @validator('database_url', always=True)
    def build_database_url(cls, v, values):
        """
        Build database URL from components if not provided.
        
        Why validator?
        - DRY: Don't repeat URL construction
        - Flexibility: Can provide full URL or components
        """
        if v:
            return v
        
        return (
            f"postgresql://{values['db_user']}:{values['db_password']}"
            f"@{values['db_host']}:{values['db_port']}/{values['db_name']}"
        )
    
    @validator('redis_url', always=True)
    def build_redis_url(cls, v, values):
        """Build Redis URL from components."""
        if v:
            return v
        
        password = values.get('redis_password')
        if password:
            return f"redis://:{password}@{values['redis_host']}:{values['redis_port']}/0"
        else:
            return f"redis://{values['redis_host']}:{values['redis_port']}/0"
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """
        Ensure log level is valid.
        
        Why validator?
        - Catches typos (DEBGU → raises error)
        - Lists valid options
        """
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'log_level must be one of {valid_levels}')
        return v.upper()
    
    class Config:
        """
        Pydantic configuration.
        
        env_file: Load from .env file
        case_sensitive: DB_HOST != db_host
        """
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False


class ProjectConfig:
    """
    Per-project configuration stored in database.
    
    Why separate from Settings?
    - Settings: Global app config (same for all projects)
    - ProjectConfig: Per-project settings (different for each project)
    """
    
    def __init__(self, project_id: str, db_session):
        """Load project configuration from database."""
        from backend.database.models import ProjectConfig as DBProjectConfig
        
        db_config = db_session.query(DBProjectConfig).filter(
            DBProjectConfig.project_id == project_id
        ).first()
        
        if not db_config:
            # Use defaults
            db_config = DBProjectConfig(project_id=project_id)
            db_session.add(db_config)
            db_session.commit()
        
        self.project_id = project_id
        self.batch_size = db_config.batch_size
        self.labels = self._parse_labels(db_config.labels)
    
    def _parse_labels(self, labels_json: dict) -> dict:
        """Parse labels from JSON."""
        return labels_json or {
            'ready_to_merge': 'Ready-To-Merge',
            'not_ready': 'Not-Ready',
            'batch_merge': 'Batch-Merge',
            'rejected': 'Rejected'
        }


class ConfigManager:
    """
    Singleton config manager.
    
    Why singleton?
    - Settings loaded once at startup
    - Same settings across entire app
    """
    _instance = None
    _settings: Optional[Settings] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def settings(self) -> Settings:
        """Get global settings."""
        if self._settings is None:
            self._settings = Settings()
        return self._settings
    
    def load_project_config(self, project_id: str, db_session) -> ProjectConfig:
        """Load configuration for a specific project."""
        return ProjectConfig(project_id, db_session)


# Global config manager instance
config_manager = ConfigManager()
```

**Key concepts explained**:

**Field with ellipsis (...)** means REQUIRED:
```python
db_name: str = Field(...)  # Must be provided!
db_host: str = Field(default='localhost')  # Optional, has default
```

**Validators** run custom validation logic:
```python
@validator('log_level')
def validate_log_level(cls, v):
    if v not in ['DEBUG', 'INFO']:
        raise ValueError('Invalid log level')
    return v
```

**Learning Exercise**: Test configuration

Create `.env` file:
```bash
DB_NAME=merge_assist
DB_PASSWORD=secret123
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
```

Test config:
```python
from config import config_manager

settings = config_manager.settings
print(f"Database URL: {settings.database_url}")
print(f"Redis URL: {settings.redis_url}")
print(f"Log Level: {settings.log_level}")
print(f"Batch Size: {settings.default_batch_size}")
```

---

## 6. Part 5: GitLab API Integration

### Learning Objectives
- Understand REST API patterns
- Implement dual client strategy
- Handle rate limiting and retries
- Use Pydantic for API validation

### 6.1: Why Dual Client Approach?

**Challenge**: GitLab API is complex with 100+ endpoints.

**Option 1**: Use python-gitlab library
- ✅ High-level abstractions
- ✅ Handles pagination, auth
- ❌ Limited control
- ❌ Bugs affect our app

**Option 2**: Custom HTTP client with aiohttp
- ✅ Full control
- ✅ Custom retry logic
- ❌ Must implement everything
- ❌ More code to maintain

**Our solution**: Both!
```
┌─────────────────────────────────┐
│     GitLabUnified (Facade)      │
│  Single interface for all calls │
└────────────┬────────────────────┘
             │
     ┌───────┴────────┐
     │                │
┌────▼─────┐    ┌────▼────────┐
│ Custom   │    │  Library    │
│ Client   │    │  Client     │
└──────────┘    └─────────────┘
```

**Strategy**:
1. Try custom client first (preferred)
2. If fails, fallback to library client
3. Best of both worlds!

### 6.2: Pydantic Models for GitLab Data

**Why Pydantic models for API responses?**

**Without validation** (risky ❌):
```python
mr_data = await api.get('/merge_requests/123')
title = mr_data['title']  # KeyError if field missing!
iid = mr_data['iid']  # Could be string, not int!
```

**With Pydantic** (safe ✅):
```python
mr = MergeRequest(**mr_data)
title = mr.title  # Guaranteed to exist and be string
iid = mr.iid  # Guaranteed to be int
```

Create `backend/gitlab_integration/gitlab_models.py`:

```python
"""
Pydantic models for GitLab API entities.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime


class GitLabUser(BaseModel):
    """GitLab user model."""
    id: int
    username: str
    name: str
    email: Optional[str] = None
    
    class Config:
        """Allow extra fields from API."""
        extra = 'allow'


class MergeRequest(BaseModel):
    """
    GitLab Merge Request model.
    
    Maps API response to typed Python object.
    """
    id: int
    iid: int  # Internal ID (used in URLs: !123)
    title: str
    description: Optional[str] = None
    state: str  # opened, closed, merged
    source_branch: str
    target_branch: str
    author: GitLabUser
    assignee: Optional[GitLabUser] = None
    created_at: datetime
    updated_at: datetime
    merged_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    
    # Status fields
    work_in_progress: bool = False
    has_conflicts: bool = False
    blocking_discussions_resolved: bool = True
    
    # Pipeline
    pipeline: Optional[dict] = None
    head_pipeline: Optional[dict] = None
    
    # Helpers
    def is_wip(self) -> bool:
        """Check if MR is work in progress."""
        return (
            self.work_in_progress or
            self.title.upper().startswith('WIP:') or
            self.title.upper().startswith('[WIP]') or
            self.title.upper().startswith('DRAFT:')
        )
    
    def has_pipeline_passed(self) -> bool:
        """Check if latest pipeline passed."""
        pipeline = self.head_pipeline or self.pipeline
        if not pipeline:
            return False
        return pipeline.get('status') == 'success'
    
    class Config:
        extra = 'allow'  # GitLab API might add new fields


class Pipeline(BaseModel):
    """GitLab CI/CD Pipeline."""
    id: int
    status: str  # pending, running, success, failed, canceled
    ref: str  # Branch name
    sha: str  # Commit SHA
    created_at: datetime
    updated_at: datetime
    
    def is_finished(self) -> bool:
        """Check if pipeline has finished."""
        return self.status in ['success', 'failed', 'canceled', 'skipped']
    
    def is_successful(self) -> bool:
        """Check if pipeline succeeded."""
        return self.status == 'success'
```

**Why helper methods?**
- Encapsulate logic: `mr.is_wip()` is clearer than checking multiple conditions
- DRY: Logic in one place, not repeated everywhere
- Testable: Can unit test `is_wip()` independently

### 6.3: Custom HTTP Client with Retry Logic

Create `backend/gitlab_integration/gitlab_custom_client.py`:

```python
"""
Custom GitLab API client using aiohttp.
"""
import aiohttp
import asyncio
import logging
from typing import Optional, List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class GitLabCustomClient:
    """
    Custom GitLab API client with fine-grained control.
    
    Why aiohttp?
    - Async/await support (non-blocking I/O)
    - Connection pooling
    - Timeout support
    - Full control over requests
    """
    
    def __init__(self, base_url: str, private_token: str, api_version: str = 'v4'):
        """
        Initialize GitLab client.
        
        Args:
            base_url: GitLab instance URL (e.g., 'https://gitlab.com')
            private_token: Personal access token
            api_version: API version (default: v4)
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api/{api_version}"
        self.headers = {
            'PRIVATE-TOKEN': private_token,
            'Content-Type': 'application/json'
        }
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session.
        
        Why reuse session?
        - Connection pooling (faster subsequent requests)
        - Keeps TCP connections alive
        - Reduces overhead
        """
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self.session
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic.
        
        Why retry with exponential backoff?
        - Network is unreliable (transient errors happen)
        - GitLab might be temporarily unavailable
        - Rate limiting (429 errors)
        
        Retry strategy:
        - Attempt 1: Immediate
        - Attempt 2: Wait 2 seconds
        - Attempt 3: Wait 4 seconds
        - Attempt 4: Wait 8 seconds (max 10s)
        
        Example:
            Request fails → Wait 2s → Retry
            Still fails → Wait 4s → Retry
            Still fails → Wait 8s → Retry
            Still fails → Raise exception
        """
        session = await self._get_session()
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        async with session.request(method, url, **kwargs) as response:
            # Log request
            logger.debug(f"{method} {url} → {response.status}")
            
            # Handle rate limiting
            if response.status == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"Rate limited. Waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                raise Exception("Rate limited, retry")
            
            # Raise for 4xx/5xx errors
            response.raise_for_status()
            
            # Parse JSON response
            return await response.json()
    
    async def get_merge_request(
        self,
        project_id: int,
        mr_iid: int
    ) -> Dict[str, Any]:
        """
        Get a specific merge request.
        
        Args:
            project_id: GitLab project ID
            mr_iid: Merge request internal ID (the !123 number)
        
        Returns:
            MR data as dictionary
        
        API: GET /projects/:id/merge_requests/:mr_iid
        """
        endpoint = f"projects/{project_id}/merge_requests/{mr_iid}"
        return await self._request('GET', endpoint)
    
    async def get_merge_requests(
        self,
        project_id: int,
        state: str = 'opened',
        **filters
    ) -> List[Dict[str, Any]]:
        """
        List merge requests for a project.
        
        Args:
            project_id: GitLab project ID
            state: 'opened', 'closed', 'merged', 'all'
            **filters: Additional filters (assignee_id, labels, etc.)
        
        Returns:
            List of MR dictionaries
        
        API: GET /projects/:id/merge_requests
        """
        endpoint = f"projects/{project_id}/merge_requests"
        params = {'state': state, **filters}
        return await self._request('GET', endpoint, params=params)
    
    async def merge_mr(
        self,
        project_id: int,
        mr_iid: int,
        merge_commit_message: Optional[str] = None,
        should_remove_source_branch: bool = True
    ) -> Dict[str, Any]:
        """
        Merge a merge request.
        
        Args:
            project_id: GitLab project ID
            mr_iid: MR internal ID
            merge_commit_message: Custom commit message
            should_remove_source_branch: Delete branch after merge
        
        API: PUT /projects/:id/merge_requests/:mr_iid/merge
        """
        endpoint = f"projects/{project_id}/merge_requests/{mr_iid}/merge"
        data = {
            'should_remove_source_branch': should_remove_source_branch
        }
        if merge_commit_message:
            data['merge_commit_message'] = merge_commit_message
        
        return await self._request('PUT', endpoint, json=data)
    
    async def rebase_mr(
        self,
        project_id: int,
        mr_iid: int
    ) -> Dict[str, Any]:
        """
        Rebase a merge request.
        
        Why rebase before merge?
        - Ensures MR is up-to-date with target branch
        - Prevents merge conflicts
        - Creates linear history
        
        API: PUT /projects/:id/merge_requests/:mr_iid/rebase
        """
        endpoint = f"projects/{project_id}/merge_requests/{mr_iid}/rebase"
        return await self._request('PUT', endpoint)
    
    async def add_label(
        self,
        project_id: int,
        mr_iid: int,
        label: str
    ) -> Dict[str, Any]:
        """
        Add a label to an MR.
        
        API: PUT /projects/:id/merge_requests/:mr_iid
        """
        # First get current labels
        mr = await self.get_merge_request(project_id, mr_iid)
        current_labels = mr.get('labels', [])
        
        if label not in current_labels:
            current_labels.append(label)
        
        endpoint = f"projects/{project_id}/merge_requests/{mr_iid}"
        return await self._request('PUT', endpoint, json={'labels': ','.join(current_labels)})
    
    async def add_comment(
        self,
        project_id: int,
        mr_iid: int,
        comment_body: str
    ) -> Dict[str, Any]:
        """
        Add a comment to an MR.
        
        API: POST /projects/:id/merge_requests/:mr_iid/notes
        """
        endpoint = f"projects/{project_id}/merge_requests/{mr_iid}/notes"
        return await self._request('POST', endpoint, json={'body': comment_body})
    
    async def close(self):
        """Close aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
```

**Key concepts explained**:

**Async/await**: Non-blocking I/O

**Synchronous** (blocks):
```python
response1 = requests.get(url1)  # Wait 200ms
response2 = requests.get(url2)  # Wait 200ms
response3 = requests.get(url3)  # Wait 200ms
# Total: 600ms
```

**Asynchronous** (concurrent):
```python
task1 = aiohttp.get(url1)  # Start immediately
task2 = aiohttp.get(url2)  # Start immediately
task3 = aiohttp.get(url3)  # Start immediately
results = await asyncio.gather(task1, task2, task3)  # Wait for all
# Total: 200ms (3x faster!)
```

**Exponential backoff**: Wait longer after each failure
- Prevents overwhelming server during outage
- Gives server time to recover
- Standard practice in distributed systems

---

This continues! Would you like me to create the remaining parts covering Worker POD detailed implementation, frontend step-by-step, and Kubernetes deployment?
