import sys
import duckdb
from pathlib import Path

# Add parent directories to sys.path to enable app module imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.pipeline.parser import extract_keywords_polars, clean_and_tokenize
from app.ai.matcher import analyze_resume_fit
from app.ai.coach import evaluate_user_response

def test_polars_keyword_extractor():
    """Verify that Polars extracts technical terms and counts them accurately."""
    sample_text = "I am a Python developer. I love coding in Python and PyTorch. MLOps is fun!"
    kws = extract_keywords_polars(sample_text, limit=5)
    
    assert len(kws) > 0
    # The most frequent word should be 'python' (appears twice)
    assert kws[0]["token"] == "python"
    assert kws[0]["count"] == 2
    assert kws[0]["is_tech"] is True
    
    # Assert stop-words like 'i', 'am', 'a', 'and' were successfully filtered out
    tokens = [k["token"] for k in kws]
    assert "i" not in tokens
    assert "am" not in tokens

def test_clean_and_tokenize():
    """Ensure token cleaning strips punctuation and normalizes characters."""
    sample = "FastAPI! Docker? Python; MLOps."
    tokens = clean_and_tokenize(sample)
    assert tokens == ["fastapi", "docker", "python", "mlops"]

def test_resume_matcher_jaccard_fallback():
    """Test that the resume matcher computes valid scores between 0 and 100."""
    resume = "Skills: Python, React, Docker, Postgres, SQL, MLOps."
    jd_perfect = "Looking for a Python developer experienced with React, Docker, Postgres, SQL, and MLOps."
    jd_poor = "Hiring a Java backend specialist with experience in Spring Boot, Kubernetes, and AWS cloud."
    
    res_perfect = analyze_resume_fit(resume, jd_perfect)
    res_poor = analyze_resume_fit(resume, jd_poor)
    
    assert 0 <= res_perfect["fit_score"] <= 100
    assert 0 <= res_poor["fit_score"] <= 100
    # Perfect match should have a significantly higher score than poor match
    assert res_perfect["fit_score"] > res_poor["fit_score"]
    assert "python" in res_perfect["matching_skills"]
    assert "java" in res_poor["missing_skills"]

def test_duckdb_schema_crud():
    """Ensure DuckDB connection runs query migrations and basic insertions."""
    # Use an in-memory database for clean unit testing
    conn = duckdb.connect(":memory:")
    try:
        # Create test table
        conn.execute("""
        CREATE TABLE applications (
            id VARCHAR PRIMARY KEY,
            company_name VARCHAR,
            job_title VARCHAR,
            status VARCHAR
        )
        """)
        
        # Insert record
        conn.execute("INSERT INTO applications VALUES ('123', 'Stripe', 'Staff DE', 'WISHLIST')")
        
        # Query record
        row = conn.execute("SELECT * FROM applications WHERE id = '123'").fetchone()
        assert row is not None
        assert row[1] == "Stripe"
        assert row[2] == "Staff DE"
        assert row[3] == "WISHLIST"
    finally:
        conn.close()

def test_ai_coach_evaluator():
    """Verify that the AI coach scores user answers contextually."""
    question = "Explain column-oriented database storage."
    good_answer = "Columnar storage stores data by column rather than row. This is highly efficient for OLAP queries because it enables vectorized scanning and compression, which is why tools like DuckDB and ClickHouse use it."
    bad_answer = "I don't know much about database storage, sorry."
    
    good_eval = evaluate_user_response(question, good_answer, "Data Engineer")
    bad_eval = evaluate_user_response(question, bad_answer, "Data Engineer")
    
    assert good_eval["score"] > bad_eval["score"]
    assert len(good_eval["feedback"]) > 0
    assert len(good_eval["model_answer"]) > 0

def test_scraper_endpoint(monkeypatch):
    """Verify that GET /api/analytics/scrape is functional."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routers import analytics
    
    monkeypatch.setattr(
        analytics, 
        "careerflow_lakehouse_flow", 
        lambda jobs: "Mocked Prefect Flow Completed"
    )
    
    client = TestClient(app)
    # Use a dummy keyword like 'AI' which is in our local pool or falls back beautifully
    response = client.get("/api/analytics/scrape?keyword=AI")
    
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert len(data["jobs"]) > 0
    # The scraped jobs should all have 'status' as 'WISHLIST'
    for job in data["jobs"]:
        assert job["status"] == "WISHLIST"
