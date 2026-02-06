# Merge Assist - Implementation Plan (Updated)

High-level plan for building a GitLab Merge Request automation tool with authentication, intelligent batching, and comprehensive secrets management.

## User Review Summary ✅

All architectural decisions have been confirmed:

> [!IMPORTANT]
> **Confirmed Architecture**
> - **Microservices**: Separate Watcher, Listener, per-project Workers, Frontend, Health Checker
> - **Auth/Authorization**: JWT + RBAC (admin, project_owner, priority_manager, viewer roles)
> - **Secrets Management**: AWS Secrets Manager (EKS) + encrypted local files (Docker)
> - **Batch Size**: Default 5 MRs, configurable per project, adjustable anytime
> - **Batch Strategy**: Sync batch branch with target, rebase MRs, reject failures with comments
> - **GitLab Integration**: Dual approach (custom client + python-gitlab library)
> - **Webhook Scalability**: HPA for traffic handling, per-project option available
> - **Tech Stack**: Python/FastAPI, React/TS, PostgreSQL, Redis, K8s/EKS, Terraform

---

## Proposed Changes

### Component 1: Authentication & Authorization

JWT-based authentication with role-based access control.

#### [NEW] [auth/auth.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/auth/auth.py)
- JWT token generation and validation
- User authentication logic  
- Password hashing (bcrypt)
- Token refresh mechanism

#### [NEW] [auth/rbac.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/auth/rbac.py)
- Roles: `admin`, `project_owner`, `priority_manager`, `viewer`
- Permission decorators for API endpoints
- Project-level permission checks

#### [NEW] [auth/middleware.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/auth/middleware.py)
- FastAPI authentication middleware
- Token extraction and verification
- User context injection

---

### Component 2: Secrets Management

Centralized secrets handling for all credentials and tokens.

#### [NEW] [secrets/secrets_manager.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/secrets/secrets_manager.py)
- **AWS Secrets Manager** for EKS (production)
- **Local encrypted file** for Docker (development)
- Secrets: GitLab tokens, DB credentials, Redis, AI tokens, JWT keys
- Auto-rotation support
- Environment-based retrieval (dev/staging/prod)

#### [NEW] [secrets/encryption.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/secrets/encryption.py)
- AES-256 encryption for local secrets
- Key derivation from master password (PBKDF2)

---

### Component 3: Database Layer

PostgreSQL database with auth, project configs, MR states, and history.

#### [NEW] [database/schema.sql](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/database/schema.sql)
- Tables: `users`, `roles`, `user_roles`, `projects`, `project_permissions`, `merge_requests`, `merge_history`, `batch_operations`, `logs`, `project_config`
- Indexes for auth queries and MR lookups

#### [NEW] [database/models.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/database/models.py)
- SQLAlchemy ORM models
- Base model class for DRY (timestamps, soft delete)
- Relationship mappings

#### [NEW] [database/migrations/](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/database/migrations/)
- Alembic migration scripts

---

### Component 4: GitLab API Integration (Dual Approach)

Custom + library-based clients for comprehensive GitLab operations.

#### [NEW] [gitlab_integration/gitlab_custom_client.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/gitlab_integration/gitlab_custom_client.py)
- Custom HTTP-based GitLab API client
- Methods: `get_mrs_for_user()`, `get_mr_details()`, `check_pipeline_status()`, `rebase_mr()`, `merge_mr()`, `add_label()`, `remove_label()`, `add_comment()`
- Retry logic and rate limiting

#### [NEW] [gitlab_integration/gitlab_library_client.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/gitlab_integration/gitlab_library_client.py)
- Client using python-gitlab library
- Fallback for complex operations
- Official API coverage

#### [NEW] [gitlab_integration/gitlab_unified.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/gitlab_integration/gitlab_unified.py)
- Unified facade for both clients
- Automatic fallback on errors
- Operation-based client selection

#### [NEW] [gitlab_integration/gitlab_models.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/gitlab_integration/gitlab_models.py)
- Pydantic models for GitLab entities (MR, Pipeline, Project)

---

### Component 5: Configuration Management

Multi-project configuration with runtime updates.

#### [NEW] [config/config.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/config/config.py)
- Environment-based settings (dev/staging/prod)
- Project-specific: batch size (adjustable anytime), labels, target branches
- Pydantic validation
- Runtime config update API

---

### Component 6: Watcher Service

Polls GitLab for assigned MRs.

