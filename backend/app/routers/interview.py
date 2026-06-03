import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from app.database import get_db_connection
from app.ai.coach import generate_next_question, evaluate_user_response

router = APIRouter(prefix="/api/interview", tags=["Interview"])

class AnswerPayload(BaseModel):
    answer: str

def serialize_log(row):
    return {
        "id": row[0],
        "interview_id": row[1],
        "speaker": row[2],
        "message": row[3],
        "score": row[4],
        "feedback": row[5],
        "created_date": row[6]
    }

@router.post("/start/{app_id}")
def start_interview(app_id: str):
    """Start a new mock interview session based on the job card and active resume."""
    conn = get_db_connection()
    try:
        # 1. Fetch active resume
        resume_row = conn.execute("SELECT parsed_text FROM resumes WHERE is_active = TRUE").fetchone()
        if not resume_row:
            raise HTTPException(status_code=400, detail="Please upload a resume first before starting a mock interview.")
        resume_text = resume_row[0]
        
        # 2. Fetch job details
        jd_row = conn.execute("SELECT company_name, job_title, job_description FROM applications WHERE id = ?", [app_id]).fetchone()
        if not jd_row:
            raise HTTPException(status_code=404, detail="Target job card not found.")
        company, role, jd = jd_row
        
        # 3. Create a new interview session
        session_id = str(uuid.uuid4())
        now_str = datetime.now().isoformat()
        
        conn.execute(
            """
            INSERT INTO interviews (id, application_id, interviewer_name, interviewer_role, created_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            [session_id, app_id, "Gemini AI Interviewer", f"Lead {role} Recruiter", now_str]
        )
        
        # 4. Generate the INITIAL question
        initial_question = generate_next_question(company, role, jd, resume_text, [])
        
        # 5. Log the initial question into the logs
        log_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO interview_logs (id, interview_id, speaker, message, score, feedback, created_date)
            VALUES (?, ?, 'AI', ?, NULL, NULL, ?)
            """,
            [log_id, session_id, initial_question, now_str]
        )
        
        return {
            "session_id": session_id,
            "company_name": company,
            "job_title": role,
            "initial_question": initial_question,
            "message": "Interview session started successfully."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start interview: {e}")
    finally:
        conn.close()

@router.get("/history/{session_id}", response_model=List[dict])
def get_session_history(session_id: str):
    """Retrieve full chronological chat transcript logs for the session."""
    conn = get_db_connection()
    try:
        # Check if session exists
        exists = conn.execute("SELECT 1 FROM interviews WHERE id = ?", [session_id]).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Interview session not found.")
            
        rows = conn.execute(
            "SELECT * FROM interview_logs WHERE interview_id = ? ORDER BY created_date ASC",
            [session_id]
        ).fetchall()
        
        return [serialize_log(row) for row in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load history: {e}")
    finally:
        conn.close()

@router.post("/answer/{session_id}")
def submit_answer(session_id: str, payload: AnswerPayload):
    """Submit candidate response, grade it dynamically, and trigger the next question."""
    user_answer = payload.answer.strip()
    if not user_answer:
        raise HTTPException(status_code=400, detail="Answer content cannot be empty.")
        
    conn = get_db_connection()
    try:
        # 1. Fetch interview & job context
        sess_row = conn.execute(
            """
            SELECT i.application_id, a.company_name, a.job_title, a.job_description, r.parsed_text
            FROM interviews i
            JOIN applications a ON i.application_id = a.id
            JOIN resumes r ON r.is_active = TRUE
            WHERE i.id = ?
            """,
            [session_id]
        ).fetchone()
        
        if not sess_row:
            raise HTTPException(status_code=404, detail="Active interview context not found.")
            
        app_id, company, role, jd, resume_text = sess_row
        
        # 2. Get the last AI question asked
        last_ai_row = conn.execute(
            """
            SELECT message FROM interview_logs 
            WHERE interview_id = ? AND speaker = 'AI' 
            ORDER BY created_date DESC LIMIT 1
            """,
            [session_id]
        ).fetchone()
        
        if not last_ai_row:
            raise HTTPException(status_code=400, detail="No active question found to answer.")
            
        last_question = last_ai_row[0]
        
        # 3. Grade the user answer
        evaluation = evaluate_user_response(last_question, user_answer, role)
        
        # 4. Save user response + score/feedback to logs
        now_str = datetime.now().isoformat()
        user_log_id = str(uuid.uuid4())
        
        conn.execute(
            """
            INSERT INTO interview_logs (id, interview_id, speaker, message, score, feedback, created_date)
            VALUES (?, ?, 'USER', ?, ?, ?, ?)
            """,
            [
                user_log_id,
                session_id,
                user_answer,
                evaluation["score"],
                evaluation["feedback"],
                now_str
            ]
        )
        
        # 5. Fetch full history to decide if interview is complete (e.g. standard 4 questions completed)
        history_rows = conn.execute(
            "SELECT speaker, message FROM interview_logs WHERE interview_id = ? ORDER BY created_date ASC",
            [session_id]
        ).fetchall()
        
        history_list = [{"speaker": r[0], "message": r[1]} for r in history_rows]
        user_answer_count = sum(1 for h in history_list if h["speaker"] == "USER")
        
        is_complete = user_answer_count >= 4
        next_question = ""
        
        if not is_complete:
            # 6. Generate the next question
            next_question = generate_next_question(company, role, jd, resume_text, history_list)
            
            # Save new AI question to database logs
            ai_log_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO interview_logs (id, interview_id, speaker, message, score, feedback, created_date)
                VALUES (?, ?, 'AI', ?, NULL, NULL, ?)
                """,
                [ai_log_id, session_id, next_question, now_str]
            )
            
        return {
            "is_complete": is_complete,
            "evaluation": {
                "score": evaluation["score"],
                "feedback": evaluation["feedback"],
                "model_answer": evaluation["model_answer"]
            },
            "next_question": next_question,
            "message": "Response submitted and evaluated."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Answer submission failed: {e}")
    finally:
        conn.close()
