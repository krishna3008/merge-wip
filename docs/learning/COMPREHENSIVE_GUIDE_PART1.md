# Merge Assist - Complete Step-by-Step Rebuild Guide

## 🎯 Purpose of This Guide

This guide will teach you how to build Merge Assist—a production-ready GitLab MR automation tool—**completely from scratch**. You'll understand not just HOW to build each component, but **WHY** each technology and pattern was chosen.

By the end, you'll have mastered:
- **Database design** for multi-tenant SaaS applications
- **JWT authentication** and role-based access control (RBAC)
- **Secrets management** for production environments
- **Microservices architecture** with Python and FastAPI
- **GitLab API integration** with dual client strategy
- **React frontend** with TypeScript
- **Kubernetes deployment** on AWS EKS

---

## 📚 Table of Contents

1. [Prerequisites & Setup](#1-prerequisites--setup)
2. [Part 1: Database Foundation](#2-part-1-database-foundation)
3. [Part 2: Authentication System](#3-part-2-authentication-system)
4. [Part 3: Secrets Management](#4-part-3-secrets-management)
5. [Part 4: Configuration Management](#5-part-4-configuration-management)
6. [Part 5: GitLab API Integration](#6-part-5-gitlab-api-integration)
7. [Part 6: Worker POD - Validation & Merge Logic](#7-part-6-worker-pod---validation--merge-logic)
8. [Part 7: Watcher & Listener Services](#8-part-7-watcher--listener-services)
9. [Part 8: API Gateway](#9-part-8-api-gateway)
10. [Part 9: Frontend Dashboard](#10-part-9-frontend-dashboard)
11. [Part 10: Docker & Kubernetes](#11-part-10-docker--kubernetes)
12. [Testing Strategy](#12-testing-strategy)
13. [Production Deployment](#13-production-deployment)

---

## 1. Prerequisites & Setup

### Why These Prerequisites?

Before building any application, you need to understand the tools and environment. Here's why each tool is essential:

**Python 3.10+**: Modern Python with type hints, async/await, and performance improvements  
**PostgreSQL 13+**: Robust ACID-compliant database for mission-critical data  
**Redis 7**: High-performance in-memory database for pub/sub and caching  
**Docker**: Ensures consistent environment across development and production  
**Node.js 18+**: For the React frontend build tools  

### Installation Steps

#### Step 1.1: Install Python 3.10

**Why Python?** Python is ideal for backend development due to:
- Extensive libraries for web frameworks (FastAPI), database access (SQLAlchemy), and API clients
- Strong async/await support for I/O-bound operations (GitLab API calls)
- Easy to read and maintain
- Great for DevOps automation

```bash
# macOS
brew install python@3.10

# Ubuntu
sudo apt update
sudo apt install python3.10 python3.10-venv python3.10-dev

# Verify
python3.10 --version  # Should show Python 3.10.x
```

#### Step 1.2: Install PostgreSQL

**Why PostgreSQL over MySQL/SQLite?**
- **ACID compliance**: Guarantees data integrity (critical for merge operations)
- **JSON support**: JSONB columns for flexible configuration storage
- **Mature**: Battle-tested in production for decades
- **Advanced features**: Partial indexes, triggers, foreign keys

```bash
# macOS
brew install postgresql@13
brew services start postgresql@13

# Ubuntu
sudo apt install postgresql-13 postgresql-contrib-13
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database
createdb merge_assist

# Verify
psql -c "SELECT version();"
```

**Learning Checkpoint**: What is ACID?
- **A**tomicity: All operations in a transaction succeed or all fail
- **C**onsistency: Data is always in a valid state
- **I**solation**: Concurrent transactions don't interfere
- **D**urability: Committed data survives crashes

#### Step 1.3: Install Redis

**Why Redis?**
- **Pub/Sub**: Perfect for event distribution to Worker PODs
- **Speed**: In-memory = microsecond latency
- **Simple**: Easy to set up and use
- **Reliable**: Battle-tested message broker

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis

# Test connection
redis-cli ping  # Should return PONG
```

#### Step 1.4: Install Node.js

**Why Node.js for a Python backend project?**
- Frontend build tools (React, TypeScript) run on Node.js
- npm is the standard package manager for JavaScript/TypeScript
- Webpack, Babel, ESLint all require Node.js

```bash
# macOS
brew install node@18

# Ubuntu
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify
node --version  # Should show v18.x
npm --version
```

#### Step 1.5: Install Docker

**Why Docker?**
- **Consistency**: "Works on my machine" → "Works everywhere"
- **Isolation**: Each service runs in its own container
- **Easy deployment**: Build once, deploy anywhere
- **Local development**: Replicate production environment locally

```bash
# macOS: Download Docker Desktop from docker.com
# Ubuntu
sudo apt-get update
sudo apt-get install docker.io docker-compose
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER  # Add yourself to docker group

# Verify
docker --version
docker-compose --version
```

#### Step 1.6: Set Up Project Directory

```bash
mkdir -p merge-assist-from-scratch
cd merge-assist-from-scratch

# Create directory structure
mkdir -p backend/{database,auth,secrets,config,gitlab_integration,services/{watcher,listener,worker},api,tests}
mkdir -p frontend/src/components
mkdir -p k8s terraform docs tests

# Create Python virtual environment
python3.10 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Create requirements.txt (we'll populate this as we go)
touch requirements.txt
```

**Why this structure?**
- **Separation of concerns**: Each directory has a single responsibility
- **Scalability**: Easy to add new services
- **Clarity**: Anyone can understand the project layout instantly

---

## 2. Part 1: Database Foundation

### Learning Objectives
- Understand database schema design
- Learn normalization and indexing
- Master SQLAlchemy ORM
- Implement database connection management

### 2.1: Understanding the Data Model

**Question**: What data do we need to store?

**Answer**: For an MR automation tool, we need:
1. **Users**: Who can access the system?
2. **Roles**: What permissions do users have?
3. **Projects**: Which GitLab projects are managed?
4. **MRs**: Track all merge requests being processed
5. **Audit logs**: Who did what and when?

### 2.2: Design the Database Schema

**Why start with schema design?**
- Data is the foundation of any application
- Bad schema = performance problems later
- Easier to change code than to migrate data in production

#### Step 2.2.1: Users Table

Create `backend/database/schema.sql`:

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Why UUID for primary keys?**
- **Globally unique**: Can merge databases without ID conflicts
- **Security**: Harder to guess sequential IDs
- **Distributed systems**: Generate IDs without coordinating with database

**Why VARCHAR(100) for username?**
- Most usernames are short (5-20 chars)
- 100 gives headroom for edge cases
- Fixed length would waste space (CHAR vs VARCHAR)

**Why separate password_hash instead of password?**
- **NEVER store plaintext passwords!**
- If database is breached, passwords are still safe (hashed with bcrypt)

**Why TIMESTAMP WITH TIME ZONE?**
- Application might be used globally
- Converts to user's local timezone automatically
- Avoids daylight saving time bugs

**Learning Exercise**: What happens if you use TIMESTAMP without time zone?
❌ Bad: 2PM in New York is stored as 2PM in Tokyo
✅ Good: 2PM EST is stored as UTC, displayed correctly everywhere

#### Step 2.2.2: Add Indexes

```sql
-- Add indexes for fast lookups
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

**Why indexes?**
- Without index: Database scans ALL rows to find username="john" (O(n))
- With index: Database uses B-tree to find instantly (O(log n))

**Example**: Finding "john" in 1 million users
- No index: ~1 million comparisons
- With index: ~20 comparisons (log₂ 1,000,000 ≈ 20)

**When NOT to index?**
- Small tables (<1000 rows): Index overhead > benefit
- Columns rarely used in WHERE clauses
- Columns with low cardinality (e.g., boolean fields)

#### Step 2.2.3: Auto-Update Timestamps

```sql
-- Function to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for users table
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

**Why triggers instead of application code?**
- **DRY principle**: Don't repeat timestamp logic in every UPDATE query
- **Reliability**: Can't forget to update timestamp
- **Database guarantee**: Even direct SQL updates get correct timestamp

#### Step 2.2.4: Roles and Permissions (Many-to-Many)

```sql
-- Roles table
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- User-Role junction table (many-to-many)
CREATE TABLE user_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role_id)
);

CREATE INDEX idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX idx_user_roles_role_id ON user_roles(role_id);
```

**Why a junction table?**
- User can have multiple roles (admin + project_owner)
- Role can be assigned to multiple users
- Direct foreign keys can't model many-to-many

**Diagram**:
```
Users          User_Roles         Roles
┌────┐         ┌────────┐         ┌─────┐
│ ID │────┐    │user_id │    ┌────│  ID │
│name│    └───▶│role_id │◀───┘    │name │
└────┘         └────────┘         └─────┘
```

**Why ON DELETE CASCADE?**
- If user is deleted, automatically remove their role assignments
- Maintains referential integrity
- Alternative: Set to NULL, but then you have orphaned rows

**Learning Exercise**: Insert sample data

```sql
-- Insert default roles
INSERT INTO roles (name, description) VALUES
('admin', 'Full system access'),
('project_owner', 'Manage specific projects'),
('priority_manager', 'Adjust MR priorities'),
('viewer', 'Read-only access');

-- Create admin user (password: admin123, hashed with bcrypt)
INSERT INTO users (username, email, password_hash) VALUES
('admin', 'admin@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyWnFkUEPGy2');

-- Assign admin role
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.username = 'admin' AND r.name = 'admin';
```

### 2.3: SQLAlchemy ORM Models

**Why use an ORM instead of raw SQL?**
- **Type safety**: Python objects with type hints
- **DRY**: No repeating table definitions
- **Database agnostic**: Switch PostgreSQL ↔ MySQL with config change
- **Relationships**: Automatic JOIN queries
- **Validation**: Catch errors before hitting database

#### Step 2.3.1: Install SQLAlchemy

Add to `requirements.txt`:
```
sqlalchemy==2.0.23
psycopg2-binary==2.9.9  # PostgreSQL driver
alembic==1.12.1  # Database migrations
```

Install:
```bash
pip install -r requirements.txt
```

**Why psycopg2-binary?**
- SQLAlchemy needs a driver to talk to PostgreSQL
- `psycopg2` is the standard Python-PostgreSQL adapter
- `-binary` includes pre-compiled C extensions (faster, easier install)

**Why Alembic?**
- Version control for database schema
- Safe migrations in production
- Rollback capability

#### Step 2.3.2: Create Base Model with Mixin

Create `backend/database/models.py`:

```python
"""
SQLAlchemy ORM models for Merge Assist.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

Base = declarative_base()


class TimestampMixin:
    """
    Mixin to add created_at and updated_at timestamps.
    
    Why a mixin?
    - DRY principle: Don't repeat timestamp columns in every model
    - Consistency: All models have same timestamp behavior
    - Flexibility: Easy to add to any model with inheritance
    """
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
```

**What is a Mixin?**
A mixin is a class that provides methods/attributes to other classes through inheritance.

**Example without mixin** (repetitive ❌):
```python
class User(Base):
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

class Project(Base):
    created_at = Column(DateTime, default=datetime.utcnow)  # Repeated!
    updated_at = Column(DateTime, default=datetime.utcnow)  # Repeated!
```

**Example with mixin** (DRY ✅):
```python
class User(Base, TimestampMixin):
    pass  # Automatically has created_at and updated_at!

class Project(Base, TimestampMixin):
    pass  # Also has timestamps!
```

#### Step 2.3.3: User Model

```python
class User(Base, TimestampMixin):
    """
    User model for authentication and authorization.
    """
    __tablename__ = 'users'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Relationship to roles (many-to-many through user_roles)
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(username='{self.username}', email='{self.email}')>"
```

**Why UUID(as_uuid=True)?**
- `as_uuid=True`: Python receives actual UUID object, not string
- Easier to work with: `user.id` is UUID, not "550e8400..."

**Why index=True on username and email?**
- Login queries: `WHERE username = 'john'`
- Without these indexes, every login scans entire table!

**Why nullable=False?**
- Database-level constraint ensures no NULL values
- Fail fast: Catches bugs immediately rather than silently accepting bad data

**What is back_populates?**
Bidirectional relationship: From User, access roles; from Role, access users.

```python
# Forward: Get roles for a user
user = session.query(User).first()
for ur in user.user_roles:
    print(ur.role.name)

# Backward: Get users with a role
role = session.query(Role).first()
for ur in role.user_roles:
    print(ur.user.username)
```

#### Step 2.3.4: Complete All Models

Continue in `backend/database/models.py`:

```python
class Role(Base, TimestampMixin):
    """Role model for RBAC."""
    __tablename__ = 'roles'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(500))
    
    user_roles = relationship("UserRole", back_populates="role")


class UserRole(Base):
    """Junction table for User-Role many-to-many relationship."""
    __tablename__ = 'user_roles'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)
    assigned_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")
```

**Why assigned_at in junction table?**
- Audit trail: When was this role assigned?
- Useful for billing: "User had admin role from Jan-Mar"

### 2.4: Database Connection Manager

**Why a connection manager?**
- **Single source of truth**: Connection string in one place
- **Session management**: Automatic cleanup
- **Connection pooling**: Reuse connections instead of creating new ones

#### Step 2.4.1: Create Connection Module

Create `backend/database/connection.py`:

```python
"""
Database connection manager with singleton pattern.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
import os


class Database:
    """
    Singleton database connection manager.
    
    Why singleton?
    - One engine per application (not per request)
    - Connection pooling works properly
    - Avoid resource exhaustion
    """
    _instance = None
    _engine = None
    _SessionLocal = None
    
    def __new__(cls):
        """Ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance
    
    def initialize(self, database_url: str = None):
        """
        Initialize database connection.
        
        Args:
            database_url: PostgreSQL connection string
                Format: postgresql://user:password@host:port/dbname
        """
        if self._engine is not None:
            return  # Already initialized
        
        if database_url is None:
            # Build from environment variables
            user = os.getenv('DB_USER', 'merge_assist')
            password = os.getenv('DB_PASSWORD', 'password')
            host = os.getenv('DB_HOST', 'localhost')
            port = os.getenv('DB_PORT', '5432')
            dbname = os.getenv('DB_NAME', 'merge_assist')
            
            database_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        
        # Create engine with connection pooling
        self._engine = create_engine(
            database_url,
            pool_size=10,        # Max 10 connections in pool
            max_overflow=20,     # Allow 20 more if pool exhausted
            pool_pre_ping=True,  # Verify connection before use
            echo=False           # Set True to see SQL queries (debugging)
        )
        
        # Create session factory
        self._SessionLocal = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=self._engine)
        )
    
    @contextmanager
    def get_session(self):
        """
        Context manager for database sessions.
        
        Usage:
            with db.get_session() as session:
                user = session.query(User).first()
        
        Why context manager?
        - Automatic session cleanup
        - Automatic rollback on exceptions
        - Can't forget to close session
        """
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def close(self):
        """Close all database connections."""
        if self._SessionLocal:
            self._SessionLocal.remove()
        if self._engine:
            self._engine.dispose()


# Global database instance
db = Database()
```

**What is connection pooling?**
Creating database connections is expensive (~100ms). Connection pooling reuses existing connections.

**Without pooling**:
```
Request 1: Create connection (100ms) → Query (5ms) → Close
Request 2: Create connection (100ms) → Query (5ms) → Close
Request 3: Create connection (100ms) → Query (5ms) → Close
Total: 315ms
```

**With pooling**:
```
Request 1: Create connection (100ms) → Query (5ms) → Return to pool
Request 2: Reuse connection (0ms) → Query (5ms) → Return to pool
Request 3: Reuse connection (0ms) → Query (5ms) → Return to pool
Total: 115ms (2.7x faster!)
```

**Why pool_pre_ping=True?**
- Database might close idle connections
- Pre-ping checks if connection is still alive
- Automatically reconnects if needed

**Learning Exercise**: Test the connection

Create `backend/database/test_connection.py`:

```python
from connection import db
from models import User, Base

# Initialize database
db.initialize()

# Create tables (in production, use Alembic migrations)
Base.metadata.create_all(db._engine)

# Test query
with db.get_session() as session:
    users = session.query(User).all()
    print(f"Found {len(users)} users")
    for user in users:
        print(f"  - {user.username}: {user.email}")
```

Run it:
```bash
cd backend/database
python test_connection.py
```

---

## 3. Part 2: Authentication System

### Learning Objectives
- Understand JWT (JSON Web Tokens)
- Implement secure password hashing
- Build role-based access control (RBAC)
- Create authentication middleware

### 3.1: Why JWT for Authentication?

**Traditional session-based auth**:
```
User logs in → Server creates session → Stores in Redis/Database
Every request → Server looks up session → Verifies user
```

**Problems**:
- ❌ Server must store session state (not stateless)
- ❌ Harder to scale horizontally (session not shared across servers)
- ❌ Requires session storage (Redis, database)

**JWT-based auth**:
```
User logs in → Server creates signed token → Returns to client
Every request → Client sends token → Server verifies signature
```

**Benefits**:
- ✅ Stateless (token contains all info)
- ✅ Scales horizontally (any server can verify token)
- ✅ No session storage needed

**JWT Structure**:
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTIzIiwiZXhwIjoxNjQwOTk1MjAwfQ.signature

Header (base64)    Payload (base64)       Signature
Algorithm: HS256   user_id: 123           HMACSHA256(
Type: JWT          exp: 1640995200        header + payload,
                                         secret_key)
```

**Why signature?**
- Prevents tampering: Changing payload invalidates signature
- Server verifies signature using secret key
- If signature is invalid → Token was tampered with → Reject

### 3.2: Password Hashing

**Why hash passwords?**
If database is breached, plain passwords are exposed:
```
username | password
---------|----------
john     | MyPassword123  ← Attacker sees this!
alice    | secret456      ← Attacker sees this!
```

With hashing:
```
username | password_hash
---------|----------
john     | $2b$12$LQv3c1yq...  ← Attacker sees gibberish
alice    | $2b$12$xT9vzP2k...  ← Useless without original password
```

**Why bcrypt over MD5/SHA256?**
- **Slow by design**: Takes ~100ms to hash (prevents brute force)
- **Salt included**: Same password → Different hash each time
- **Adaptive**: Can increase iterations as computers get faster

**Example**: Brute forcing 8-character password
- MD5: ~1 billion hashes/second → Cracked in seconds
- bcrypt: ~10 hashes/second → Takes millions of years

#### Step 3.2.1: Install Dependencies

Add to `requirements.txt`:
```
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
python-multipart==0.0.6
```

Install:
```bash
pip install -r requirements.txt
```

**Why these libraries?**
- `passlib`: Password hashing with bcrypt support
- `python-jose`: JWT creation and verification
- `python-multipart`: Parse form data (username/password from login form)

#### Step 3.2.2: Create Authentication Module

Create `backend/auth/auth.py`:

```python
"""
JWT authentication utilities.
"""
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import os

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Example:
        >>> hash_password("MyPassword123")
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyWnFkUEPGy2'
    
    Why bcrypt?
    - Industry standard for password hashing
    - Automatically handles salting
    - Adjustable work factor (current: 12 rounds)
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    Example:
        >>> hashed = hash_password("MyPassword123")
        >>> verify_password("MyPassword123", hashed)
        True
        >>> verify_password("WrongPassword", hashed)
        False
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload data (user_id, username, roles, etc.)
    
    Returns:
        Signed JWT token string
    
    Example:
        >>> token = create_access_token({"user_id": "123", "username": "john"})
        >>> print(token)
        eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    
    Token structure:
        {
            "user_id": "123",
            "username": "john",
            "exp": 1640995200,  # Expiration timestamp
            "type": "access"     # Token type
        }
    """
    to_encode = data.copy()
    
    # Add expiration time
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "type": "access"
    })
    
    # Sign and return token
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    Create a JWT refresh token (longer expiration).
    
    Why separate refresh tokens?
    - Access token: Short-lived (30 min) for API requests
    - Refresh token: Long-lived (7 days) to get new access tokens
    - If access token is stolen, damage is limited to 30 minutes
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> dict:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")
    
    Returns:
        Decoded payload if valid, None if invalid
    
    Why verify token type?
    - Prevents using refresh token as access token
    - Each token should only be used for its intended purpose
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check token type
        if payload.get("type") != token_type:
            return None
        
        return payload
        
    except JWTError:
        return None
```

**Learning Exercise**: Test password hashing

Create `backend/auth/test_auth.py`:

```python
from auth import hash_password, verify_password, create_access_token, verify_token

# Test password hashing
password = "MySecurePassword123"
hashed = hash_password(password)

print(f"Original password: {password}")
print(f"Hashed password: {hashed}")
print(f"Hash length: {len(hashed)} characters")

# Verify correct password
print(f"\nVerify correct password: {verify_password(password, hashed)}")  # True

# Verify wrong password
print(f"Verify wrong password: {verify_password('WrongPassword', hashed)}")  # False

# Test JWT tokens
user_data = {"user_id": "123", "username": "john", "roles": ["admin"]}
access_token = create_access_token(user_data)

print(f"\nAccess token: {access_token[:50]}...")

# Verify token
payload = verify_token(access_token)
print(f"Decoded payload: {payload}")
```

Run it:
```bash
cd backend/auth
python test_auth.py
```

**Expected output**:
```
Original password: MySecurePassword123
Hashed password: $2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyWnFk UEPGy2
Hash length: 60 characters

Verify correct password: True
Verify wrong password: False

Access token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2...
Decoded payload: {'user_id': '123', 'username': 'john', 'roles': ['admin'], 'exp': 1640995200, 'type': 'access'}
```

---

This comprehensive guide continues with detailed explanations for all remaining components. Would you like me to continue with the full guide covering all parts?
