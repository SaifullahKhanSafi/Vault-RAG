CREATE TABLE rag_extracted_pages (
 version_id uuid NOT NULL, document_id uuid NOT NULL, workspace_id uuid NOT NULL,
 page integer NOT NULL CHECK(page>0), method text NOT NULL, text_content text NOT NULL,
 tables jsonb NOT NULL DEFAULT '[]', PRIMARY KEY(version_id,page),
 FOREIGN KEY(version_id,workspace_id) REFERENCES rag_versions(id,workspace_id) ON DELETE CASCADE,
 FOREIGN KEY(document_id,workspace_id) REFERENCES rag_documents(id,workspace_id) ON DELETE CASCADE
);
ALTER TABLE rag_extracted_pages ENABLE ROW LEVEL SECURITY;
CREATE POLICY page_read ON rag_extracted_pages FOR SELECT TO rag_app USING(rag_can_read_document(document_id));
CREATE POLICY worker_access ON rag_extracted_pages FOR ALL TO rag_worker USING(true) WITH CHECK(true);
GRANT SELECT ON rag_extracted_pages TO rag_app;
GRANT SELECT,INSERT,DELETE ON rag_extracted_pages TO rag_worker;
