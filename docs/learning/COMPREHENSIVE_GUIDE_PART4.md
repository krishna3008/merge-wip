# Merge Assist - Comprehensive Guide Part 4
## Worker POD, Frontend, and Deployment

*Final part - Continuation from Part 3*

---

## 7. Part 6: Worker POD - Merge Logic Implementation

### Learning Objectives
- Implement MR validation logic
- Build single and batch merge workflows
- Understand Redis pub/sub pattern
- Implement retry and error handling

### 7.1: Worker POD Architecture

**What is a POD?**
In Kubernetes, a POD is the smallest deployable unit. For us, each project gets its own Worker POD.

**Why one Worker per project?**
- ✅ Isolation: Project A's issues don't affect Project B
- ✅ Scaling: Add more projects → Kubernetes creates more PODs
- ✅ Failure containment: If Worker crashes, only one project affected

**Worker POD workflow**:
```
1. Initialize (connect to DB, Redis, GitLab)
2. Subscribe to Redis channel for project events
3. Main loop:
   a. Wait for MR event from Redis
   b. Validate MR (pipeline, approvals, conflicts)
   c. If ready → Add to merge queue
   d. Check queue for batch merge opportunity
   e. Execute merge (single or batch)
4. Repeat
```

### 7.2: MR Validation Logic

**Why validate before merging?**
- Broken pipeline → Don't merge (would break main branch!)
- Unresolved discussions → Author needs to address feedback
- Merge conflicts → Can't merge automatically
- WIP status → Not ready yet

Create `backend/services/worker/validators.py`:

```python
"""
MR validation logic for Worker POD.
"""
import logging
from typing import Tuple, List
from backend.gitlab_integration.gitlab_unified import GitLabUnified
from backend.gitlab_integration.gitlab_models import MergeRequest

logger = logging.getLogger(__name__)


class MRValidator:
    """
    Validates MRs before merging.
    
    Why separate validator class?
    - Single Responsibility Principle
    - Easy to test
    - Reusable across different merge strategies
    """
    
    def __init__(self, gitlab: GitLabUnified, merge_assist_user_id: int):
        """
        Initialize validator.
        
        Args:
            gitlab: GitLab API client
            merge_assist_user_id: User ID of Merge Assist bot
        """
        self.gitlab = gitlab
        self.merge_assist_user_id = merge_assist_user_id
    
    async def is_ready_to_merge(
        self,
        mr_data: dict
    ) -> Tuple[bool, List[str]]:
        """
        Check if MR is ready to merge.
        
        Returns:
            (is_ready, reasons)
            - is_ready: True if MR can be merged
            - reasons: List of reasons if not ready (empty if ready)
        
        Validation checks:
        1. Not WIP/Draft
        2. Pipeline exists and passed
        3. Has required approvals
        4. No merge conflicts
        5. All discussions resolved
        """
        reasons = []
        
        # Parse MR data
        mr = MergeRequest(**mr_data)
        
        # Check 1: WIP status
        if mr.is_wip():
            reasons.append("MR is marked as WIP/Draft")
        
        # Check 2: Pipeline status
        if not mr.has_pipeline_passed():
            pipeline_status = (
                mr.head_pipeline or mr.pipeline or {}
            ).get('status', 'missing')
            reasons.append(f"Pipeline status is '{pipeline_status}' (must be 'success')")
        
        # Check 3: Merge conflicts
        if mr.has_conflicts:
            reasons.append("MR has merge conflicts")
        
        # Check 4: Discussions
        if not mr.blocking_discussions_resolved:
            reasons.append("Not all discussions are resolved")
        
        # Check 5: Assignment
        if not mr.assignee or mr.assignee.id != self.merge_assist_user_id:
            reasons.append("MR not assigned to Merge Assist")
        
        is_ready = len(reasons) == 0
        
        if is_ready:
            logger.info(f"MR !{mr.iid} is READY to merge")
        else:
            logger.info(f"MR !{mr.iid} is NOT ready: {', '.join(reasons)}")
        
        return is_ready, reasons
```

**Why return tuple (bool, List[str])?**
- `bool`: Quick check (is ready?)
- `List[str]`: Detailed feedback (why not ready?)
- Can be used for logging or user notifications

