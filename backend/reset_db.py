import psycopg

# Note: We use the raw postgresql:// URI for the psycopg connection
DB_URI = "postgresql://rag_user:securepassword@localhost:5432/rag_db"

try:
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS langchain_pg_embedding CASCADE;")
        conn.execute("DROP TABLE IF EXISTS langchain_pg_collection CASCADE;")
    print("Success: Tables dropped! The database is ready for new vectors.")
except Exception as e:
    print(f"Error: {e}")