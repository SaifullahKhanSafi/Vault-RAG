ALTER TABLE rag_jobs ADD COLUMN trace_context jsonb NOT NULL DEFAULT '{}';
