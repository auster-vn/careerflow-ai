import boto3
import polars as pl
import duckdb
from io import BytesIO
from datetime import datetime
from botocore.client import Config
from app.config import (
    MINIO_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    S3_BRONZE_BUCKET, S3_SILVER_BUCKET, DATABASE_PATH
)

def get_s3_client():
    """Create a boto3 S3 client configured for local MinIO."""
    return boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT_URL,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        config=Config(signature_version='s3v4')
    )

def init_s3_buckets():
    """Ensure all required MinIO Medallion buckets exist."""
    s3 = get_s3_client()
    required_buckets = [S3_BRONZE_BUCKET, S3_SILVER_BUCKET, "mlflow-artifacts"]
    for bucket in required_buckets:
        try:
            s3.head_bucket(Bucket=bucket)
            print(f"[Lakehouse S3] Bucket '{bucket}' already exists.")
        except Exception:
            try:
                s3.create_bucket(Bucket=bucket)
                print(f"[Lakehouse S3] Created bucket '{bucket}' successfully.")
            except Exception as e:
                print(f"[Lakehouse S3 Error] Failed to create bucket '{bucket}': {e}")

def write_to_bronze_lake(jobs_data: list):
    """
    Ingests raw scraped job listings, wraps them into a Polars DataFrame,
    converts to Parquet bytes, and writes to MinIO Bronze.
    """
    if not jobs_data:
        return
        
    s3 = get_s3_client()
    init_s3_buckets()
    
    # Ingest using Polars
    df_raw = pl.DataFrame(jobs_data)
    
    # Add ingestion timestamps
    df_raw = df_raw.with_columns([
        pl.lit(datetime.now().isoformat()).alias("ingested_at")
    ])
    
    # Serialize to Parquet bytes
    buffer = BytesIO()
    df_raw.write_parquet(buffer)
    buffer.seek(0)
    
    # Save to partitioned structure in S3 Bronze
    now = datetime.now()
    s3_key = f"jobs_raw/year={now.year}/month={now.month:02d}/jobs_{int(now.timestamp())}.parquet"
    
    try:
        s3.put_object(
            Bucket=S3_BRONZE_BUCKET,
            Key=s3_key,
            Body=buffer.getvalue()
        )
        print(f"[Lakehouse Bronze] Uploaded raw batch parquet to s3://{S3_BRONZE_BUCKET}/{s3_key}")
        return s3_key
    except Exception as e:
        print(f"[Lakehouse Bronze Error] S3 upload failed: {e}")
        return None

def run_silver_etl_pipeline():
    """
    Prefect-orchestrated Flow Task:
    1. Downloads all Bronze Parquet partitions.
    2. Runs Polars cleaning: deduplication, lowercase column normalization,
       salary extraction, and string trimmings.
    3. Uploads deduplicated clean Parquet to MinIO Silver.

    Schema-resilient: uses diagonal_relaxed concat so Bronze files with
    different schemas (e.g. old files without 'source' column) are merged
    safely — missing columns are filled with null.
    """
    s3 = get_s3_client()
    init_s3_buckets()

    # Download all parquets under jobs_raw/ from Bronze
    try:
        response = s3.list_objects_v2(Bucket=S3_BRONZE_BUCKET, Prefix="jobs_raw/")
        if "Contents" not in response:
            print("[Lakehouse Silver warning] No Bronze parquets found to clean.")
            return False

        dfs = []
        for obj in response["Contents"]:
            s3_key = obj["Key"]
            try:
                file_bytes = s3.get_object(Bucket=S3_BRONZE_BUCKET, Key=s3_key)["Body"].read()
                df_part = pl.read_parquet(BytesIO(file_bytes))
                dfs.append(df_part)
            except Exception as read_err:
                print(f"[Lakehouse Silver] Skipping unreadable file {s3_key}: {read_err}")

        if not dfs:
            return False

        # Concatenate Bronze partitions with schema-relaxed mode
        # diagonal_relaxed: fills missing columns with null instead of erroring
        if len(dfs) == 1:
            df_bronze = dfs[0]
        else:
            df_bronze = pl.concat(dfs, how="diagonal_relaxed")

        # Ensure required columns exist with defaults
        required_cols = {
            "id": pl.Utf8,
            "company_name": pl.Utf8,
            "job_title": pl.Utf8,
            "job_url": pl.Utf8,
            "job_description": pl.Utf8,
            "status": pl.Utf8,
            "salary_range": pl.Utf8,
            "notes": pl.Utf8,
            "source": pl.Utf8,
            "ingested_at": pl.Utf8,
        }
        for col_name, col_type in required_cols.items():
            if col_name not in df_bronze.columns:
                df_bronze = df_bronze.with_columns(
                    pl.lit(None).cast(col_type).alias(col_name)
                )

        # POLARS ETL CLEANING PIPELINE:
        # 1. Deduplicate on company_name + job_title + job_url
        # 2. Clean string columns (strip whitespace)
        # 3. Fill missing salaries and source with defaults
        df_silver = (
            df_bronze
            .unique(subset=["company_name", "job_title", "job_url"])
            .with_columns([
                pl.col("company_name").str.strip_chars(),
                pl.col("job_title").str.strip_chars(),
                pl.col("salary_range").fill_null("N/A").str.strip_chars(),
                pl.col("job_description").fill_null("").str.strip_chars(),
                pl.col("source").fill_null("Unknown").str.strip_chars(),
                pl.lit(datetime.now().isoformat()).alias("cleaned_at")
            ])
        )

        # Serialize Silver DataFrame to Parquet
        silver_buffer = BytesIO()
        df_silver.write_parquet(silver_buffer)
        silver_buffer.seek(0)

        # Upload clean Silver Parquet
        s3.put_object(
            Bucket=S3_SILVER_BUCKET,
            Key="jobs_clean/jobs_silver.parquet",
            Body=silver_buffer.getvalue()
        )
        print(f"[Lakehouse Silver] Successfully processed {df_silver.height} unique jobs to Silver Parquet.")
        return True
    except Exception as e:
        print(f"[Lakehouse Silver Error] Silver ETL pipeline failed: {e}")
        return False

