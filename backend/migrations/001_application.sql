CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE rag_users (
 id uuid PRIMARY KEY, email text NOT NULL UNIQUE, name text NOT NULL,
 password_hash text NOT NULL, disabled boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE rag_workspaces (
 id uuid PRIMARY KEY, name text NOT NULL, created_by uuid NOT NULL REFERENCES rag_users,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE rag_memberships (
 workspace_id uuid REFERENCES rag_workspaces ON DELETE CASCADE,
 user_id uuid REFERENCES rag_users ON DELETE CASCADE,
 role text NOT NULL CHECK(role IN ('admin','editor','reader')),
 PRIMARY KEY(workspace_id,user_id)
);
CREATE FUNCTION rag_role(w uuid) RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
 SET search_path=pg_catalog,public AS $$
 SELECT role FROM public.rag_memberships
 WHERE workspace_id=w AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid
 $$;
REVOKE ALL ON FUNCTION rag_role(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rag_role(uuid) TO rag_app,rag_worker;
CREATE FUNCTION rag_create_workspace(label text) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog,public AS $$
 DECLARE w uuid := gen_random_uuid(); u uuid := NULLIF(current_setting('app.user_id',true),'')::uuid;
 BEGIN
 IF u IS NULL OR NOT EXISTS(SELECT 1 FROM public.rag_users WHERE id=u AND NOT disabled)
 THEN RAISE EXCEPTION 'Authentication required'; END IF;
 IF length(trim(label)) NOT BETWEEN 1 AND 120 THEN RAISE EXCEPTION 'Invalid workspace name'; END IF;
 INSERT INTO public.rag_workspaces(id,name,created_by) VALUES(w,trim(label),u);
 INSERT INTO public.rag_memberships VALUES(w,u,'admin');
 RETURN w;
 END $$;
REVOKE ALL ON FUNCTION rag_create_workspace(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rag_create_workspace(text) TO rag_app;
CREATE TABLE rag_sessions (
 token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES rag_users ON DELETE CASCADE,
 expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON rag_sessions(expires_at);
CREATE TABLE rag_documents (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES rag_workspaces,
 name text NOT NULL, created_by uuid NOT NULL REFERENCES rag_users,
 active_version uuid, deleted_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(id,workspace_id)
);
CREATE UNIQUE INDEX rag_document_names ON rag_documents(workspace_id,name) WHERE deleted_at IS NULL;
CREATE TABLE rag_versions (
 id uuid PRIMARY KEY, document_id uuid NOT NULL, workspace_id uuid NOT NULL,
 version integer NOT NULL, checksum text, storage_key text,
 embedding_model text NOT NULL, status text NOT NULL DEFAULT 'queued'
 CHECK(status IN ('queued','processing','ready','failed')),
 chunk_count integer NOT NULL DEFAULT 0, size_bytes bigint NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(id,workspace_id), UNIQUE(document_id,version), UNIQUE(document_id,checksum),
 FOREIGN KEY(document_id,workspace_id) REFERENCES rag_documents(id,workspace_id) ON DELETE CASCADE
);
ALTER TABLE rag_documents ADD CONSTRAINT rag_active_version_fk
 FOREIGN KEY(active_version,workspace_id) REFERENCES rag_versions(id,workspace_id);
CREATE TABLE rag_chunks (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, document_id uuid NOT NULL,
 version_id uuid NOT NULL, page integer NOT NULL CHECK(page>0), page_label text,
 content text NOT NULL, embedding vector(768) NOT NULL,
 search_vector tsvector GENERATED ALWAYS AS(to_tsvector('english',content)) STORED,
 UNIQUE(version_id,id),
 FOREIGN KEY(document_id,workspace_id) REFERENCES rag_documents(id,workspace_id) ON DELETE CASCADE,
 FOREIGN KEY(version_id,workspace_id) REFERENCES rag_versions(id,workspace_id) ON DELETE CASCADE
);
CREATE INDEX ON rag_chunks USING gin(search_vector);
CREATE INDEX ON rag_chunks(workspace_id,version_id);
CREATE TABLE rag_jobs (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, version_id uuid NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','processing','ready','failed','cancelled')),
 progress integer NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
 attempts integer NOT NULL DEFAULT 0, max_attempts integer NOT NULL DEFAULT 3,
 error text, locked_by text, lease_until timestamptz, available_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(version_id,workspace_id) REFERENCES rag_versions(id,workspace_id) ON DELETE CASCADE
);
CREATE INDEX ON rag_jobs(status,available_at);
CREATE TABLE rag_conversations (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES rag_workspaces,
 user_id uuid NOT NULL REFERENCES rag_users, title text NOT NULL DEFAULT 'New chat',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 busy_until timestamptz, UNIQUE(id,workspace_id,user_id)
);
CREATE TABLE rag_messages (
 sequence bigint GENERATED ALWAYS AS IDENTITY,
 id uuid PRIMARY KEY, conversation_id uuid NOT NULL, workspace_id uuid NOT NULL,
 user_id uuid NOT NULL, role text NOT NULL CHECK(role IN ('user','assistant')),
 content text NOT NULL, sources jsonb NOT NULL DEFAULT '[]',
 status text NOT NULL DEFAULT 'complete' CHECK(status IN ('complete','streaming','failed','cancelled')),
 request_id uuid, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(conversation_id,workspace_id,user_id) REFERENCES rag_conversations(id,workspace_id,user_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX rag_message_request ON rag_messages(conversation_id,request_id,role) WHERE request_id IS NOT NULL;
CREATE INDEX ON rag_messages(conversation_id,created_at);
CREATE TABLE rag_feedback (
 message_id uuid PRIMARY KEY REFERENCES rag_messages ON DELETE CASCADE,
 workspace_id uuid NOT NULL REFERENCES rag_workspaces, user_id uuid NOT NULL REFERENCES rag_users,
 rating integer NOT NULL CHECK(rating IN (-1,1)), note text NOT NULL DEFAULT '',
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE rag_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES rag_workspaces,
 user_id uuid NOT NULL REFERENCES rag_users, action text NOT NULL, target text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE rag_query_runs (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES rag_workspaces, user_id uuid NOT NULL REFERENCES rag_users,
 conversation_id uuid REFERENCES rag_conversations ON DELETE SET NULL,
 outcome text NOT NULL, duration_ms integer NOT NULL, first_token_ms integer,
 retrieval_ms integer, model text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE rag_rate_limits (key text PRIMARY KEY, count integer NOT NULL, expires_at timestamptz NOT NULL);
CREATE TABLE rag_model_leases (id uuid PRIMARY KEY, owner text NOT NULL, expires_at timestamptz NOT NULL);
CREATE TABLE rag_workers (id text PRIMARY KEY, heartbeat_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE rag_http_metrics (
 method text NOT NULL, route text NOT NULL, status integer NOT NULL,
 requests bigint NOT NULL DEFAULT 0, duration_ms double precision NOT NULL DEFAULT 0,
 PRIMARY KEY(method,route,status)
);
GRANT USAGE ON SCHEMA public TO rag_app,rag_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON rag_users,rag_sessions,rag_rate_limits,rag_model_leases TO rag_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON rag_workspaces,rag_memberships,rag_documents,rag_versions,rag_chunks,
 rag_jobs,rag_conversations,rag_messages,rag_feedback TO rag_app;
GRANT SELECT,INSERT ON rag_audit,rag_query_runs TO rag_app;
GRANT USAGE ON SEQUENCE rag_audit_id_seq TO rag_app;
GRANT USAGE ON SEQUENCE rag_messages_sequence_seq TO rag_app;
GRANT SELECT,INSERT,UPDATE ON rag_http_metrics TO rag_app;
GRANT SELECT ON rag_workers TO rag_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON rag_documents,rag_versions,rag_chunks,rag_jobs,rag_model_leases,rag_workers TO rag_worker;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['rag_documents','rag_versions','rag_chunks','rag_jobs'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY workspace_read ON %I FOR SELECT TO rag_app USING (rag_role(workspace_id) IS NOT NULL)',t);
  EXECUTE format('CREATE POLICY workspace_write ON %I FOR ALL TO rag_app USING (rag_role(workspace_id) IN (''admin'',''editor'')) WITH CHECK (rag_role(workspace_id) IN (''admin'',''editor''))',t);
  EXECUTE format('CREATE POLICY worker_access ON %I TO rag_worker USING (true) WITH CHECK (true)',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['rag_conversations','rag_messages','rag_feedback'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY personal_access ON %I TO rag_app USING (user_id=NULLIF(current_setting(''app.user_id'',true),'''')::uuid AND rag_role(workspace_id) IS NOT NULL) WITH CHECK (user_id=NULLIF(current_setting(''app.user_id'',true),'''')::uuid AND rag_role(workspace_id) IS NOT NULL)',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['rag_audit','rag_query_runs'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY admin_read ON %I FOR SELECT TO rag_app USING (rag_role(workspace_id)=''admin'')',t);
  EXECUTE format('CREATE POLICY own_insert ON %I FOR INSERT TO rag_app WITH CHECK (user_id=NULLIF(current_setting(''app.user_id'',true),'''')::uuid AND rag_role(workspace_id) IS NOT NULL)',t);
 END LOOP;
END $$;
ALTER TABLE rag_workspaces ENABLE ROW LEVEL SECURITY;
CREATE POLICY workspace_read ON rag_workspaces FOR SELECT TO rag_app USING(rag_role(id) IS NOT NULL);
CREATE POLICY workspace_edit ON rag_workspaces FOR UPDATE TO rag_app USING(rag_role(id)='admin') WITH CHECK(rag_role(id)='admin');
ALTER TABLE rag_memberships ENABLE ROW LEVEL SECURITY;
CREATE POLICY member_read ON rag_memberships FOR SELECT TO rag_app USING(rag_role(workspace_id) IS NOT NULL);
CREATE POLICY member_write ON rag_memberships TO rag_app USING(rag_role(workspace_id)='admin') WITH CHECK(rag_role(workspace_id)='admin');