#### [NEW] [services/watcher/watcher.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/watcher/watcher.py)
- APScheduler for polling
- Multi-project support
- Detects new/updated MRs
- Publishes to Redis queue

#### [NEW] [services/watcher/Dockerfile](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/watcher/Dockerfile)

---

### Component 7: Listener Service (Scalable Webhooks)

Real-time webhook receiver with horizontal scaling.

#### [NEW] [services/listener/listener.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/listener/listener.py)
- FastAPI endpoint: `/webhook/gitlab`
- **Horizontal Pod Autoscaler (HPA)** for traffic handling
- Option for per-project deployment if needed
- Webhook signature validation
- Events: MR assignment, approval, pipeline status
- Publishes to Redis with rate limiting

#### [NEW] [services/listener/Dockerfile](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/listener/Dockerfile)

---

### Component 8: Worker POD Service (Per-Project)

Core merge automation - **one dedicated instance per project**.

#### [NEW] [services/worker/worker.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/worker/worker.py)
- Consumes Redis queue (project-specific)
- Orchestrates validation and merge workflows

#### [NEW] [services/worker/validators.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/worker/validators.py)
- DRY validation: `is_pipeline_successful()`, `is_approved()`, `is_assigned()`, `is_ready_to_merge()`
- 3-strike rejection logic

#### [NEW] [services/worker/merger.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/worker/merger.py)
- **Single MR workflow**: Check up-to-date → Rebase → Wait pipeline → Merge
- **Batch workflow**:
  1. Ensure batch branch fully synced with target
  2. Merge MRs to batch (ordered by timestamp)
  3. Create batch MR
  4. Wait for pipeline success
  5. Merge individual MRs via API after rebase
  6. **Rebase failure**: Reject MR with comment, continue with others

#### [NEW] [services/worker/label_manager.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/worker/label_manager.py)
- Labels: "Merge Assist: Recognised for Merge", "Not Ready", "Rejected", "Ready to Merge", "Batch Merge Request"

#### [NEW] [services/worker/comment_manager.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/worker/comment_manager.py)
- Templated comments for rejection, batch status, merge success, errors

#### [NEW] [services/worker/Dockerfile](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/worker/Dockerfile)

---

### Component 9: Health Check Service

Monitors PODs and alerts stakeholders.

#### [NEW] [services/health/health_checker.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/health/health_checker.py)
- Kubernetes API integration
- Auto-restart attempts
- Alerts to project owners and tool admins (email/Slack)

#### [NEW] [services/health/Dockerfile](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/health/Dockerfile)

---

### Component 10: AI Debugging Assistant (Optional)

AI-powered config debugging with secure token storage.

#### [NEW] [services/ai/ai_assistant.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/services/ai/ai_assistant.py)
- OpenAI/Anthropic integration
- Analyzes errors, suggests fixes
- Generates MR comments for issues
- Token from secrets manager

---

### Component 11: Frontend (React + Auth)

Dashboard with authentication and role-based UI.

#### [NEW] [frontend/src/App.tsx](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/frontend/src/App.tsx)
- Routing with protected routes
- Login page
- Project/target branch selectors

#### [NEW] [frontend/src/components/Login.tsx](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/frontend/src/components/Login.tsx)
- Login form with JWT storage

#### [NEW] [frontend/src/components/Dashboard.tsx](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/frontend/src/components/Dashboard.tsx)
- MR status categories with real-time WebSocket updates

#### [NEW] [frontend/src/components/PriorityManager.tsx](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/frontend/src/components/PriorityManager.tsx)
- Priority assignment (restricted to `priority_manager` and `admin` roles)
- Reorder MRs within batch limit

#### [NEW] [frontend/src/components/LogsViewer.tsx](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/frontend/src/components/LogsViewer.tsx)
- Live POD logs streaming

#### [NEW] [frontend/src/components/HealthStatus.tsx](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/frontend/src/components/HealthStatus.tsx)
- POD health dashboard

#### [NEW] [frontend/src/api/client.ts](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/frontend/src/api/client.ts)
- Axios client with JWT injection and auto-refresh

#### [NEW] [frontend/Dockerfile](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/frontend/Dockerfile)

---

### Component 12: API Gateway (Protected Endpoints)

FastAPI service with JWT-protected routes.

#### [NEW] [api/api_gateway.py](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/api/api_gateway.py)
- Endpoints:
  - `POST /auth/login`, `POST /auth/refresh`
  - `GET /projects` (role-based filtering)
  - `GET /projects/{id}/mrs`
  - `POST /mrs/{id}/priority` (requires `priority_manager`)
  - `PUT /projects/{id}/config` (requires `admin` or `project_owner`)
  - `GET /logs/{project_id}`
  - `GET /health`
  - WebSocket `/ws/updates`

