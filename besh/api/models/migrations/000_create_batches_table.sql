-- Create batches table
CREATE TABLE IF NOT EXISTS batches (
    id VARCHAR(50) PRIMARY KEY,
    object VARCHAR(20) DEFAULT 'batch',
    endpoint VARCHAR(100) NOT NULL,
    input_file_id VARCHAR(50) NOT NULL,
    completion_window VARCHAR(10) DEFAULT '24h',
    status VARCHAR(20) DEFAULT 'validating',
    output_file_id VARCHAR(50),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    in_progress_at TIMESTAMP,
    completed_at TIMESTAMP,
    failed_at TIMESTAMP,
    expired_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    expires_at TIMESTAMP,
    finalizing_at TIMESTAMP,
    
    -- Token usage and request count fields
    total_tokens INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    request_failed INTEGER DEFAULT 0,
    request_completed INTEGER DEFAULT 0,
    request_total INTEGER DEFAULT 0
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS ix_batches_status ON batches(status);
CREATE INDEX IF NOT EXISTS ix_batches_created_at ON batches(created_at);

