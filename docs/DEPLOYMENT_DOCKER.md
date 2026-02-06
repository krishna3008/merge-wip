# Merge Assist - Docker Deployment Guide

## Complete Docker & Docker Compose Deployment

This guide covers deploying Merge Assist using Docker and Docker Compose for local development, staging, or small production deployments.

---

## Quick Start

```bash
# Clone repository
git clone <repository-url>
cd merge-assist

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Access API
curl http://localhost:8000/health
```

---

## Production Docker Compose Setup

### Step 1: Create Production Environment File

Create `.env.production`:

```bash
# Database
DB_HOST=postgres
DB_PORT=5432
DB_USER=merge_assist
DB_PASSWORD=CHANGE_ME_STRONG_RANDOM_PASSWORD
DB_NAME=merge_assist

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=CHANGE_ME_REDIS_PASSWORD

# JWT
JWT_SECRET_KEY=CHANGE_ME_LONG_RANDOM_STRING_MIN_32_CHARS
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Secrets Provider
SECRETS_PROVIDER=local
SECRETS_FILE=/app/secrets/local_secrets.enc
MASTER_PASSWORD=CHANGE_ME_MASTER_PASSWORD

# GitLab
GITLAB_URL=https://gitlab.com
MERGE_ASSIST_USER_ID=YOUR_GITLAB_USER_ID

# Application
DEBUG=false
LOG_LEVEL=INFO
FRONTEND_URL=http://localhost:3000

# Service Ports
API_GATEWAY_PORT=8000
LISTENER_PORT=8001

# Worker Configuration
WATCHER_POLLING_INTERVAL=300
WORKER_CHECK_INTERVAL=60
DEFAULT_BATCH_SIZE=5
```

### Step 2: Enhanced Docker Compose

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:13
    container_name: merge-assist-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backend/database/schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - merge-assist-network

  # Redis
  redis:
    image: redis:7-alpine
    container_name: merge-assist-redis
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD} --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "--pass", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks:
      - merge-assist-network

  # API Gateway
  api-gateway:
    build:
      context: .
      dockerfile: backend/api/Dockerfile
    container_name: merge-assist-api-gateway
    restart: unless-stopped
    env_file:
      - .env.production
    ports:
      - "${API_GATEWAY_PORT}:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - app_secrets:/app/secrets
      - ./backend:/app/backend:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - merge-assist-network

  # Listener Service
  listener:
    build:
      context: .
      dockerfile: backend/services/listener/Dockerfile
    container_name: merge-assist-listener
    restart: unless-stopped
    env_file:
      - .env.production
    ports:
      - "${LISTENER_PORT}:8001"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - app_secrets:/app/secrets
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      replicas: 2  # Run 2 instances for load balancing
    networks:
      - merge-assist-network

  # Watcher Service
  watcher:
    build:
      context: .
      dockerfile: backend/services/watcher/Dockerfile
    container_name: merge-assist-watcher
    restart: unless-stopped
    env_file:
      - .env.production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - app_secrets:/app/secrets
    networks:
      - merge-assist-network

  # Worker POD (template - create one per project)
  # worker-project1:
  #   build:
  #     context: .
  #     dockerfile: backend/services/worker/Dockerfile
  #   container_name: merge-assist-worker-project1
  #   restart: unless-stopped
  #   env_file:
  #     - .env.production
  #   environment:
  #     - PROJECT_ID=<uuid-of-project>
  #   command: ["python", "-m", "backend.services.worker.worker_pod", "<uuid-of-project>"]
  #   depends_on:
  #     postgres:
  #       condition: service_healthy
  #     redis:
  #       condition: service_healthy
  #   volumes:
  #     - app_secrets:/app/secrets
  #   networks:
  #     - merge-assist-network

  # Nginx Reverse Proxy (Optional)
  nginx:
    image: nginx:alpine
    container_name: merge-assist-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - api-gateway
      - listener
    networks:
      - merge-assist-network

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  app_secrets:
    driver: local

networks:
  merge-assist-network:
    driver: bridge
