ALTER TABLE rag_users ADD COLUMN email_verified boolean NOT NULL DEFAULT false;
UPDATE rag_users SET email_verified=true;
CREATE TABLE rag_action_tokens (
 token_hash text PRIMARY KEY, purpose text NOT NULL CHECK(purpose IN ('verify','reset','invite')),
 user_id uuid REFERENCES rag_users ON DELETE CASCADE, email text NOT NULL,
 workspace_id uuid REFERENCES rag_workspaces ON DELETE CASCADE, role text,
 expires_at timestamptz NOT NULL, used_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON rag_action_tokens(expires_at);
CREATE TABLE rag_mail_outbox (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), recipient text NOT NULL, subject text NOT NULL, body text NOT NULL,
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(), sent_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT,INSERT,UPDATE,DELETE ON rag_action_tokens TO rag_app;
GRANT SELECT,INSERT,UPDATE ON rag_mail_outbox TO rag_app;
ALTER TABLE rag_documents ADD COLUMN restricted boolean NOT NULL DEFAULT false;
CREATE TABLE rag_document_access (
 document_id uuid NOT NULL REFERENCES rag_documents ON DELETE CASCADE,
 user_id uuid NOT NULL REFERENCES rag_users ON DELETE CASCADE, PRIMARY KEY(document_id,user_id)
);
GRANT SELECT,INSERT,DELETE ON rag_document_access TO rag_app;
CREATE FUNCTION rag_can_read_document(doc uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
 SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.rag_documents d WHERE d.id=doc AND
   public.rag_role(d.workspace_id) IS NOT NULL AND
   (NOT d.restricted OR public.rag_role(d.workspace_id)='admin' OR
    d.created_by=NULLIF(current_setting('app.user_id',true),'')::uuid OR
    EXISTS(SELECT 1 FROM public.rag_document_access a WHERE a.document_id=d.id AND a.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid)))
 $$;
REVOKE ALL ON FUNCTION rag_can_read_document(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rag_can_read_document(uuid) TO rag_app;
ALTER TABLE rag_document_access ENABLE ROW LEVEL SECURITY;
CREATE POLICY acl_read ON rag_document_access FOR SELECT TO rag_app USING(rag_can_read_document(document_id));
CREATE POLICY acl_write ON rag_document_access FOR ALL TO rag_app
 USING(EXISTS(SELECT 1 FROM rag_documents d WHERE d.id=document_id AND rag_role(d.workspace_id)='admin'))
 WITH CHECK(EXISTS(SELECT 1 FROM rag_documents d WHERE d.id=document_id AND rag_role(d.workspace_id)='admin'));
-- Restrictive policies combine with every pre-existing permissive policy, including editor writes.
CREATE POLICY document_acl ON rag_documents AS RESTRICTIVE TO rag_app
 USING(rag_can_read_document(id)) WITH CHECK(rag_role(workspace_id) IS NOT NULL);
CREATE POLICY version_acl ON rag_versions AS RESTRICTIVE TO rag_app
 USING(rag_can_read_document(document_id)) WITH CHECK(rag_can_read_document(document_id));
CREATE POLICY chunk_acl ON rag_chunks AS RESTRICTIVE TO rag_app
 USING(rag_can_read_document(document_id)) WITH CHECK(rag_can_read_document(document_id));
CREATE POLICY job_acl ON rag_jobs AS RESTRICTIVE TO rag_app
 USING(EXISTS(SELECT 1 FROM rag_versions v WHERE v.id=version_id))
 WITH CHECK(EXISTS(SELECT 1 FROM rag_versions v WHERE v.id=version_id));
ALTER TABLE rag_conversations ADD COLUMN pinned boolean NOT NULL DEFAULT false;
CREATE TABLE rag_oidc_identities (
 issuer text NOT NULL, subject text NOT NULL, user_id uuid NOT NULL REFERENCES rag_users ON DELETE CASCADE,
 PRIMARY KEY(issuer,subject)
);
GRANT SELECT,INSERT ON rag_oidc_identities TO rag_app;
CREATE FUNCTION rag_accept_invitation(digest text) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog,public AS $$
 DECLARE a public.rag_action_tokens; u uuid := NULLIF(current_setting('app.user_id',true),'')::uuid;
 BEGIN
 SELECT t.* INTO a FROM public.rag_action_tokens t JOIN public.rag_users usr ON usr.id=u
 WHERE t.token_hash=digest AND t.purpose='invite' AND t.email=usr.email AND usr.email_verified AND NOT usr.disabled
 AND t.used_at IS NULL AND t.expires_at>now() FOR UPDATE OF t;
 IF NOT FOUND THEN RAISE EXCEPTION 'Invalid invitation'; END IF;
 INSERT INTO public.rag_memberships(workspace_id,user_id,role) VALUES(a.workspace_id,u,a.role) ON CONFLICT DO NOTHING;
 UPDATE public.rag_action_tokens SET used_at=now() WHERE token_hash=digest;
 INSERT INTO public.rag_audit(workspace_id,user_id,action) VALUES(a.workspace_id,u,'invitation.accepted');
 END $$;
REVOKE ALL ON FUNCTION rag_accept_invitation(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rag_accept_invitation(text) TO rag_app;
