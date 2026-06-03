import httpx
import json
import random
from typing import Dict, List
from app import config
from app.pipeline.parser import clean_and_tokenize, TECHNICAL_DICTIONARY

# Rich Offline Q&A Database for mock interview fallbacks
OFFLINE_QUESTIONS = {
    "technical": [
        "Can you explain the key differences between Polars and PySpark in terms of execution engines and memory management?",
        "How does DuckDB achieve high performance on analytical queries compared to row-based databases like standard PostgreSQL?",
        "When using a vector database like LanceDB, what are the trade-offs between Flat indexing and IVF-PQ indexing for similarity search?",
        "Explain how you would handle schema drift in an ETL data pipeline using Polars or dbt.",
        "How do you design a robust Dead Letter Queue (DLQ) in a real-time event streaming pipeline using Kafka or RabbitMQ?",
        "Can you walk me through your experience building RAG pipelines? How do you prevent hallucinations in LLM synthesizers?",
        "What is the difference between Jaccard similarity and Cosine similarity, and when would you use each in text parsing?",
        "Explain how asynchronous tasks work in FastAPI. What is the role of 'async def' versus standard 'def' in endpoints?",
        "How would you optimize a slow database query in PostgreSQL that joins multiple heavy fact tables?"
    ],
    "behavioral": [
        "Tell me about a time you had to optimize a pipeline that was running slow or crashing in production. What was your process?",
        "Describe a situation where you had a disagreement with a team member regarding system architecture. How did you resolve it?",
        "How do you keep up with rapid changes in AI and Data Engineering? Share an example of a tool you recently learned and applied.",
        "Tell me about a challenging technical bug you faced recently. How did you diagnose and solve it?"
    ]
}

