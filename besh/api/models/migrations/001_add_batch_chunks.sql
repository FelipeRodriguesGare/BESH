-- Migration: Add batch_chunks table for chunked batch processing
-- This enables processing large batch files (1M+ requests) by splitting them
-- into smaller chunks that can be processed in parallel

CREATE TABLE IF NOT EXISTS batch_chunks (
    id SERIAL PRIMARY KEY,
    batch_id VARCHAR(255) NOT NULL,
    chunk_id INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    output_file_id VARCHAR(255),
    completed_at TIMESTAMP,
    error TEXT,
    request_count INTEGER DEFAULT 0,
    successful_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(batch_id, chunk_id),
    FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE CASCADE
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_batch_chunks_batch_id ON batch_chunks(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_chunks_status ON batch_chunks(status);
CREATE INDEX IF NOT EXISTS idx_batch_chunks_batch_status ON batch_chunks(batch_id, status);