#### [NEW] [api/Dockerfile](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/backend/api/Dockerfile)

---

### Component 13: Docker & Kubernetes Deployment

#### [NEW] [docker-compose.yml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/docker-compose.yml)
- All services with local secrets file

#### [NEW] [k8s/namespace.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/namespace.yaml)

#### [NEW] [k8s/postgres.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/postgres.yaml)
- StatefulSet, PVC

#### [NEW] [k8s/redis.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/redis.yaml)

#### [NEW] [k8s/watcher.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/watcher.yaml)

#### [NEW] [k8s/listener.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/listener.yaml)
- **HPA for webhook traffic scaling**
- Supports per-project deployment if needed

#### [NEW] [k8s/worker-template.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/worker-template.yaml)
- Template instantiated per project

#### [NEW] [k8s/api-gateway.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/api-gateway.yaml)

#### [NEW] [k8s/frontend.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/frontend.yaml)

#### [NEW] [k8s/health-checker.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/health-checker.yaml)

#### [NEW] [k8s/secrets-external.yaml](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/k8s/secrets-external.yaml)
- External Secrets Operator config for AWS Secrets Manager

---

### Component 14: Terraform Infrastructure

#### [NEW] [terraform/main.tf](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/terraform/main.tf)
- EKS cluster, VPC, subnets, security groups
- IAM roles for service accounts
- AWS Secrets Manager setup
- External Secrets Operator installation

#### [NEW] [terraform/variables.tf](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/terraform/variables.tf)

#### [NEW] [terraform/outputs.tf](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/terraform/outputs.tf)

---

### Component 15: Testing & Documentation

#### [NEW] [tests/unit/](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/tests/unit/)
- Unit tests with mocked GitLab API (pytest)
- Auth, validators, merger logic tests

#### [NEW] [tests/integration/](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/tests/integration/)
- DB integration, Redis tests

#### [NEW] [tests/e2e/](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/tests/e2e/)
- Full workflow simulation

#### [NEW] [tests/load/](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/tests/load/)
- Locust load testing for batch operations and webhook traffic

#### [NEW] [README.md](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/README.md)
- Overview, quick start, architecture diagram

#### [NEW] [docs/architecture.md](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/docs/architecture.md)
- Detailed architecture with Mermaid diagrams

#### [NEW] [docs/api.md](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/docs/api.md)
- OpenAPI spec

#### [NEW] [docs/configuration.md](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/docs/configuration.md)
- Project onboarding, config options

#### [NEW] [docs/learning/](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/docs/learning/)
- **tutorial-part1.md**: Development environment setup
- **tutorial-part2.md**: Database and auth layer
- **tutorial-part3.md**: GitLab API integration (dual approach)
- **tutorial-part4.md**: Service implementation
- **tutorial-part5.md**: Frontend with React + Auth
- **tutorial-part6.md**: Kubernetes deployment
- **tutorial-part7.md**: Secrets management best practices
- **resources.md**: Study materials, links, best practices

#### [NEW] [docs/development-guide.md](file:///Users/sivamuralikrishna/Documents/worklearning/merge_wip/docs/development-guide.md)
- Step-by-step recreation guide
- Design decisions
- Extension points

---

## Verification Plan

### Automated Tests
- `pytest tests/unit -v --cov`
- `pytest tests/integration -v`
- `pytest tests/e2e -v`
- `locust -f tests/load/locustfile.py`

### Docker Testing
- `docker-compose build && docker-compose up`
- Verify all services, check logs

### Kubernetes Testing
- Deploy to minikube: `kubectl apply -f k8s/`
- Test HPA scaling for listener
- Verify per-project worker PODs
- Test secrets from AWS Secrets Manager (local minikube uses local secrets)

### EKS Deployment
- Provision: `terraform apply`
- Deploy and verify ingress
- Test auth endpoints
- Verify role-based access
- Monitor resource usage

### Manual Verification
1. Login with different roles
2. Create/assign test MRs in GitLab
3. Verify dashboard displays correctly
4. Test validation, single merge, batch merge
5. Test priority management (authorized users only)
6. Test rebase failure rejection
7. Verify secrets access from AWS Secrets Manager
8. Test webhook scalability with load
9. Verify health checks and alerts
