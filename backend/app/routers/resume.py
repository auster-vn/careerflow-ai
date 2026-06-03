import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File
from app.database import get_db_connection
from app.pipeline.parser import extract_text_from_pdf
from app.ai.matcher import analyze_resume_fit

router = APIRouter(prefix="/api/resume", tags=["Resume"])

@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Upload and parse a new resume PDF. Sets it as the active resume."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")
        
    try:
        pdf_bytes = await file.read()
        parsed_text = extract_text_from_pdf(pdf_bytes)
        
        if not parsed_text:
            raise HTTPException(status_code=422, detail="Unable to extract text from PDF.")
            
        resume_id = str(uuid.uuid4())
        now_str = datetime.now().isoformat()
        
        conn = get_db_connection()
        try:
            # Mark all existing resumes as inactive
            conn.execute("UPDATE resumes SET is_active = FALSE")
            
            # Insert the new active resume
            conn.execute(
                """
                INSERT INTO resumes (id, file_name, parsed_text, is_active, created_date)
                VALUES (?, ?, ?, TRUE, ?)
                """,
                [resume_id, file.filename, parsed_text, now_str]
            )
            return {
                "id": resume_id,
                "file_name": file.filename,
                "length": len(parsed_text),
                "message": "Resume uploaded and activated successfully."
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database write failed: {e}")
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File reading failed: {e}")

@router.get("/active")
def get_active_resume():
    """Retrieve the currently active resume text and details."""
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT id, file_name, created_date, parsed_text FROM resumes WHERE is_active = TRUE").fetchone()
        if not row:
            return {"active": False, "message": "No active resume found. Please upload one."}
        return {
            "active": True,
            "id": row[0],
            "file_name": row[1],
            "created_date": row[2],
            "parsed_text": row[3]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        conn.close()

@router.post("/analyze/{app_id}")
def analyze_application_fit(app_id: str):
    """Analyze the active resume's compatibility against a job description in the CRM."""
    conn = get_db_connection()
    try:
        # 1. Fetch active resume
        resume_row = conn.execute("SELECT parsed_text FROM resumes WHERE is_active = TRUE").fetchone()
        if not resume_row:
            raise HTTPException(status_code=404, detail="Please upload a resume first to run analysis.")
        resume_text = resume_row[0]
        
        # 2. Fetch target job description
        jd_row = conn.execute("SELECT job_description, company_name, job_title FROM applications WHERE id = ?", [app_id]).fetchone()
        if not jd_row:
            raise HTTPException(status_code=404, detail="Target job application not found.")
        jd_text, company, title = jd_row
        
        if not jd_text or len(jd_text.strip()) < 20:
            raise HTTPException(status_code=422, detail="Job description is too brief. Please edit the job card and paste the full description.")
            
        # 3. Perform semantic and keyword match analysis
        match_data = analyze_resume_fit(resume_text, jd_text)
        
        return {
            "application_id": app_id,
            "company_name": company,
            "job_title": title,
            "fit_score": match_data["fit_score"],
            "matching_skills": match_data["matching_skills"],
            "missing_skills": match_data["missing_skills"],
            "recommendations": match_data["recommendations"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ATS Analysis failed: {e}")
    finally:
        conn.close()
