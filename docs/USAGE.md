# Merge Assist - Usage Guide

## 📖 Complete Usage Instructions

This guide covers how to use Merge Assist in production.

---

## Table of Contents

1. [Initial Setup](#initial-setup)
2. [User Management](#user-management)
3. [Project Configuration](#project-configuration)
4. [Using the System](#using-the-system)
5. [Monitoring & Troubleshooting](#monitoring--troubleshooting)
6. [API Reference](#api-reference)

---

## Initial Setup

### 1. Create Admin User

First time setup requires creating an admin user via database:

```bash
# Connect to PostgreSQL
psql -h <DB_HOST> -U merge_assist -d merge_assist

# Create admin user
INSERT INTO users (username, email, password_hash, is_active)
VALUES (
    'admin',
    'admin@yourcompany.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyWnFkUEPGy2',  -- Password: admin123
    true
);

# Create admin role
INSERT INTO roles (name, description)
VALUES ('admin', 'Full system access');

# Assign admin role
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.username = 'admin' AND r.name = 'admin';
```

**⚠️ IMPORTANT**: Change the default password immediately after first login!

### 2. Configure GitLab Integration

#### Option A: AWS Secrets Manager (Production)

```bash
# Store GitLab token in AWS Secrets Manager
aws secretsmanager create-secret \
    --name merge-assist/gitlab/project/12345 \
    --secret-string '{"token":"glpat-your-token-here"}'

# Store Merge Assist user ID
aws secretsmanager create-secret \
    --name merge-assist/gitlab/merge_assist_user_id \
    --secret-string '{"user_id":"67890"}'
```

#### Option B: Local Encrypted File (Development)

```bash
# Set master password
export MASTER_PASSWORD="your-secure-master-password"

# Run Python script to store secrets
python << EOF
from backend.secrets.secrets_manager import SecretsManager
import os

os.environ['SECRETS_PROVIDER'] = 'local'
os.environ['SECRETS_FILE'] = '/app/secrets/local_secrets.enc'
os.environ['MASTER_PASSWORD'] = os.getenv('MASTER_PASSWORD')

manager = SecretsManager()
manager.initialize()

# Store GitLab token
manager._provider.set_secret('gitlab/project/12345', {
    'token': 'glpat-your-token-here'
})

# Store Merge Assist user ID
manager._provider.set_secret('gitlab/merge_assist_user_id', {
    'user_id': '67890'
})
EOF
```

### 3. Configure GitLab Webhooks

For each project you want to manage:

1. Go to **Settings → Webhooks** in GitLab
2. Create webhook with URL: `https://your-listener-url/webhook/gitlab`
3. Select events:
   - ✅ Merge request events
   - ✅ Pipeline events
4. Save webhook

---

## User Management

### Creating Users

**Via API** (requires admin role):

```bash
curl -X POST https://your-api-url/users \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe",
    "email": "john@example.com",
    "password": "SecurePassword123",
    "roles": ["project_owner"]
  }'
```

**Via Database**:

```sql
-- Create user
INSERT INTO users (username, email, password_hash)
VALUES ('johndoe', 'john@example.com', '<bcrypt_hash>');

-- Assign role
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.username = 'johndoe' AND r.name = 'project_owner';
```

### Role Permissions

| Role | Permissions |
|------|-------------|
| **Admin** | Full access to everything |
| **Project Owner** | Manage assigned projects, view logs |
| **Priority Manager** | View projects, adjust MR priorities |
| **Viewer** | Read-only access to projects and status |

---

## Project Configuration

### 1. Add New Project

```bash
# Via API
curl -X POST https://your-api-url/projects \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Project",
    "gitlab_id": 12345,
    "gitlab_url": "https://gitlab.com/myorg/myproject",
    "is_active": true
  }'
```

### 2. Configure Project Settings

```bash
# Set batch size and labels
curl -X PUT https://your-api-url/projects/PROJECT_UUID/config \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 5,
    "labels": {
      "ready_to_merge": "Ready-To-Merge",
      "not_ready": "Not-Ready",
      "batch_merge": "Batch-Merge",
      "rejected": "Rejected"
    }
  }'
```

### 3. Deploy Worker POD

After adding a project, deploy its Worker POD:

```bash
# Kubernetes
sed 's/PROJECT_ID/<actual-uuid>/g; s/PROJECT_NAME/<project-name>/g' \
  k8s/worker-template.yaml | kubectl apply -f -

# Docker
docker run -d \
  --name worker-<project-name> \
  -e PROJECT_ID=<actual-uuid> \
  --env-file .env \
  merge-assist/worker:latest \
  <actual-uuid>
```

---

## Using the System

### Workflow Overview

```
┌─────────────────────────────────────────────────────┐
│  1. Developer creates MR in GitLab                  │
│  2. Assigns MR to "Merge Assist" user              │
└──────────────────┬──────────────────────────────────┘
                   │
      ┌────────────▼─────────────┐
      │  Watcher (polls) OR      │
      │  Listener (webhook)      │
      │  discovers new MR        │
      └────────────┬─────────────┘
                   │
         ┌─────────▼──────────┐
         │  Worker POD        │
         │  validates MR:     │
         │  - Pipeline pass?  │
         │  - Approvals?      │
         │  - Conflicts?      │
         │  - WIP status?     │
         └─────────┬──────────┘
                   │
       ┌───────────▼────────────┐
       │  Ready?                │
       ├───────────┬────────────┤
       │  YES      │    NO      │
       │           │            │
       │  Add      │  Add label │
       │  "Ready"  │  + comment │
       │  label    │            │
       └─────┬─────┴────────────┘
             │
    ┌────────▼─────────┐
    │ Batch decision   │
    │ >=5 ready MRs?   │
    ├─────┬──────┬─────┤
    │ YES │      │ NO  │
    │     │      │     │
    │Batch│      │Single
    │merge│      │merge│
    └─────┴──────┴─────┘
```

### Merge Request Lifecycle

1. **Recognized**: MR discovered, added to database
2. **Validated**: Checks passed, labeled "Ready-To-Merge"
3. **Queued**: Waiting for merge opportunity
4. **Rebasing**: Being updated with target branch
5. **Merging**: Merge in progress
6. **Merged**: Successfully merged ✅
7. **Rejected**: Failed 3 validation attempts ❌

### Single MR Merge

When < 5 MRs are ready:

```
1. Rebase MR with target branch
2. Wait for pipeline to run (max 30 minutes)
3. If pipeline passes → Merge
4. If pipeline fails → Add comment, increment rejection count
```

### Batch Merge (5 MRs)

When ≥ 5 MRs are ready:

```
1. Create batch branch (batch-merge-YYYYMMDD-HHMMSS)
2. Merge all 5 MRs into batch branch (skip CI)
3. Push batch branch → Triggers ONE pipeline
4. If pipeline passes:
   a. Rebase each MR individually
   b. Wait for its pipeline
   c. Merge if passes
5. If pipeline fails:
   - Identify failing MR (manual or bisect)
   - Remove from batch
   - Retry with remaining MRs
```

**Benefit**: Test 5 MRs with 1 pipeline instead of 5 separate pipelines!

### Adjusting MR Priority

Priority Managers can reorder the merge queue:

```bash
curl -X POST https://your-api-url/mrs/MR_UUID/priority \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"new_priority": 1}'  # Higher number = higher priority
```

---

## Monitoring & Troubleshooting

### View Logs

**Via API**:

```bash
# All logs
curl https://your-api-url/logs \
  -H "Authorization: Bearer YOUR_TOKEN"

# Project-specific logs
curl 'https://your-api-url/logs?project_id=PROJECT_UUID&limit=100' \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Via Kubernetes**:

```bash
# API Gateway logs
kubectl logs -n merge-assist -l app=api-gateway --tail=100

# Worker POD logs
kubectl logs -n merge-assist -l app=worker,project=my-project --tail=100

# Watcher logs
kubectl logs -n merge-assist -l app=watcher --tail=100

# Listener logs
kubectl logs -n merge-assist -l app=listener --tail=100
```

### Health Checks

```bash
# API Gateway
curl https://your-api-url/health

# Listener
curl https://your-listener-url/health

# Check all pods
kubectl get pods -n merge-assist
```

### Common Issues

#### MR Not Being Picked Up

**Symptoms**: MR assigned to Merge Assist but no action

**Checks**:
1. Verify MR is assigned to correct user ID
2. Check Watcher logs: `kubectl logs -l app=watcher`
3. Verify GitLab webhook is configured
4. Check Listener logs for webhook events

**Solution**:
```bash
# Verify Merge Assist user ID
curl https://gitlab.com/api/v4/user \
  -H "PRIVATE-TOKEN: your-token"

# Check webhook deliveries in GitLab
# Settings → Webhooks → Recent Deliveries
```

#### MR Stuck in "Ready" Status

**Symptoms**: MR labeled "Ready-To-Merge" but not merging

**Checks**:
1. Check Worker POD logs: `kubectl logs -l project=<name>`
2. Verify pipeline passed
3. Check for merge conflicts

**Solution**:
```bash
# Manually trigger merge check
curl -X POST https://your-api-url/admin/trigger-check \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -d '{"mr_id": "MR_UUID"}'
```

#### Pipeline Timeout

**Symptoms**: MR stuck waiting for pipeline

**Issue**: Pipeline taking > 30 minutes

**Solution**:
- Increase timeout in Worker POD config
- Or optimize GitLab CI/CD pipeline

```python
# In worker_pod.py, increase timeout:
pipeline_passed = await self._wait_for_pipeline(
    project_id,
    mr_iid,
    timeout_minutes=60  # Increase from 30 to 60
)
```

---

## API Reference

### Authentication

#### POST /auth/login
Login and receive JWT tokens.

**Request**:
```bash
curl -X POST https://api-url/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

**Response**:
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer"
}
```

#### GET /auth/me
Get current user information.

**Request**:
```bash
curl https://api-url/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Projects

#### GET /projects
List all projects.

**Permissions**: `VIEW_ALL_PROJECTS`

**Response**:
```json
[
  {
    "id": "uuid",
    "name": "Project Name",
    "gitlab_id": 12345,
    "is_active": true
  }
]
```

#### GET /projects/{id}/mrs
List MRs for a project.

**Permissions**: `VIEW_PROJECT`

**Response**:
```json
[
  {
    "id": "uuid",
    "gitlab_mr_iid": 123,
    "title": "Feature: Add new component",
    "status": "ready",
    "target_branch": "main",
    "recognized_at": "2024-01-15T10:30:00Z"
  }
]
```

### Merge Requests

#### POST /mrs/{id}/priority
Set MR priority.

**Permissions**: `SET_MR_PRIORITY`

**Request**:
```bash
curl -X POST https://api-url/mrs/MR_UUID/priority \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"new_priority": 10}'
```

### Logs

#### GET /logs
View system logs.

**Permissions**: `VIEW_LOGS`

**Query Parameters**:
- `project_id`: Filter by project (optional)
- `limit`: Number of log entries (default: 100)

**Response**:
```json
[
  {
    "id": "uuid",
    "level": "INFO",
    "message": "MR !123 merged successfully",
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

---

## Best Practices

### Security

1. **Change default passwords immediately**
2. **Use AWS Secrets Manager in production** (not local encrypted files)
3. **Rotate GitLab tokens** every 90 days
4. **Enable 2FA** for admin accounts
5. **Use strong JWT secret** (>32 characters, random)
6. **Limit API access** via firewall rules

### Performance

1. **Batch size**: 5 MRs is optimal (balance between speed and reliability)
2. **Worker PODs**: One per active project
3. **Watcher interval**: 5 minutes for most projects
4. **Use webhooks** instead of polling when possible (faster, less load)

### Reliability

1. **Monitor health checks** regularly
2. **Set up alerts** for Worker POD failures
3. **Database backups** daily (PostgreSQL)
4. **Redis persistence** enabled (AOF + RDB)
5. **Resource limits** on pods to prevent resource exhaustion

---

## Support & Troubleshooting

### Debug Mode

Enable debug logging:

```bash
# Environment variable
export LOG_LEVEL=DEBUG

# Or in .env file
LOG_LEVEL=DEBUG
```

### Database Queries

```sql
-- Check MR status distribution
SELECT status, COUNT(*) FROM merge_requests GROUP BY status;

-- Find stuck MRs (ready for >1 hour)
SELECT * FROM merge_requests
WHERE status = 'ready'
AND recognized_at < NOW() - INTERVAL '1 hour';

-- Recent activity
SELECT * FROM logs ORDER BY created_at DESC LIMIT 50;
```

### Emergency Actions

**Stop all merges**:
```bash
# Scale down Worker PODs
kubectl scale deployment -n merge-assist -l app=worker --replicas=0
```

**Resume merges**:
```bash
# Scale up Worker PODs
kubectl scale deployment -n merge-assist -l app=worker --replicas=1
```

---

## Appendix

### Useful Commands

```bash
# View all pods
kubectl get pods -n merge-assist

# Restart service
kubectl rollout restart deployment/api-gateway -n merge-assist

# View pod resources
kubectl top pods -n merge-assist

# Access database
kubectl exec -it postgres-0 -n merge-assist -- psql -U merge_assist

# Check HPA status
kubectl get hpa -n merge-assist
```

### Configuration Files

- `.env`: Environment variables
- `k8s/*.yaml`: Kubernetes manifests
- `docker-compose.yml`: Local development
- `requirements.txt`: Python dependencies

---

*For technical implementation details, see the Comprehensive Learning Guides in `docs/learning/`.*
