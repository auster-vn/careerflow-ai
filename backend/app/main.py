import sys
import uvicorn
from pathlib import Path
from contextlib import asynccontextmanager

# Dynamic python path bootstrapping to allow running from any directory
sys.path.append(str(Path(__file__).resolve().parent.parent))      # backend/ folder
sys.path.append(str(Path(__file__).resolve().parent.parent.parent)) # careerflow-ai/ root folder

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import HOST, PORT
from app.database import init_databases
from app.routers import crm, resume, interview, analytics

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan manager to bootstrap databases on application startup."""
    print("[CareerFlow API] Starting server and checking data lakehouse connections...")
    init_databases()
    yield
    print("[CareerFlow API] Shutting down and releasing resources.")

app = FastAPI(
    title="CareerFlow AI API",
    description="High-performance AI-powered Job Search CRM and Mock Interview Simulator.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register modular routers
app.include_router(crm.router)
app.include_router(resume.router)
app.include_router(interview.router)
app.include_router(analytics.router)

@app.get("/api/health")
def health_check():
    """Health check endpoint to ensure API service is online."""
    return {"status": "healthy", "service": "CareerFlow AI Backend"}

if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