### 7.3: Single MR Merge Workflow

**Single merge steps**:
1. Rebase MR (update with latest target branch)
2. Wait for pipeline to run on rebased code
3. Verify pipeline passes
4. Execute merge
5. Update database

Create `backend/services/worker/merger.py`:

```python
"""
Merge orchestration logic.
"""
import asyncio
import logging
from typing import List, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class Merger:
    """Handles single and batch merge operations."""
    
    def __init__(
        self,
        gitlab,
        validator,
        label_manager,
        comment_manager,
        project_config
    ):
        """
        Initialize merger.
        
        Why inject dependencies?
        - Testability: Can mock GitLab, validator, etc.
        - Flexibility: Swap implementations
        - Clear dependencies: Easy to see what merger needs
        """
        self.gitlab = gitlab
        self.validator = validator
        self.label_manager = label_manager
        self.comment_manager = comment_manager
        self.project_config = project_config
    
    async def merge_single_mr(
        self,
        project_id: int,
        mr_data: dict,
        db_session
    ) -> bool:
        """
        Merge a single MR.
        
        Workflow:
        1. Rebase
        2. Wait for pipeline
        3. Merge
        
        Returns:
            True if successful, False otherwise
        """
        mr_iid = mr_data['iid']
        logger.info(f"Starting single merge for MR !{mr_iid}")
        
        try:
            # Step 1: Rebase
            logger.info(f"Rebasing MR !{mr_iid}")
            await self.gitlab.rebase_mr(project_id, mr_iid)
            
            # Step 2: Wait for pipeline
            logger.info(f"Waiting for pipeline on MR !{mr_iid}")
            pipeline_passed = await self._wait_for_pipeline(
                project_id,
                mr_iid,
                timeout_minutes=30
            )
            
            if not pipeline_passed:
                logger.warning(f"Pipeline failed for MR !{mr_iid}")
                await self.comment_manager.add_pipeline_failed_comment(
                    project_id,
                    mr_iid
                )
                self._update_mr_status(db_session, mr_iid, 'failed')
                return False
            
            # Step 3: Merge
            logger.info(f"Merging MR !{mr_iid}")
            await self.gitlab.merge_mr(project_id, mr_iid)
            
            # Update database
            self._update_mr_status(db_session, mr_iid, 'merged')
            
            logger.info(f"✅ Successfully merged MR !{mr_iid}")
            return True
            
        except Exception as e:
            logger.error(f"Error merging MR !{mr_iid}: {e}")
            await self.comment_manager.add_error_comment(
                project_id,
                mr_iid,
                str(e)
            )
            return False
    
    async def _wait_for_pipeline(
        self,
        project_id: int,
        mr_iid: int,
        timeout_minutes: int = 30
    ) -> bool:
        """
        Wait for pipeline to complete.
        
        Why polling?
        - GitLab doesn't send webhook when pipeline completes
          during rebase
        - Must check periodically
        
        Timeout prevents infinite waiting.
        """
        start_time = datetime.utcnow()
        timeout = timedelta(minutes=timeout_minutes)
        
        while datetime.utcnow() - start_time < timeout:
            # Get latest MR data
            mr_data = await self.gitlab.get_merge_request(project_id, mr_iid)
            
            pipeline = mr_data.get('head_pipeline')
            if not pipeline:
                # No pipeline yet, wait
                await asyncio.sleep(5)
                continue
            
            status = pipeline['status']
            
            if status == 'success':
                return True
            elif status in ['failed', 'canceled']:
                return False
            else:
                # Still running, wait
                await asyncio.sleep(10)
        
        # Timeout
        logger.warning(f"Pipeline timeout for MR !{mr_iid}")
        return False
    
    def _update_mr_status(self, db_session, mr_iid: int, status: str):
        """Update MR status in database."""
        from backend.database.models import MergeRequest
        
        db_mr = db_session.query(MergeRequest).filter(
            MergeRequest.gitlab_mr_iid == mr_iid
        ).first()
        
        if db_mr:
            db_mr.status = status
            if status == 'merged':
                db_mr.merged_at = datetime.utcnow()
            db_session.commit()
```

