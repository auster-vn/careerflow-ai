import duckdb
import lancedb
from pathlib import Path
from app.config import DATABASE_PATH, LANCEDB_URI

def get_db_connection():
    """Get a connection to the DuckDB database file."""
    return duckdb.connect(DATABASE_PATH)

def init_duckdb():
    """Initialize the DuckDB tables if they don't exist."""
    conn = get_db_connection()
    try:
        # Create applications CRM table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id VARCHAR PRIMARY KEY,
            company_name VARCHAR NOT NULL,
            job_title VARCHAR NOT NULL,
            job_url VARCHAR,
            job_description TEXT,
            status VARCHAR DEFAULT 'WISHLIST',
            salary_range VARCHAR,
            notes TEXT,
            applied_date VARCHAR,
            updated_date VARCHAR
        )
        """)

        # Create resumes table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS resumes (
            id VARCHAR PRIMARY KEY,
            file_name VARCHAR NOT NULL,
            parsed_text TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_date VARCHAR
        )
        """)

        # Create interviews table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS interviews (
            id VARCHAR PRIMARY KEY,
            application_id VARCHAR NOT NULL,
            interviewer_name VARCHAR,
            interviewer_role VARCHAR,
            created_date VARCHAR,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        )
        """)

        # Create interview logs (chat transcripts + AI grading)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS interview_logs (
            id VARCHAR PRIMARY KEY,
            interview_id VARCHAR NOT NULL,
            speaker VARCHAR NOT NULL, -- 'AI' or 'USER'
            message TEXT NOT NULL,
            score INTEGER,            -- 0-10 grade (only for USER answers)
            feedback TEXT,            -- feedback / suggestions (only for USER answers)
            created_date VARCHAR,
            FOREIGN KEY (interview_id) REFERENCES interviews(id)
        )
        """)
        
        print("[Database] DuckDB schema initialized successfully.")
    except Exception as e:
        print(f"[Database Error] DuckDB initialization failed: {e}")
    finally:
        conn.close()

def init_lancedb():
    """Initialize the LanceDB instance and tables."""
    try:
        # Ensure the vector storage directory exists
        Path(LANCEDB_URI).mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(LANCEDB_URI)
        
        # LanceDB tables are created dynamically when data is inserted,
        # but we can verify the connection is healthy.
        print(f"[Database] LanceDB connected successfully at {LANCEDB_URI}")
        return db
    except Exception as e:
        print(f"[Database Error] LanceDB initialization failed: {e}")
        return None

def init_databases():
    """End-to-end database bootstrapping."""
    init_duckdb()
    init_lancedb()

if __name__ == "__main__":
    init_databases()
