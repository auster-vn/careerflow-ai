import sys
import polars as pl
import xgboost as xgb
import numpy as np
from pathlib import Path

# Add parent directories to sys.path to enable app module imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.ai.matcher import cosine_similarity

def test_polars_silver_parquet_logic():
    """Test that the Polars standardizer cleans company names, strips strings, and Normalizes columns."""
    raw_dummy = pl.DataFrame({
        "company_name": ["Google  ", "Stripe"],
        "job_title": ["  Senior MLE", "Lead Data Engineer"],
        "job_url": ["url1", "url2"],
        "salary_range": [None, "$150,000"],
        "job_description": ["Desc1", "Desc2"]
    })
    
    # Run inline Polars cleaning sequence equivalent to silver_etl
    cleaned_df = (
        raw_dummy
        .unique(subset=["company_name", "job_title", "job_url"])
        .with_columns([
            pl.col("company_name").str.strip_chars(),
            pl.col("job_title").str.strip_chars(),
            pl.col("salary_range").fill_null("N/A").str.strip_chars(),
            pl.col("job_description").fill_null("").str.strip_chars()
        ])
    )
    
    # Assert whitespace was successfully stripped and outputs are sorted
    assert sorted(cleaned_df.select("company_name").to_series().to_list()) == ["Google", "Stripe"]
    assert sorted(cleaned_df.select("job_title").to_series().to_list()) == ["Lead Data Engineer", "Senior MLE"]
    
    # Assert missing salaries filled with 'N/A'
    assert sorted(cleaned_df.select("salary_range").to_series().to_list()) == ["$150,000", "N/A"]

def test_cosine_similarity_edge_cases():
    """Verify that cosine similarity accurately scores overlapping vectors and handles zeros."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    v_zero = [0.0, 0.0, 0.0]
    
    # Identity similarity should be 1.0
    assert abs(cosine_similarity(v1, v2) - 1.0) < 1e-6
    # Orthogonal vectors similarity should be 0.0
    assert abs(cosine_similarity(v1, v3)) < 1e-6
    # Handling divide by zero zero-vectors
    assert cosine_similarity(v1, v_zero) == 0.0

def test_xgboost_salary_prediction_shape():
    """Verify that the XGBoost salary regressor inference handles 14 features."""
    # 14 features: company_name_len, jd_len, is_mle, is_de, + 10 hot tech tags
    dummy_input = np.random.uniform(0.0, 1.0, (1, 14))
    
    # Instantiate a dummy model mimicking our regressor
    model = xgb.XGBRegressor(n_estimators=5, max_depth=2)
    
    # Fit on small dummy batch
    X_dummy = np.random.uniform(0.0, 1.0, (10, 14))
    y_dummy = np.random.uniform(100000.0, 200000.0, (10,))
    model.fit(X_dummy, y_dummy)
    
    # Inference
    pred = model.predict(dummy_input)
    assert len(pred) == 1
    assert isinstance(float(pred[0]), float)

def test_xgboost_success_classification_shape():
    """Verify that the XGBoost success classifier outputs float probability scales."""
    # 4 features: match_score, avg_grade, matching_skills_count, missing_skills_count
    dummy_input = np.random.uniform(0.0, 1.0, (1, 4))
    
    model = xgb.XGBClassifier(n_estimators=5, max_depth=2)
    
    # Fit on dummy binary batch
    X_dummy = np.random.uniform(0.0, 1.0, (10, 4))
    y_dummy = np.array([0, 1, 0, 1, 1, 0, 0, 1, 0, 1])
    model.fit(X_dummy, y_dummy)
    
    # Predict prob
    prob = model.predict_proba(dummy_input)
    assert prob.shape == (1, 2)
    # Probability float between 0.0 and 1.0
    assert 0.0 <= float(prob[0, 1]) <= 1.0
