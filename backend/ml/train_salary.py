import os
import sys
import duckdb
import numpy as np
import polars as pl
import xgboost as xgb
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error

# Add parent directories to sys.path to enable app module imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import DATABASE_PATH, MLFLOW_TRACKING_URI
from app.database import init_databases
from app.pipeline.parser import clean_and_tokenize, TECHNICAL_DICTIONARY

def load_training_data():
    """Load historical applications to train the salary regressor model."""
    init_databases() # Self-initialize DuckDB schemas if empty
    conn = duckdb.connect(DATABASE_PATH)
    try:
        # Fetch CRM jobs
        rows = conn.execute("SELECT id, company_name, job_title, salary_range, job_description FROM applications").fetchall()
        if len(rows) < 5:
            # Seed synthetic training rows if warehouse is empty
            print("[ML Salary] Insufficient real jobs. Generating synthetic rows to train XGBoost...")
            dummy_data = []
            companies = ["Google", "Stripe", "Netflix", "Meta", "Amazon", "Apple", "OpenAI", "Airbnb", "Uber", "ByteDance"]
            roles = ["Data Engineer", "Machine Learning Engineer", "Software Engineer", "Backend Developer"]
            skills_pool = [
                ("python, SQL, Spark, Docker, Prefect, dbt", 150000),
                ("python, PyTorch, LLM, Docker, Kubernetes, MLOps", 195000),
                ("javascript, typescript, React, Node, Express", 125000),
                ("golang, gRPC, kubernetes, microservices, sql", 165000),
                ("python, pandas, scikit-learn, XGBoost, SQL", 140000),
                ("scala, spark, kafka, flink, data lake", 175000),
                ("python, langchain, openai, embeddings, vector search", 185000),
                ("rust, WebAssembly, typescript, react, node", 155000),
                ("python, airflow, dbt, snowflake, bigquery", 145000),
                ("cpp, CUDA, pyTorch, deep learning, GPU", 210000)
            ]
            for i in range(100):
                comp = random_choice(companies)
                title = random_choice(roles)
                skills, salary = random_choice(skills_pool)
                # Introduce slight variance
                var = np.random.randint(-15000, 15000)
                dummy_data.append({
                    "id": f"dummy_{i}",
                    "company_name": comp,
                    "job_title": title,
                    "salary_range": f"${salary + var - 10000} - ${salary + var + 10000}",
                    "job_description": f"Hiring a {title} at {comp}. Core technologies: {skills}."
                })
            
            # Write dummy data to warehouse
            conn.execute("CREATE TABLE IF NOT EXISTS applications (id VARCHAR PRIMARY KEY, company_name VARCHAR, job_title VARCHAR, job_url VARCHAR, job_description TEXT, status VARCHAR, salary_range VARCHAR, notes TEXT, applied_date VARCHAR, updated_date VARCHAR)")
            for item in dummy_data:
                conn.execute(
                    "INSERT OR IGNORE INTO applications (id, company_name, job_title, job_description, status, salary_range, updated_date) VALUES (?, ?, ?, ?, 'WISHLIST', ?, ?)",
                    [item["id"], item["company_name"], item["job_title"], item["job_description"], item["salary_range"], "2026-06-02"]
                )
            rows = conn.execute("SELECT id, company_name, job_title, salary_range, job_description FROM applications").fetchall()
            
        return rows
    finally:
        conn.close()

def random_choice(lst):
    """Simple offline random choice implementation."""
    idx = np.random.randint(0, len(lst))
    return lst[idx]

def preprocess_and_train():
    """Extract features via Polars, train XGBoost Regressor, and track with MLflow."""
    import mlflow
    import mlflow.xgboost
    
    # 1. Set MLflow tracking URI
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("CareerFlow_Salary_Prediction")

    raw_data = load_training_data()
    
    # Feature engineering: check presence of hot technical keywords using Polars
    processed_records = []
    for row in raw_data:
        app_id, comp, title, salary_str, jd = row
        
        # Extract target salary (median numerical value)
        salary_nums = [int(s) for s in re_findall(r"\d+", salary_str.replace(",", ""))]
        if not salary_nums or len(salary_nums) < 2:
            # Fallback average
            target_salary = 140000.0
        else:
            # Median of range
            target_salary = float(np.mean(salary_nums))
            
        tokens = set(clean_and_tokenize(jd))
        
        # One-Hot encode core technical keywords
        feat = {
            "target": target_salary,
            "company_name_len": float(len(comp)),
            "jd_len": float(len(jd)),
            "is_mle": 1.0 if "ml" in title.lower() or "learning" in title.lower() or "ai" in title.lower() else 0.0,
            "is_de": 1.0 if "data" in title.lower() or "pipeline" in title.lower() or "etl" in title.lower() else 0.0
        }
        
        # Check presence of major technical tags
        hot_tags = ["python", "react", "docker", "sql", "spark", "kubernetes", "mlops", "aws", "rust", "prefect"]
        for tag in hot_tags:
            feat[f"has_{tag}"] = 1.0 if tag in tokens else 0.0
            
        processed_records.append(feat)
        
    # Load features into a Polars DataFrame
    df = pl.DataFrame(processed_records)
    
    # Split features and target
    X_cols = [c for c in df.columns if c != "target"]
    X = df.select(X_cols).to_numpy()
    y = df.select("target").to_numpy().flatten()
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Hyperparameters
    params = {
        "n_estimators": 80,
        "max_depth": 5,
        "learning_rate": 0.08,
        "objective": "reg:squarederror",
        "random_state": 42
    }
    
    print(f"[ML Salary] Connecting to MLflow at {MLFLOW_TRACKING_URI}...")
    
    try:
        # Start MLflow run
        with mlflow.start_run() as run:
            # Log params
            mlflow.log_params(params)
            
            # Train XGBoost
            model = xgb.XGBRegressor(**params)
            model.fit(X_train, y_train)
            
            # Predict & Evaluate
            preds = model.predict(X_test)
            rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
            mae = float(mean_absolute_error(y_test, preds))
            
            # Log metrics
            mlflow.log_metric("RMSE", rmse)
            mlflow.log_metric("MAE", mae)
            
            # Log model
            mlflow.xgboost.log_model(
                model, 
                artifact_path="salary_model", 
                registered_model_name="XGBoost_Salary_Regressor"
            )
            
            print(f"[ML Salary Run Completed] MLflow Run ID: {run.info.run_id}")
            print(f" - RMSE: ${rmse:,.2f} | MAE: ${mae:,.2f}")
            
            # Save a local active copy for runtime API fallback serving
            local_model_path = Path(DATABASE_PATH).parent / "models"
            local_model_path.mkdir(parents=True, exist_ok=True)
            model.save_model(str(local_model_path / "salary_xgb.json"))
            
            return run.info.run_id
    except Exception as e:
        print(f"[MLflow Logging Failed] Running in standalone local mode: {e}")
        # Train locally anyway and save the model
        model = xgb.XGBRegressor(**params)
        model.fit(X_train, y_train)
        
        preds = model.predict(X_test)
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
        
        local_model_path = Path(DATABASE_PATH).parent / "models"
        local_model_path.mkdir(parents=True, exist_ok=True)
        model.save_model(str(local_model_path / "salary_xgb.json"))
        
        print(f"[ML Salary Standalone Completed] Saved model locally. RMSE: ${rmse:,.2f}")
        return "LOCAL_RUN"

def re_findall(pattern, string):
    """Offline simple digit extractor."""
    import re
    return re.findall(pattern, string)

if __name__ == "__main__":
    preprocess_and_train()