### 7.4: Batch Merge Workflow

**Why batch merge?**
- **Efficiency**: Test 5 MRs together instead of 5 separate pipelines
- **Speed**: 1 pipeline run instead of 5 (saves ~50 minutes if each takes 10 min)
- **Resource savings**: Less CI/CD usage

**Batch merge strategy**:
```
1. Create batch branch (batch-merge-2024-01-15-001)
2. Merge all 5 MRs into batch branch (without triggering CI)
3. Push batch branch → Triggers ONE pipeline
4. If pipeline passes:
   a. Rebase each MR individually
   b. Wait for its pipeline
   c. Merge
5. If pipeline fails:
   a. Identify which MR broke it
   b. Remove from batch
   c. Retry with remaining MRs
```

```python
async def merge_batch(
    self,
    project_id: int,
    target_branch: str,
    mrs: List[dict],
    db_session
) -> bool:
    """
    Merge multiple MRs as a batch.
    
    Args:
        project_id: GitLab project ID
        target_branch: Target branch (e.g., 'main')
        mrs: List of MR data dictionaries
        db_session: Database session
    
    Returns:
        True if batch merged successfully
    """
    batch_id = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    batch_branch = f"batch-merge-{batch_id}"
    
    logger.info(f"Starting batch merge for {len(mrs)} MRs")
    
    try:
        # Step 1: Create batch branch
        await self.gitlab.create_branch(
            project_id,
            batch_branch,
            target_branch
        )
        
        # Step 2: Merge all MRs into batch branch
        for mr in mrs:
            mr_iid = mr['iid']
            try:
                await self.gitlab.merge_into_branch(
                    project_id,
                    mr['source_branch'],
                    batch_branch,
                    skip_ci=True  # Don't trigger CI yet
                )
                logger.info(f"Merged !{mr_iid} into {batch_branch}")
            except Exception as e:
                logger.error(f"Failed to merge !{mr_iid} into batch: {e}")
                # Remove this MR from batch
                mrs.remove(mr)
        
        # Step 3: Push batch branch (triggers pipeline)
        # GitLab automatically triggers pipeline on push
        
        # Step 4: Wait for batch pipeline
        pipeline_passed = await self._wait_for_branch_pipeline(
            project_id,
            batch_branch,
            timeout_minutes=60
        )
        
        if not pipeline_passed:
            logger.warning("Batch pipeline failed")
            # Could implement bisect here to find failing MR
            return False
        
        # Step 5: Merge individual MRs
        success_count = 0
        for mr in mrs:
            merged = await self.merge_single_mr(project_id, mr, db_session)
            if merged:
                success_count += 1
        
        logger.info(f"Batch merge complete: {success_count}/{len(mrs)} successful")
        
        # Cleanup: Delete batch branch
        await self.gitlab.delete_branch(project_id, batch_branch)
        
        return success_count == len(mrs)
        
    except Exception as e:
        logger.error(f"Batch merge error: {e}")
        return False
```

---

## 8. Part 7: Frontend with React & TypeScript

### Learning Objectives
- Build React components with TypeScript
- Implement JWT authentication flow
- Create responsive dashboards
- Handle API communication

### 8.1: Why React?

**React benefits**:
- ✅ Component-based (reusable UI pieces)
- ✅ Virtual DOM (fast updates)
- ✅ Huge ecosystem
- ✅ TypeScript support

**Why TypeScript?**
- ✅ Type safety (catch errors before runtime)
- ✅ Better IDE autocomplete
- ✅ Easier refactoring
- ✅ Self-documenting code

### 8.2: Authentication Flow

**JWT authentication in frontend**:
```
1. User enters credentials
2. POST /auth/login → Receives JWT token
3. Store token in localStorage
4. Include token in all API requests:
   Authorization: Bearer <token>
5. If 401 error → Token expired → Redirect to login
```

**Example: Login Component**

Already created in `/frontend/src/components/Login.tsx`!

**Key concepts**:
```typescript
// TypeScript interface
interface LoginProps {
  onLoginSuccess: (token: string) => void;
}

// Typed state
const [username, setUsername] = useState<string>('');

// Typed function
const handleLogin = async (e: React.FormEvent): Promise<void> => {
  // ...
}
```