def sync_lakehouse_to_duckdb():
    """
    DuckDB-Medallion Sync:
    Connects to the DuckDB Warehouse and directly runs an OLAP query loading
    our Silver Parquet data from S3 using httpfs, synchronizing it to the CRM database.
    """
    s3 = get_s3_client()
    try:
        # Download silver file locally or let DuckDB fetch it
        # To avoid complex SSL setup on local docker networks, we download the Silver Parquet bytes
        # and insert them directly into DuckDB which is extremely robust.
        silver_obj = s3.get_object(Bucket=S3_SILVER_BUCKET, Key="jobs_clean/jobs_silver.parquet")
        df_silver = pl.read_parquet(BytesIO(silver_obj["Body"].read()))
        
        conn = duckdb.connect(DATABASE_PATH)
        try:
            # Drop old temp table if exists
            conn.execute("DROP TABLE IF EXISTS silver_temp")
            
            # Register Polars DataFrame in DuckDB context
            conn.register("silver_temp", df_silver)
            
            # UPSERT clean jobs into applications CRM table
            conn.execute("""
            INSERT OR IGNORE INTO applications (id, company_name, job_title, job_url, job_description, status, salary_range, notes, applied_date, updated_date)
            SELECT 
                id,
                company_name,
                job_title,
                job_url,
                job_description,
                status,
                salary_range,
                notes,
                ingested_at,
                cleaned_at
            FROM silver_temp
            """)
            
            print("[Database Sync] Synchronized S3 Silver Lakehouse with local DuckDB CRM.")
            return True
        except Exception as ex:
            print(f"[Database Sync Error] DuckDB transaction failed: {ex}")
            return False
        finally:
            conn.close()
    except Exception as e:
        print(f"[Database Sync Warning] MinIO Silver Parquet is not uploaded yet: {e}")
        return False

if __name__ == "__main__":
    init_s3_buckets()
    # Seed dummy scraped jobs
    dummy_scraped = [
        {
            "id": "1",
            "company_name": "Netflix  ",
            "job_title": "  Senior MLE",
            "job_url": "https://netflix.com/careers/1",
            "job_description": "We are looking for a Senior Machine Learning Engineer with Python, PyTorch, and Docker experience.",
            "status": "WISHLIST",
            "salary_range": "$180,000 - $220,000",
            "notes": "Emailed recruiter John"
        },
        {
            "id": "2",
            "company_name": "Stripe",
            "job_title": "Lead Data Engineer",
            "job_url": "https://stripe.com/careers/2",
            "job_description": "Join Stripe as a Lead Data Engineer. Requires robust Python, Spark, SQL, and Prefect knowledge.",
            "status": "APPLIED",
            "salary_range": "$160,000 - $200,000",
            "notes": "Applied on portal"
        }
    ]
    write_to_bronze_lake(dummy_scraped)
    run_silver_etl_pipeline()
    sync_lakehouse_to_duckdb()
