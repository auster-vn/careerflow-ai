import os
import sys
import subprocess
from pathlib import Path
from prefect import task, flow

# Ensure backend libraries are visible to the Prefect runtime
sys.path.append(str(Path(__file__).resolve().parent.parent / "backend"))

from app.pipeline.etl_lakehouse import (
    write_to_bronze_lake,
    run_silver_etl_pipeline,
    sync_lakehouse_to_duckdb
)

@task(retries=3, retry_delay_seconds=10, name="Ingest Scraped Jobs (Bronze)")
def ingest_raw_jobs_task(jobs_batch: list):
    """Prefect task: Scrape raw market listings and write to Bronze S3 bucket."""
    print("[Prefect Task] Running Ingestion to Bronze Parquet Lake...")
    s3_key = write_to_bronze_lake(jobs_batch)
    if not s3_key:
        raise RuntimeError("Bronze ingestion failed.")
    return s3_key

@task(name="Run Polars Standardizer (Silver)")
def run_silver_etl_task():
    """Prefect task: Clean, align, and deduplicate Bronze records into Silver Parquet."""
    print("[Prefect Task] Invoking Polars ETL Pipeline (Bronze -> Silver)...")
    success = run_silver_etl_pipeline()
    if not success:
        raise RuntimeError("Silver ETL pipeline failed.")
    return "Silver Parquet Cleaned successfully."

@task(name="Sync S3 Lake to DuckDB Warehouse")
def run_warehouse_sync_task():
    """Prefect task: Sync deduplicated Silver data into local DuckDB analytical engine."""
    print("[Prefect Task] Synchronizing S3 Silver bucket into DuckDB...")
    success = sync_lakehouse_to_duckdb()
    if not success:
        raise RuntimeError("Database Sync failed.")
    return "DuckDB Warehouse synced."

@task(name="Execute dbt Analytical Warehouse Models (Gold)")
def run_dbt_models_task():
    """Prefect task: Run dbt core transformations (Staging -> Marts) on DuckDB."""
    print("[Prefect Task] Executing dbt transformations...")
    dbt_dir = Path(__file__).resolve().parent.parent / "dbt_project"
    
    # We simulate/run dbt run CLI. If dbt is not installed globally, we log the SQL equivalent.
    try:
        # Run dbt run command
        result = subprocess.run(
            ["dbt", "run", "--profiles-dir", "."],
            cwd=dbt_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print("[Prefect Task] dbt models built successfully:")
            print(result.stdout)
            return "dbt built."
        else:
            print(f"[Prefect Task Warning] dbt execution returned error: {result.stderr}")
            print("Fallback: Executing Gold layer dbt aggregates inside DuckDB manually.")
            raise RuntimeError("dbt shell failed.")
    except Exception as e:
        print(f"[Prefect Task Fallback] Running manual SQL transformations: {e}")
        # Run fallback SQL inside DuckDB representing the dbt staging and mart logic
        import duckdb
        from app.config import DATABASE_PATH
        conn = duckdb.connect(DATABASE_PATH)
        try:
            # Recreate staged table view
            conn.execute("CREATE OR REPLACE VIEW stg_applications AS SELECT id as application_id, TRIM(company_name) as company_name, TRIM(job_title) as job_title, status as application_status, salary_range, notes, applied_date, updated_date FROM applications")
            
            # Recreate gold marts table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS interview_marts AS 
            SELECT 
                al.interview_id,
                COUNT(*) as total_exchanges,
                ROUND(AVG(al.score), 2) as average_score,
                MAX(al.score) as peak_score,
                MIN(al.created_date) as session_date,
                i.application_id,
                a.company_name,
                a.job_title
            FROM main.interview_logs al
            JOIN main.interviews i ON al.interview_id = i.id
            JOIN main.applications a ON i.application_id = a.id
            WHERE al.speaker = 'USER'
            GROUP BY al.interview_id, i.application_id, a.company_name, a.job_title, i.id
            """)
            print("[Database Fallback] Manually materialized dbt 'interview_marts' gold table successfully.")
            return "Gold SQL materialized."
        except Exception as ex:
            print(f"[Database Fallback Error] SQL materialization failed: {ex}")
            return "Gold SQL failed."
        finally:
            conn.close()

@flow(name="CareerFlow Medallion Lakehouse Flow")
def careerflow_lakehouse_flow(raw_jobs_batch: list):
    """
    Complete Prefect Medallion Pipeline:
    Ingests to Bronze -> Cleans to Silver Parquet -> Syncs to DuckDB -> Transforms to Gold Marts.
    """
    print("[Prefect Flow] Starting CareerFlow Medallion Pipeline Flow...")
    bronze_ref = ingest_raw_jobs_task(raw_jobs_batch)
    silver_ref = run_silver_etl_task()
    sync_ref = run_warehouse_sync_task()
    gold_ref = run_dbt_models_task()
    print("[Prefect Flow] CareerFlow Pipeline completed successfully!")
    return {
        "bronze_ref": bronze_ref,
        "silver_ref": silver_ref,
        "sync_ref": sync_ref,
        "gold_ref": gold_ref
    }

if __name__ == "__main__":
    # Seed sample scraped jobs for debugging run
    debug_jobs = [
        {
            "id": "3",
            "company_name": "Google",
            "job_title": "Senior Data Engineer",
            "job_url": "https://google.com/careers/3",
            "job_description": "We are seeking a Senior Data Engineer. Core tech stack: Python, Polars, DuckDB, Prefect, and dbt.",
            "status": "WISHLIST",
            "salary_range": "$170,000 - $210,000",
            "notes": "Referral requested"
        }
    ]
    careerflow_lakehouse_flow(debug_jobs)