### 8.3: Dashboard Component

Create `frontend/src/components/Dashboard.tsx`:

```typescript
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './Dashboard.css';

interface Project {
  id: string;
  name: string;
  gitlab_id: number;
  is_active: boolean;
}

interface MR {
  id: string;
  gitlab_mr_iid: number;
  title: string;
  status: string;
  target_branch: string;
}

const Dashboard: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [mrs, setMrs] = useState<MR[]>([]);
  const [loading, setLoading] = useState(false);
  
  // Get token from localStorage
  const token = localStorage.getItem('access_token');
  
  // Configure axios with auth header
  const api = axios.create({
    baseURL: process.env.REACT_APP_API_URL,
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  // Load projects on mount
  useEffect(() => {
    loadProjects();
  }, []);
  
  const loadProjects = async () => {
    try {
      const response = await api.get('/projects');
      setProjects(response.data);
    } catch (error) {
      console.error('Failed to load projects:', error);
    }
  };
  
  const loadMRs = async (projectId: string) => {
    setLoading(true);
    try {
      const response = await api.get(`/projects/${projectId}/mrs`);
      setMrs(response.data);
      setSelectedProject(projectId);
    } catch (error) {
      console.error('Failed to load MRs:', error);
    } finally {
      setLoading(false);
    }
  };
  
  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'ready': return '#28a745';
      case 'merged': return '#6c757d';
      case 'rejected': return '#dc3545';
      default: return '#ffc107';
    }
  };
  
  return (
    <div className="dashboard">
      <h1>Merge Assist Dashboard</h1>
      
      <div className="projects-section">
        <h2>Projects</h2>
        <div className="projects-list">
          {projects.map(project => (
            <div
              key={project.id}
              className={`project-card ${selectedProject === project.id ? 'selected' : ''}`}
              onClick={() => loadMRs(project.id)}
            >
              <h3>{project.name}</h3>
              <p>GitLab ID: {project.gitlab_id}</p>
              <span className={`status ${project.is_active ? 'active' : 'inactive'}`}>
                {project.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>
          ))}
        </div>
      </div>
      
      {selectedProject && (
        <div className="mrs-section">
          <h2>Merge Requests</h2>
          {loading ? (
            <p>Loading...</p>
          ) : (
            <table className="mrs-table">
              <thead>
                <tr>
                  <th>MR</th>
                  <th>Title</th>
                  <th>Target Branch</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {mrs.map(mr => (
                  <tr key={mr.id}>
                    <td>!{mr.gitlab_mr_iid}</td>
                    <td>{mr.title}</td>
                    <td>{mr.target_branch}</td>
                    <td>
                      <span
                        className="status-badge"
                        style={{ backgroundColor: getStatusColor(mr.status) }}
                      >
                        {mr.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};

export default Dashboard;
```

---

## 9. Part 8: Kubernetes Deployment

### Learning Objectives
- Understand Kubernetes concepts
- Deploy multi-service application
- Configure autoscaling
- Manage secrets

### 9.1: Kubernetes Core Concepts

**Pod**: Smallest deployable unit (1+ containers)
**Deployment**: Manages replicas of pods
**Service**: Network endpoint for pods
**StatefulSet**: For stateful apps (database)
**HPA**: Horizontal Pod Autoscaler (auto-scaling)

### 9.2: Deployment Strategy

**Our architecture in Kubernetes**:
```
┌─────────────────────────────────────────┐
│           Namespace: merge-assist       │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  API Gateway (Deployment, 2 pods) │◀─── LoadBalancer
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Listener (Deployment + HPA)     │◀─── LoadBalancer
│  │  Min: 2, Max: 10 pods            │     (webhooks)
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Watcher (Deployment, 1 pod)     │  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────┐  ┌──────────────┐  │
│  │ Worker POD 1 │  │ Worker POD 2 │  │
│  │ (Project A)  │  │ (Project B)  │  │
│  └──────────────┘  └──────────────┘  │
│                                         │
│  ┌───────────────┐  ┌──────────────┐  │
│  │ PostgreSQL    │  │ Redis        │  │
│  │ (StatefulSet) │  │ (Deployment) │  │
│  └───────────────┘  └──────────────┘  │
└─────────────────────────────────────────┘
```

