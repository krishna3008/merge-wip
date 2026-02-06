-- Merge Assist Database Schema
-- PostgreSQL 13+

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users and Authentication
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_active ON users(is_active);

-- Roles
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Insert default roles
INSERT INTO roles (name, description) VALUES
    ('admin', 'Full access to all projects and settings'),
    ('project_owner', 'Manage specific projects, view logs'),
    ('priority_manager', 'Set MR priorities within batch size limit'),
    ('viewer', 'Read-only access to dashboard');

-- User-Role mapping
CREATE TABLE user_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role_id)
);

CREATE INDEX idx_user_roles_user ON user_roles(user_id);
CREATE INDEX idx_user_roles_role ON user_roles(role_id);

-- Projects
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gitlab_project_id BIGINT UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    gitlab_url TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_projects_gitlab_id ON projects(gitlab_project_id);
CREATE INDEX idx_projects_active ON projects(is_active);

-- Project Permissions (user access to projects)
CREATE TABLE project_permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    can_manage BOOLEAN DEFAULT false,
    can_set_priority BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, project_id)
);

CREATE INDEX idx_project_permissions_user ON project_permissions(user_id);
CREATE INDEX idx_project_permissions_project ON project_permissions(project_id);

-- Project Configuration
CREATE TABLE project_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID UNIQUE NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    target_branches JSONB NOT NULL DEFAULT '[]', -- Array of target branch names
    batch_size INTEGER NOT NULL DEFAULT 5,
    polling_interval_seconds INTEGER DEFAULT 300,
    labels JSONB NOT NULL DEFAULT '{}', -- Custom labels configuration
    webhook_enabled BOOLEAN DEFAULT true,
    ai_debug_enabled BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_project_config_project ON project_config(project_id);

-- Merge Requests
CREATE TABLE merge_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    gitlab_mr_iid BIGINT NOT NULL,
    gitlab_mr_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    source_branch VARCHAR(255) NOT NULL,
    target_branch VARCHAR(255) NOT NULL,
    author VARCHAR(255),
    status VARCHAR(50) NOT NULL, -- recognized, not_ready, ready_to_merge, merging, merged, rejected, failed
    rejection_count INTEGER DEFAULT 0,
    rejection_reason TEXT,
    priority INTEGER DEFAULT 0, -- Higher number = higher priority
    pipeline_status VARCHAR(50),
    is_approved BOOLEAN DEFAULT false,
    is_assigned BOOLEAN DEFAULT false,
    labels JSONB DEFAULT '[]',
    recognized_at TIMESTAMP WITH TIME ZONE,
    merged_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, gitlab_mr_iid)
);

CREATE INDEX idx_mrs_project ON merge_requests(project_id);
CREATE INDEX idx_mrs_status ON merge_requests(status);
CREATE INDEX idx_mrs_target_branch ON merge_requests(target_branch);
CREATE INDEX idx_mrs_priority ON merge_requests(priority DESC);
CREATE INDEX idx_mrs_recognized_at ON merge_requests(recognized_at);
CREATE INDEX idx_mrs_gitlab_iid ON merge_requests(gitlab_mr_iid);

-- Batch Operations
CREATE TABLE batch_operations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    target_branch VARCHAR(255) NOT NULL,
    batch_branch VARCHAR(255) NOT NULL,
    batch_mr_iid BIGINT,
    batch_mr_id BIGINT,
    mr_ids JSONB NOT NULL, -- Array of MR UUIDs in this batch
    status VARCHAR(50) NOT NULL, -- pending, pipeline_running, pipeline_success, pipeline_failed, merging, completed, failed
    pipeline_status VARCHAR(50),
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_batch_ops_project ON batch_operations(project_id);
CREATE INDEX idx_batch_ops_status ON batch_operations(status);
CREATE INDEX idx_batch_ops_started ON batch_operations(started_at);

-- Merge History (audit log)
CREATE TABLE merge_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mr_id UUID NOT NULL REFERENCES merge_requests(id) ON DELETE CASCADE,
    batch_operation_id UUID REFERENCES batch_operations(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL, -- recognized, rejected, merged, failed, priority_set, label_added
    details JSONB,
    performed_by VARCHAR(255) DEFAULT 'merge-assist',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_merge_history_mr ON merge_history(mr_id);
CREATE INDEX idx_merge_history_action ON merge_history(action);
CREATE INDEX idx_merge_history_created ON merge_history(created_at DESC);

-- Logs (application logs)
CREATE TABLE logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    worker_pod_id VARCHAR(255),
    level VARCHAR(20) NOT NULL, -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    message TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_logs_project ON logs(project_id);
CREATE INDEX idx_logs_level ON logs(level);
CREATE INDEX idx_logs_created ON logs(created_at DESC);
CREATE INDEX idx_logs_worker ON logs(worker_pod_id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_project_config_updated_at BEFORE UPDATE ON project_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_merge_requests_updated_at BEFORE UPDATE ON merge_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE users IS 'User accounts for authentication and authorization';
COMMENT ON TABLE roles IS 'Role definitions for RBAC';
COMMENT ON TABLE projects IS 'GitLab projects onboarded to Merge Assist';
COMMENT ON TABLE project_config IS 'Per-project configuration including batch size and labels';
COMMENT ON TABLE merge_requests IS 'Tracked merge requests with current status';
COMMENT ON TABLE batch_operations IS 'Batch merge operations tracking';
COMMENT ON TABLE merge_history IS 'Audit log of all MR actions';
COMMENT ON TABLE logs IS 'Application logs from all services';
