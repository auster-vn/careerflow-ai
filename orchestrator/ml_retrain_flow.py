import sys
from pathlib import Path
from prefect import task, flow

# Ensure backend libraries are visible to the Prefect runtime
sys.path.append(str(Path(__file__).resolve().parent.parent / "backend"))

from ml.train_salary import preprocess_and_train
from ml.train_success import train_success_classifier

@task(name="XGBoost Salary Training Loop")
def retrain_salary_task():
    """Prefect task: Clean job warehouse parquets, train and log XGBoost Regressor."""
    print("[Prefect ML Task] Starting Salary Prediction training loop...")
    run_id = preprocess_and_train()
    return f"Salary Run ID: {run_id}"

@task(name="XGBoost Success Training Loop")
def retrain_success_task():
    """Prefect task: Ingest interview metrics, train and register XGBoost Classifier."""
    print("[Prefect ML Task] Starting Success Probability training loop...")
    run_id = train_success_classifier()
    return f"Success Run ID: {run_id}"

@flow(name="CareerFlow AI Models Retrain Flow")
def careerflow_ml_retrain_flow():
    """
    Complete Prefect Flow managing the MLOps lifecycle:
    Sequentially trains the Salary Predictor and Success Forecaster, registering them in MLflow.
    """
    print("[Prefect Flow] Starting MLOps Retrain Pipeline Flow...")
    res_salary = retrain_salary_task()
    res_success = retrain_success_task()
    print("[Prefect Flow] MLOps Retrain Pipeline completed successfully!")
    return {
        "salary_status": res_salary,
        "success_status": res_success
    }

if __name__ == "__main__":
    careerflow_ml_retrain_flow()
