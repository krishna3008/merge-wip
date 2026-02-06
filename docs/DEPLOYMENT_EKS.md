# Merge Assist - EKS Deployment Guide

## Complete AWS EKS Deployment

This guide walks you through deploying Merge Assist to AWS EKS from scratch.

---

## Prerequisites

- AWS CLI configured with appropriate credentials
- kubectl installed
- eksctl installed
- Docker installed
- Terraform installed (optional, for infrastructure as code)

---

## Step 1: Create EKS Cluster

### Option A: Using eksctl (Quick)

```bash
# Create cluster with eksctl
eksctl create cluster \
  --name merge-assist-cluster \
  --region us-east-1 \
  --node-type t3.medium \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 5 \
  --with-oidc \
  --managed

# This takes ~15-20 minutes
```

### Option B: Using Terraform (Infrastructure as Code)

Create `terraform/eks.tf`:

```hcl
# terraform/eks.tf
provider "aws" {
  region = "us-east-1"
}

module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
  
  name = "merge-assist-vpc"
  cidr = "10.0.0.0/16"
  
  azs             = ["us-east-1a", "us-east-1b", "us-east-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
  
  enable_nat_gateway = true
  enable_dns_hostnames = true
  
  tags = {
    "kubernetes.io/cluster/merge-assist-cluster" = "shared"
  }
}

module "eks" {
  source = "terraform-aws-modules/eks/aws"
  
  cluster_name    = "merge-assist-cluster"
  cluster_version = "1.28"
  
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
  
  eks_managed_node_groups = {
    general = {
      desired_size = 3
      min_size     = 2
      max_size     = 5
      
      instance_types = ["t3.medium"]
      capacity_type  = "ON_DEMAND"
    }
  }
}
```

Deploy with Terraform:

```bash
cd terraform
terraform init
terraform plan
terraform apply  # Confirm with 'yes'
```

---

## Step 2: Configure kubectl

```bash
# Update kubeconfig
aws eks update-kubeconfig \
  --region us-east-1 \
  --name merge-assist-cluster

# Verify connection
kubectl get nodes
```

Expected output:
```
NAME                         STATUS   ROLES    AGE   VERSION
ip-10-0-1-xxx.ec2.internal   Ready    <none>   5m    v1.28.x
ip-10-0-2-xxx.ec2.internal   Ready    <none>   5m    v1.28.x
ip-10-0-3-xxx.ec2.internal   Ready    <none>   5m    v1.28.x
```

---

## Step 3: Build and Push Docker Images

### Create ECR Repositories

```bash
# Create repositories
aws ecr create-repository --repository-name merge-assist/api-gateway
aws ecr create-repository --repository-name merge-assist/watcher
aws ecr create-repository --repository-name merge-assist/listener
aws ecr create-repository --repository-name merge-assist/worker

# Get registry URL
REGISTRY=$(aws ecr describe-repositories \
  --repository-names merge-assist/api-gateway \
  --query 'repositories[0].repositoryUri' \
  --output text | cut -d'/' -f1)

echo "Registry: $REGISTRY"
```

### Login to ECR

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $REGISTRY
```

### Build and Push Images

```bash
# Build images
docker build -t merge-assist/api-gateway:latest -f backend/api/Dockerfile .
docker build -t merge-assist/watcher:latest -f backend/services/watcher/Dockerfile .
docker build -t merge-assist/listener:latest -f backend/services/listener/Dockerfile .
docker build -t merge-assist/worker:latest -f backend/services/worker/Dockerfile .

# Tag for ECR
docker tag merge-assist/api-gateway:latest $REGISTRY/merge-assist/api-gateway:latest
docker tag merge-assist/watcher:latest $REGISTRY/merge-assist/watcher:latest
docker tag merge-assist/listener:latest $REGISTRY/merge-assist/listener:latest
docker tag merge-assist/worker:latest $REGISTRY/merge-assist/worker:latest

# Push to ECR
docker push $REGISTRY/merge-assist/api-gateway:latest
docker push $REGISTRY/merge-assist/watcher:latest
docker push $REGISTRY/merge-assist/listener:latest
docker push $REGISTRY/merge-assist/worker:latest
```

---

## Step 4: Set Up AWS Secrets Manager

```bash
# Create secrets
aws secretsmanager create-secret \
  --name merge-assist/database/credentials \
  --secret-string '{
    "username":"merge_assist",
    "password":"CHANGE_ME_STRONG_PASSWORD"
  }'

