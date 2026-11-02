CREATE OR REPLACE FUNCTION rag_metrics() RETURNS TABLE(
 queued_jobs bigint,failed_jobs bigint,worker_alive bigint,
 query_total bigint,query_failed bigint,query_cancelled bigint,
 query_seconds double precision,first_token_seconds double precision,first_token_count bigint
) LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT
 (SELECT count(*) FROM public.rag_jobs j JOIN public.rag_versions v ON v.id=j.version_id
  JOIN public.rag_documents d ON d.id=v.document_id WHERE d.deleted_at IS NULL AND j.status IN ('queued','processing')),
 (SELECT count(*) FROM public.rag_jobs j JOIN public.rag_versions v ON v.id=j.version_id
  JOIN public.rag_documents d ON d.id=v.document_id WHERE d.deleted_at IS NULL AND j.status='failed'),
 (SELECT CASE WHEN EXISTS(SELECT 1 FROM public.rag_workers WHERE heartbeat_at>now()-interval '30 seconds') THEN 1 ELSE 0 END)::bigint,
 count(*),count(*) FILTER(WHERE outcome='failed'),count(*) FILTER(WHERE outcome='cancelled'),
 COALESCE(sum(duration_ms),0)::double precision/1000,
 COALESCE(sum(first_token_ms),0)::double precision/1000,count(first_token_ms)
 FROM public.rag_query_runs
 $$;
