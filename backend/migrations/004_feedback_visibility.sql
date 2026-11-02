-- Feedback is deliberately shared with workspace administrators; chat messages remain private.
CREATE POLICY workspace_admin_feedback ON rag_feedback FOR SELECT TO rag_app
 USING(rag_role(workspace_id)='admin');