aws secretsmanager create-secret \
  --name merge-assist/jwt/secret \
  --secret-string '{"key":"CHANGE_ME_LONG_RANDOM_STRING_AT_LEAST_32_CHARS"}'

aws secretsmanager create-secret \
  --name merge-assist/gitlab/merge_assist_user_id \
  --secret-string '{"user_id":"YOUR_MERGE_ASSIST_GITLAB_USER_ID"}'

# For each project
aws secretsmanager create-secret \
  --name merge-assist/gitlab/project/12345 \
  --secret-string '{"token":"glpat-YOUR_GITLAB_TOKEN"}'
```

### Create IAM Role for Secrets Access

```bash
# Create IAM policy
cat > secrets-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:merge-assist/*"
    }
  ]
}
EOF

aws iam create-policy \
  --policy-name MergeAssistSecretsPolicy \
  --policy-document file://secrets-policy.json

# Attach to EKS node role
NODE_ROLE=$(aws eks describe-nodegroup \
  --cluster-name merge-assist-cluster \
  --nodegroup-name <nodegroup-name> \
  --query 'nodegroup.nodeRole' \
  --output text)

aws iam attach-role-policy \
  --role-name $(basename $NODE_ROLE) \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/MergeAssistSecretsPolicy
```

---

## Step 5: Deploy PostgreSQL with EBS

Create `k8s/postgres-ebs.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: merge-assist
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: gp3
  resources:
    requests:
      storage: 50Gi
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: merge-assist
spec:
  serviceName: postgres-service
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:13
        ports:
        - containerPort: 5432
          name: postgres
        env:
        - name: POSTGRES_DB
          value: merge_assist
        - name: POSTGRES_USER
          value: merge_assist
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: password
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: merge-assist
spec:
  ports:
  - port: 5432
    targetPort: 5432
  clusterIP: None
  selector:
    app: postgres
```

---

## Step 6: Update Kubernetes Manifests for EKS

Update image references in all manifests:

```bash
# Replace local images with ECR images
cd k8s

# Update api-gateway.yaml
sed -i "s|image: merge-assist/api-gateway:latest|image: $REGISTRY/merge-assist/api-gateway:latest|g" api-gateway.yaml

# Update watcher.yaml
sed -i "s|image: merge-assist/watcher:latest|image: $REGISTRY/merge-assist/watcher:latest|g" watcher.yaml

# Update listener.yaml
sed -i "s|image: merge-assist/listener:latest|image: $REGISTRY/merge-assist/listener:latest|g" listener.yaml

# Update worker-template.yaml
sed -i "s|image: merge-assist/worker:latest|image: $REGISTRY/merge-assist/worker:latest|g" worker-template.yaml
```

---

## Step 7: Deploy to EKS

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create secrets (Kubernetes secrets for non-sensitive config)
kubectl create secret generic db-credentials \
  --from-literal=password=YOUR_DB_PASSWORD \
  -n merge-assist

# Deploy infrastructure
kubectl apply -f k8s/postgres-ebs.yaml
kubectl apply -f k8s/redis.yaml

# Wait for database to be ready
kubectl wait --for=condition=ready pod -l app=postgres -n merge-assist --timeout=300s

# Apply database schema
kubectl exec -it postgres-0 -n merge-assist -- \
  psql -U merge_assist -d merge_assist < backend/database/schema.sql

# Deploy services
kubectl apply -f k8s/api-gateway.yaml
kubectl apply -f k8s/listener.yaml
kubectl apply -f k8s/watcher.yaml

# Deploy worker PODs (one per project)
# Replace PROJECT_ID and PROJECT_NAME
sed 's/PROJECT_ID/<uuid>/g; s/PROJECT_NAME/myproject/g' \
  k8s/worker-template.yaml | kubectl apply -f -
```

---

## Step 8: Configure Load Balancer & DNS

### Get Load Balancer URL

```bash
# Get API Gateway load balancer
kubectl get svc api-gateway-service -n merge-assist

# Get Listener load balancer
kubectl get svc listener-service -n merge-assist
```

### Set Up Route53 (Optional)

```bash
# Create Route53 hosted zone (if needed)
aws route53 create-hosted-zone --name mergeassist.yourcompany.com --caller-reference $(date +%s)

#Create A record for API
API_LB=$(kubectl get svc api-gateway-service -n merge-assist -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Create alias record in Route53
# (Use AWS Console or CLI to create alias to $API_LB)
```

---

## Step 9: Enable SSL/TLS

### Install cert-manager

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer for Let's Encrypt
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@yourcompany.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

### Create Ingress

```bash
cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind:Ingress
metadata:
  name: merge-assist-ingress
  namespace: merge-assist
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - api.mergeassist.yourcompany.com
    secretName: merge-assist-tls
  rules:
  - host: api.mergeassist.yourcompany.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: api-gateway-service
            port:
              number: 80
EOF
```

---

## Step 10: Monitoring & Logging

### Install Prometheus & Grafana

```bash
# Add Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install Prometheus
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace

# Access Grafana
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
# Visit http://localhost:3000 (admin/prom-operator)
```

### Configure CloudWatch Logs

```bash
# Install Fluent Bit
kubectl apply -f https://raw.githubusercontent.com/aws-samples/amazon-cloudwatch-container-insights/latest/k8s-deployment-manifest-templates/deployment-mode/daemonset/container-insights-monitoring/quickstart/cwagent-fluent-bit-quickstart.yaml
```

---

## Step 11: Verify Deployment

```bash
# Check all pods
kubectl get pods -n merge-assist

# Check services
kubectl get svc -n merge-assist

# Test API
API_URL=$(kubectl get svc api-gateway-service -n merge-assist -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl http://$API_URL/health

# Expected: {"status":"healthy","service":"api-gateway"}
```

---

## Scaling

### Auto-Scaling (HPA)

Already configured for Listener service. To add for others:

```bash
kubectl autoscale deployment api-gateway \
  --cpu-percent=70 \
  --min=2 \
  --max=10 \
  -n merge-assist
```

### Node Auto-Scaling

```bash
# Enable cluster autoscaler
eksctl create iamserviceaccount \
  --cluster=merge-assist-cluster \
  --namespace=kube-system \
  --name=cluster-autoscaler \
  --attach-policy-arn=arn:aws:iam::aws:policy/AutoScalingFullAccess \
  --approve

# Deploy cluster autoscaler
kubectl apply -f https://raw.githubusercontent.com/kubernetes/autoscaler/master/cluster-autoscaler/cloudprovider/aws/examples/cluster-autoscaler-autodiscover.yaml
```

---

## Backup Strategy

### PostgreSQL Backups

```bash
# Create backup CronJob
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: merge-assist
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:13
            command:
            - /bin/sh
            - -c
            - pg_dump -h postgres-service -U merge_assist merge_assist | gzip > /backup/backup-$(date +%Y%m%d-%H%M%S).sql.gz
            volumeMounts:
            - name: backup-storage
              mountPath: /backup
          restartPolicy: OnFailure
          volumes:
          - name: backup-storage
            persistentVolumeClaim:
              claimName: backup-pvc
EOF
```

---

## Cost Optimization

### Spot Instances for Worker PODs

```bash
# Create spot instance node group
eksctl create nodegroup \
  --cluster=merge-assist-cluster \
  --name=spot-workers \
  --spot \
  --instance-types=t3.medium,t3a.medium \
  --nodes=2 \
  --nodes-min=1 \
  --nodes-max=5

# Label Worker PODs to use spot instances
# Add to worker-template.yaml:
# nodeSelector:
#   eks.amazonaws.com/capacityType: SPOT
```

---

## Troubleshooting

### Pods Not Starting

```bash
# Check events
kubectl describe pod <pod-name> -n merge-assist

# Check logs
kubectl logs <pod-name> -n merge-assist

# Common issues:
# - Image pull errors: Check ECR permissions
# - Secrets not found: Verify secrets exist
# - Resource limits: Check node capacity
```

### Database Connection Issues

```bash
# Test database connectivity
kubectl run -it --rm debug --image=postgres:13 --restart=Never -- \
  psql -h postgres-service.merge-assist.svc.cluster.local -U merge_assist

# Check database pods
kubectl get pods -l app=postgres -n merge-assist
```

---

## Cleanup

```bash
# Delete all resources
kubectl delete namespace merge-assist

# Delete EKS cluster
eksctl delete cluster --name merge-assist-cluster

# Or with Terraform
cd terraform
terraform destroy
```

---

*For usage instructions, see [USAGE.md](USAGE.md)*