def call_gemini_api(prompt: str, json_mode: bool = False) -> str:
    """Helper to call Gemini REST API directly using httpx."""
    if not config.GEMINI_API_KEY:
        raise ValueError("Missing GEMINI_API_KEY")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={config.GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    # Configure JSON schema/mode if requested to ensure strict parseable payloads
    config_dict = {}
    if json_mode:
        config_dict = {
            "responseMimeType": "application/json"
        }
        
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": config_dict
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                data = response.json()
                return data["contents"][0]["parts"][0]["text"]
            else:
                print(f"[Gemini Error] API call failed with code {response.status_code}: {response.text}")
                raise RuntimeError(f"API Error {response.status_code}")
    except Exception as e:
        print(f"[Gemini Error] HTTP request exception: {e}")
        raise e

def generate_next_question(company: str, role: str, jd: str, resume: str, history: List[Dict]) -> str:
    """
    Generates the next interview question.
    Connects to Gemini if API key is active; otherwise loads a highly contextual local mock question.
    """
    if not config.GEMINI_API_KEY:
        # Offline fallback logic
        asked_questions = {h["message"] for h in history if h["speaker"] == "AI"}
        # Select technical or behavioral depending on interview progress
        q_pool = OFFLINE_QUESTIONS["behavioral"] if len(asked_questions) >= 3 else OFFLINE_QUESTIONS["technical"]
        available_qs = [q for q in q_pool if q not in asked_questions]
        if not available_qs:
            available_qs = q_pool
            
        # Customize mock question with role details
        q = random.choice(available_qs)
        return f"[{company} - {role}] {q}"

    # Build Gemini prompt
    history_str = "\n".join([f"{h['speaker']}: {h['message']}" for h in history])
    prompt = f"""
    You are an elite Technical Hiring Manager interviewing a candidate for the role of '{role}' at '{company}'.
    
    JOB DESCRIPTION:
    {jd[:1000]}
    
    CANDIDATE RESUME:
    {resume[:1000]}
    
    INTERVIEW HISTORY SO FAR:
    {history_str}
    
    INSTRUCTIONS:
    - Act as the professional interviewer.
    - Generate the NEXT single interview question.
    - Focus heavily on technical skills listed in the job description or candidate's resume, especially modern DE/AI topics.
    - Do NOT include any prefixes, introductions, greetings, or meta-commentary. Just output the question.
    - Keep it concise (1 to 2 sentences max).
    """
    
    try:
        return call_gemini_api(prompt).strip()
    except Exception as e:
        print(f"[Coach Fallback] Defaulting to offline question generator: {e}")
        # Re-invoke fallback manually
        original_key = config.GEMINI_API_KEY
        config.GEMINI_API_KEY = ""
        res = generate_next_question(company, role, jd, resume, history)
        config.GEMINI_API_KEY = original_key
        return res

def evaluate_user_response(question: str, user_answer: str, role: str) -> Dict:
    """
    Grades the user's response (0-10), gives constructive feedback bullets, and provides a model answer.
    Connects to Gemini if active; otherwise compiles local heuristic grades.
    """
    if not config.GEMINI_API_KEY:
        # Offline mock evaluation helper
        tokens = set(clean_and_tokenize(user_answer))
        
        # Heuristic scoring based on answer length and technical term count
        score = 4
        if len(user_answer) > 80:
            score += 2
        if len(user_answer) > 200:
            score += 2
            
        # Match against tech dictionary
        matched_techs = tokens.intersection(TECHNICAL_DICTIONARY)
        if len(matched_techs) >= 2:
            score += 2
            
        score = min(score, 10)
        
        # Dynamic feedback bullets based on scores
        if score >= 8:
            feedback = [
                "Strong response containing key technical concepts and terminology.",
                "Provided solid structural overview of the concepts requested."
            ]
        elif score >= 5:
            feedback = [
                "Good start, but you could elaborate further with concrete project examples.",
                "Make sure to reference exact tools (like Polars, DuckDB, or FastAPI) to substantiate your experience."
            ]
        else:
            feedback = [
                "Your answer was a bit brief. Technical interviews require deep-dive explanations.",
                "Focus on explaining the underlying architecture and trade-offs rather than just definitions."
            ]
            
        return {
            "score": score,
            "feedback": "\n".join([f"- {f}" for f in feedback]),
            "model_answer": f"For a '{role}' position, a strong response would define the core concept, list active tools, explain performance implications (e.g. columnar vectorized scanning in DuckDB or zero-copy memory arrays in Polars), and share a brief runtime story from your past portfolio projects."
        }

    # Build Gemini structured prompt in JSON Mode
    prompt = f"""
    You are an expert Technical Hiring Coach grading a candidate's answer for a '{role}' role.
    
    QUESTION ASKED:
    {question}
    
    CANDIDATE ANSWER:
    {user_answer}
    
    INSTRUCTIONS:
    Evaluate the candidate's answer and respond strictly with a JSON object. The JSON MUST have these exact keys:
    1. "score": An integer between 0 and 10 representing the technical depth, correctness, and clarity of the answer.
    2. "feedback": A bulleted markdown list (2 bullets) containing constructive criticisms, what they did well, and what they missed.
    3. "model_answer": A 2-sentence highly professional 'ideal' response to the question.
    
    JSON Template format:
    {{
      "score": 8,
      "feedback": "- Good detail on X.\\n- You missed explaining Y.",
      "model_answer": "An ideal answer would..."
    }}
    """
    
    try:
        raw_json = call_gemini_api(prompt, json_mode=True)
        return json.loads(raw_json)
    except Exception as e:
        print(f"[Coach Fallback] Defaulting to local offline evaluator: {e}")
        original_key = config.GEMINI_API_KEY
        config.GEMINI_API_KEY = ""
        res = evaluate_user_response(question, user_answer, role)
        config.GEMINI_API_KEY = original_key
        return res

if __name__ == "__main__":
    # Test coach locally
    q = "What is the primary difference between DuckDB and traditional relational databases like SQLite?"
    ans = "DuckDB is columnar and OLAP focused which makes it super fast for analytical queries over columns, whereas SQLite is row-based and OLTP focused."
    
    eval_res = evaluate_user_response(q, ans, "Data Engineer")
    print(f"Offline Score: {eval_res['score']}/10")
    print(f"Feedback:\n{eval_res['feedback']}")
    print(f"Model Answer: {eval_res['model_answer']}")
