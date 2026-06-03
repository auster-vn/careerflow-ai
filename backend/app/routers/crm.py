import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from app.database import get_db_connection

router = APIRouter(prefix="/api/crm", tags=["CRM"])

class ApplicationCreate(BaseModel):
    company_name: str
    job_title: str
    job_url: Optional[str] = ""
    job_description: Optional[str] = ""
    salary_range: Optional[str] = ""
    notes: Optional[str] = ""
    status: Optional[str] = "WISHLIST"

class ApplicationUpdateStatus(BaseModel):
    status: str

class ApplicationUpdate(BaseModel):
    company_name: str
    job_title: str
    job_url: Optional[str] = ""
    salary_range: Optional[str] = ""
    notes: Optional[str] = ""

def serialize_row(row):
    """Utility to map standard tuple into dict output."""
    return {
        "id": row[0],
        "company_name": row[1],
        "job_title": row[2],
        "job_url": row[3],
        "job_description": row[4],
        "status": row[5],
        "salary_range": row[6],
        "notes": row[7],
        "applied_date": row[8],
        "updated_date": row[9]
    }

@router.get("", response_model=List[dict])
def get_all_applications():
    """Fetch all job application cards sorted by update date."""
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM applications ORDER BY updated_date DESC").fetchall()
        return [serialize_row(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")
    finally:
        conn.close()

@router.get("/{app_id}", response_model=dict)
def get_application(app_id: str):
    """Retrieve detailed information for a single application."""
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", [app_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Application not found")
        return serialize_row(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        conn.close()

@router.post("", response_model=dict)
def create_application(app: ApplicationCreate):
    """Add a new job application card to the CRM database."""
    app_id = str(uuid.uuid4())
    now_str = datetime.now().isoformat()
    
    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO applications (id, company_name, job_title, job_url, job_description, status, salary_range, notes, applied_date, updated_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                app_id,
                app.company_name.strip(),
                app.job_title.strip(),
                app.job_url.strip() if app.job_url else "",
                app.job_description.strip() if app.job_description else "",
                app.status.upper().strip(),
                app.salary_range.strip() if app.salary_range else "",
                app.notes.strip() if app.notes else "",
                now_str,
                now_str
            ]
        )
        return {
            "id": app_id,
            "company_name": app.company_name,
            "job_title": app.job_title,
            "status": app.status,
            "created_at": now_str
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create card: {e}")
    finally:
        conn.close()

@router.put("/{app_id}/status", response_model=dict)
def update_application_status(app_id: str, status_payload: ApplicationUpdateStatus):
    """Update application stage (e.g., dragged to new column)."""
    now_str = datetime.now().isoformat()
    status_upper = status_payload.status.upper().strip()
    
    conn = get_db_connection()
    try:
        # Check if card exists
        exists = conn.execute("SELECT 1 FROM applications WHERE id = ?", [app_id]).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Application card not found")
            
        conn.execute(
            "UPDATE applications SET status = ?, updated_date = ? WHERE id = ?",
            [status_upper, now_str, app_id]
        )
        return {"id": app_id, "status": status_upper, "updated_at": now_str}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    finally:
        conn.close()

@router.put("/{app_id}", response_model=dict)
def update_application_details(app_id: str, app: ApplicationUpdate):
    """Edit core card properties (company, title, salary, notes)."""
    now_str = datetime.now().isoformat()
    
    conn = get_db_connection()
    try:
        # Check if card exists
        exists = conn.execute("SELECT 1 FROM applications WHERE id = ?", [app_id]).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Application card not found")
            
        conn.execute(
            """
            UPDATE applications 
            SET company_name = ?, job_title = ?, job_url = ?, salary_range = ?, notes = ?, updated_date = ? 
            WHERE id = ?
            """,
            [
                app.company_name.strip(),
                app.job_title.strip(),
                app.job_url.strip() if app.job_url else "",
                app.salary_range.strip() if app.salary_range else "",
                app.notes.strip() if app.notes else "",
                now_str,
                app_id
            ]
        )
        return {"id": app_id, "updated_at": now_str}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    finally:
        conn.close()

@router.delete("/clear-all")
def delete_all_applications():
    """Wipe all application cards, interviews, and MinIO S3 Bronze/Silver storage files."""
    # 1. Clear MinIO S3 objects
    try:
        from app.pipeline.etl_lakehouse import get_s3_client, S3_BRONZE_BUCKET, S3_SILVER_BUCKET
        s3 = get_s3_client()
        for bucket in [S3_BRONZE_BUCKET, S3_SILVER_BUCKET]:
            resp = s3.list_objects_v2(Bucket=bucket)
            if "Contents" in resp:
                for obj in resp["Contents"]:
                    s3.delete_object(Bucket=bucket, Key=obj["Key"])
                print(f"[Lakehouse Clear] Cleared bucket '{bucket}' objects.")
    except Exception as s3_err:
        print(f"[Lakehouse Clear Warning] Failed to wipe S3 objects: {s3_err}")

    # 2. Clear DuckDB records
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM interview_logs")
        conn.execute("DELETE FROM interviews")
        conn.execute("DELETE FROM applications")
        return {"message": "Successfully cleared all applications, transcripts, and S3 lake files."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database wipe failed: {e}")
    finally:
        conn.close()

@router.delete("/{app_id}")
def delete_application(app_id: str):
    """Delete a job application from the database."""
    conn = get_db_connection()
    try:
        # Check if exists
        exists = conn.execute("SELECT 1 FROM applications WHERE id = ?", [app_id]).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Application card not found")
            
        conn.execute("DELETE FROM applications WHERE id = ?", [app_id])
        return {"message": f"Successfully deleted application {app_id}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deletion failed: {e}")
    finally:
        conn.close()
