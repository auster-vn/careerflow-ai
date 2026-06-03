import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from root of project
base_dir = Path(__file__).resolve().parent.parent.parent
env_path = base_dir / ".env"
load_dotenv(dotenv_path=env_path)

# Standard config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(base_dir / "data" / "careerflow.db"))
LANCEDB_URI = os.getenv("LANCEDB_URI", str(base_dir / "data" / "vectors"))
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# MLOps & MLflow Tracking Configs
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

# Data Lakehouse & MinIO S3 Credentials
MINIO_ENDPOINT_URL = os.getenv("MINIO_ENDPOINT_URL", "http://localhost:9000")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin123")
S3_BRONZE_BUCKET = os.getenv("S3_BRONZE_BUCKET", "bronze")
S3_SILVER_BUCKET = os.getenv("S3_SILVER_BUCKET", "silver")

# Prefect Orchestrator Configs
PREFECT_API_URL = os.getenv("PREFECT_API_URL", "http://localhost:4200/api")

# Local directories bootstrapper
data_dir = Path(DATABASE_PATH).parent
data_dir.mkdir(parents=True, exist_ok=True)

# Cache folders for local parquets
local_parquet_dir = data_dir / "medallion"
local_parquet_dir.mkdir(parents=True, exist_ok=True)

print(f"[CareerFlow Config] Loaded successfully. MinIO: {MINIO_ENDPOINT_URL} | MLflow: {MLFLOW_TRACKING_URI}")