```

### Step 3: Nginx Reverse Proxy Configuration

Create `nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream api_gateway {
        server api-gateway:8000;
    }

    upstream listener {
        server listener:8001;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
    limit_req_zone $binary_remote_addr zone=webhook_limit:10m rate=1000r/s;

    server {
        listen 80;
        server_name api.yourdomain.com;
        
        # Redirect to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name api.yourdomain.com;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        # API Gateway
        location / {
            limit_req zone=api_limit burst=20 nodelay;
            
            proxy_pass http://api_gateway;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # CORS
            add_header Access-Control-Allow-Origin $http_origin always;
            add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
            
            if ($request_method = OPTIONS) {
                return 204;
            }
        }

        # Webhooks
        location /webhook {
            limit_req zone=webhook_limit burst=100 nodelay;
            
            proxy_pass http://listener;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
    }
}
```

---

## Deployment Steps

### 1. Build Images

```bash
# Build all images
docker-compose -f docker-compose.prod.yml build

# Or build individually
docker build -t merge-assist/api-gateway:latest -f backend/api/Dockerfile .
docker build -t merge-assist/watcher:latest -f backend/services/watcher/Dockerfile .
docker build -t merge-assist/listener:latest -f backend/services/listener/Dockerfile .
docker build -t merge-assist/worker:latest -f backend/services/worker/Dockerfile .
```

### 2. Initialize Secrets

```bash
# Create secrets directory
mkdir -p secrets

# Run Python script to create encrypted secrets
docker run -it --rm \
  -v $(pwd)/secrets:/app/secrets \
  -e SECRETS_PROVIDER=local \
  -e MASTER_PASSWORD=your-master-password \
  merge-assist/api-gateway:latest \
  python - <<EOF
from backend.secrets.secrets_manager import SecretsManager
import os

os.environ['SECRETS_FILE'] = '/app/secrets/local_secrets.enc'
manager = SecretsManager()
manager.initialize()

# Store GitLab tokens
manager._provider.set_secret('gitlab/project/12345', {
    'token': 'glpat-your-token-here'
})

manager._provider.set_secret('gitlab/merge_assist_user_id', {
    'user_id': 'your-gitlab-user-id'
})
EOF
```

### 3. Start Services

```bash
# Start infrastructure first
docker-compose -f docker-compose.prod.yml up -d postgres redis

# Wait for database to be ready
docker-compose -f docker-compose.prod.yml exec postgres \
  pg_isready -U merge_assist

# Start application services
docker-compose -f docker-compose.prod.yml up -d api-gateway listener watcher

# Check logs
docker-compose -f docker-compose.prod.yml logs -f
```

### 4. Initialize Database

```bash
# Database is auto-initialized from schema.sql
# Verify tables exist
docker-compose -f docker-compose.prod.yml exec postgres \
  psql -U merge_assist -d merge_assist -c "\dt"
```

### 5. Create Admin User

```bash
docker-compose -f docker-compose.prod.yml exec postgres \
  psql -U merge_assist -d merge_assist <<EOF
INSERT INTO users (username, email, password_hash, is_active)
VALUES (
    'admin',
    'admin@yourcompany.com',
    '\$2b\$12\$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyWnFkUEPGy2',
    true
);

INSERT INTO roles (name, description)
VALUES ('admin', 'Full system access');

INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.username = 'admin' AND r.name = 'admin';
EOF
```

### 6. Add Projects and Deploy Workers

```bash
# Add project via API (get PROJECT_ID from response)
curl -X POST http://localhost/projects \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d '{"name":"My Project","gitlab_id":12345,"gitlab_url":"https://gitlab.com/org/project","is_active":true}'

# Start Worker POD for the project
docker run -d \
  --name merge-assist-worker-myproject \
  --network merge-assist_merge-assist-network \
  --env-file .env.production \
  -e PROJECT_ID=<PROJECT_UUID> \
  -v $(pwd)/secrets:/app/secrets \
  merge-assist/worker:latest \
  <PROJECT_UUID>
```

---

## Monitoring

### View Logs

```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f api-gateway

# Worker POD
docker logs -f merge-assist-worker-myproject
```

### Resource Usage

```bash
# Monitor resource usage
docker stats

# Check disk usage
docker system df
```

### Health Checks

```bash
# API Gateway
curl http://localhost/health

# Listener
curl http://localhost:8001/health

# PostgreSQL
docker-compose exec postgres pg_isready -U merge_assist

# Redis
docker-compose exec redis redis-cli --pass $REDIS_PASSWORD ping
```

---

## Backup & Restore

### Database Backup

```bash
# Create backup
docker-compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U merge_assist merge_assist > backup-$(date +%Y%m%d).sql

# Or with compression
docker-compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U merge_assist merge_assist | gzip > backup-$(date +%Y%m%d).sql.gz
```

### Automated Backups

Create `backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d-%H%M%S)