### 9.3: Step-by-Step Deployment

**Already created**:
- `k8s/namespace.yaml` - Namespace
- `k8s/secrets.yaml` - Secrets
- `k8s/postgres.yaml` - PostgreSQL StatefulSet
- `k8s/redis.yaml` - Redis deployment
- `k8s/api-gateway.yaml` - API Gateway
- `k8s/listener.yaml` - Listener + HPA
- `k8s/watcher.yaml` - Watcher
- `k8s/worker-template.yaml` - Worker POD template

**Deploy to Kubernetes**:

```bash
# 1. Build Docker images
docker build -t merge-assist/api-gateway:latest -f backend/api/Dockerfile .
docker build -t merge-assist/watcher:latest -f backend/services/watcher/Dockerfile .
docker build -t merge-assist/listener:latest -f backend/services/listener/Dockerfile .
docker build -t merge-assist/worker:latest -f backend/services/worker/Dockerfile .

# 2. Push to registry (if using remote cluster)
# docker tag merge-assist/api-gateway:latest YOUR_REGISTRY/merge-assist/api-gateway:latest
# docker push YOUR_REGISTRY/merge-assist/api-gateway:latest
# ... repeat for other images

# 3. Apply Kubernetes manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/api-gateway.yaml
kubectl apply -f k8s/listener.yaml
kubectl apply -f k8s/watcher.yaml

# 4. Create Worker PODs (one per project)
# Replace PROJECT_ID and PROJECT_NAME with actual values
sed 's/PROJECT_ID/abc-123-def/g; s/PROJECT_NAME/my-project/g' \
  k8s/worker-template.yaml | kubectl apply -f -

# 5. Verify deployment
kubectl get pods -n merge-assist
kubectl get services -n merge-assist

# 6. Access API Gateway
kubectl get svc api-gateway-service -n merge-assist
# Note the EXTERNAL-IP
curl http://EXTERNAL-IP/health
```

---

## 10. Summary & Next Steps

### What You've Learned

**Part 1**: Database, SQLAlchemy, Authentication
**Part 2**: RBAC, Secrets Management
**Part 3**: Configuration, GitLab API
**Part 4**: Worker POD, Frontend, Kubernetes

### Complete Application Checklist

- ✅ PostgreSQL schema design
- ✅ SQLAlchemy ORM models
- ✅ JWT authentication
- ✅ RBAC with decorators
- ✅ AWS Secrets Manager + local encryption
- ✅ Pydantic configuration
- ✅ Dual GitLab API clients
- ✅ MR validation logic
- ✅ Single & batch merge workflows
- ✅ Watcher service (polling)
- ✅ Listener service (webhooks)
- ✅ API Gateway (FastAPI)
- ✅ React frontend
- ✅ Docker containers
- ✅ Kubernetes deployment

### Practice Exercises

1. **Add a New Role**:
   - Add "tester" role to RBAC
   - Give permission to view MRs only
   - Test with new user

2. **Implement Email Notifications**:
   - Send email when MR is merged
   - Use SendGrid or AWS SES
   - Add email template system

3. **Add Metrics**:
   - Track merge success rate
   - Average time to merge
   - Exposemetrics for Prometheus

4. **Enhance Frontend**:
   - Add dark mode
   - Real-time updates with WebSockets
   - MR priority drag-and-drop

### Production Readiness

**Still needed**:
- Comprehensive testing (unit, integration, E2E)
- Monitoring (Prometheus + Grafana)
- Logging aggregation (ELK stack)
- CI/CD pipeline (GitHub Actions)
- Terraform for AWS EKS
- Backup strategy for PostgreSQL
- Disaster recovery plan

---

## Congratulations! 🎉

You can now build Merge Assist from scratch! You understand:
- **Why** each technology was chosen
- **How** each component works
- **When** to use each pattern

This knowledge transfers to other projects. The patterns you've learned—singleton, factory, decorator, facade—are universal.

Happy coding!