docker-compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U merge_assist merge_assist | \
  gzip > ${BACKUP_DIR}/backup-${DATE}.sql.gz

# Keep only last 7 days
find ${BACKUP_DIR} -name "backup-*.sql.gz" -mtime +7 -delete

echo "Backup completed: backup-${DATE}.sql.gz"
```

Add to cron:

```bash
# Run daily at 2 AM
0 2 * * * /path/to/backup.sh
```

### Restore Database

```bash
# From uncompressed backup
cat backup-20240115.sql | \
  docker-compose -f docker-compose.prod.yml exec -T postgres \
  psql -U merge_assist merge_assist

# From compressed backup
gunzip -c backup-20240115.sql.gz | \
  docker-compose -f docker-compose.prod.yml exec -T postgres \
  psql -U merge_assist merge_assist
```

---

## Scaling

### Scale Listener Service

```bash
# Scale to 5 instances
docker-compose -f docker-compose.prod.yml up -d --scale listener=5

# Nginx will automatically load balance
```

### Add Worker PODs

```bash
# For each new project, start a new worker
docker run -d \
  --name merge-assist-worker-project2 \
  --network merge-assist_merge-assist-network \
  --env-file .env.production \
  -e PROJECT_ID=<PROJECT_UUID> \
  -v $(pwd)/secrets:/app/secrets \
  merge-assist/worker:latest \
  <PROJECT_UUID>
```

---

## SSL/TLS Setup

### Using Let's Encrypt

```bash
# Install certbot
docker run -it --rm \
  -v $(pwd)/ssl:/etc/letsencrypt \
  -p 80:80 \
  certbot/certbot certonly \
  --standalone \
  -d api.yourdomain.com

# Certificates will be in ./ssl/live/api.yourdomain.com/
# Update nginx.conf to point to these certificates
```

### Auto-Renewal

Create `renew-cert.sh`:

```bash
#!/bin/bash
docker run --rm \
  -v $(pwd)/ssl:/etc/letsencrypt \
  -p 80:80 \
  certbot/certbot renew

docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

Add to cron:

```bash
# Check renewal daily at 3 AM
0 3 * * * /path/to/renew-cert.sh
```

---

## Troubleshooting

### Services Not Starting

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs

# Check specific service
docker-compose -f docker-compose.prod.yml logs api-gateway

# Inspect container
docker inspect merge-assist-api-gateway
```

### Database Connection Issues

```bash
# Test connectivity from API Gateway
docker-compose -f docker-compose.prod.yml exec api-gateway \
  ping postgres

# Check PostgreSQL is accepting connections
docker-compose -f docker-compose.prod.yml exec postgres \
  psql -U merge_assist -c "SELECT 1"
```

### Redis Connection Issues

```bash
# Test Redis
docker-compose -f docker-compose.prod.yml exec redis \
  redis-cli --pass $REDIS_PASSWORD ping

# Check Redis logs
docker-compose -f docker-compose.prod.yml logs redis
```

---

## Updates & Maintenance

### Update Application

```bash
# Pull latest code
git pull

# Rebuild images
docker-compose -f docker-compose.prod.yml build

# Restart services (zero downtime)
docker-compose -f docker-compose.prod.yml up -d --no-deps --build api-gateway
docker-compose -f docker-compose.prod.yml up -d --no-deps --build listener
docker-compose -f docker-compose.prod.yml up -d --no-deps --build watcher
```

### Clean Up

```bash
# Remove stopped containers
docker-compose -f docker-compose.prod.yml rm

# Remove unused images
docker image prune -a

# Remove unused volumes (CAUTION: This deletes data!)
docker volume prune
```

---

## Production Checklist

Before deploying to production:

- [ ] Change all default passwords in `.env.production`
- [ ] Set strong `JWT_SECRET_KEY` (>32 characters)
- [ ] Set strong `MASTER_PASSWORD` for secrets encryption
- [ ] Configure SSL/TLS certificates
- [ ] Set up automated database backups
- [ ] Configure log rotation
- [ ] Enable firewall rules (only ports 80, 443 exposed)
- [ ] Set `DEBUG=false` and `LOG_LEVEL=WARNING`
- [ ] Configure monitoring/alerting
- [ ] Test disaster recovery procedure
- [ ] Document server access procedures

---

*For usage instructions, see [USAGE.md](USAGE.md)*
*For EKS deployment, see [DEPLOYMENT_EKS.md](DEPLOYMENT_EKS.md)*
