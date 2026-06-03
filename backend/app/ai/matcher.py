import lancedb
import numpy as np
import polars as pl
import re
import uuid
from typing import Dict, List, Tuple, Set
from app.config import LANCEDB_URI
from app.pipeline.parser import clean_and_tokenize, TECHNICAL_DICTIONARY

# Embedding model lazy initialization to save memory
_model = None

def get_embedding_model():
    """Lazily load the SentenceTransformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            print("[Embedding] Initializing all-MiniLM-L6-v2 model locally...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as e:
            print(f"[Embedding Warning] Sentence-Transformers failed to load: {e}. Fallback to token-matching mode.")
            _model = "FALLBACK"
    return _model

def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate vector embeddings for a list of texts."""
    model = get_embedding_model()
    if model == "FALLBACK" or model is None:
        return []
    try:
        embeddings = model.encode(texts)
        return embeddings.tolist()
    except Exception as e:
        print(f"[Embedding Error] Encoding failed: {e}")
        return []

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculate the cosine similarity between two vectors."""
    a = np.array(v1)
    b = np.array(v2)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))

def _clean_vietnamese_accents(text: str) -> str:
    """Removes Vietnamese diacritics/accents from a string."""
    patterns = {
        '[àáảãạăằắẳẵặâầấẩẫậ]': 'a',
        '[èéẻẽẹêềếểễệ]': 'e',
        '[ìíỉĩị]': 'i',
        '[òóỏõọôồốổỗộơờớởỡợ]': 'o',
        '[ùúủũụưừứửữự]': 'u',
        '[ỳýỷỹỵ]': 'y',
        '[đ]': 'd',
        '[ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ]': 'A',
        '[ÈÉẺẼẸÊỀẾỂỄỆ]': 'E',
        '[ÌÍỈĨỊ]': 'I',
        '[ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢ]': 'O',
        '[ÙÚỦŨỤƯỪỨỬỮỰ]': 'U',
        '[ỲÝỶỸỴ]': 'Y',
        '[Đ]': 'D'
    }
    for pattern, repl in patterns.items():
        text = re.sub(pattern, repl, text)
    return text

# Synonyms dictionary to normalize technical keywords for precise alignment checks
SYNONYM_MAP = {
    "reactjs": "react",
    "react.js": "react",
    "nextjs": "nextjs",
    "next.js": "nextjs",
    "typescript": "typescript",
    "ts": "typescript",
    "javascript": "javascript",
    "js": "javascript",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "cicd": "ci/cd",
    "c-sharp": "c#",
    "csharp": "c#",
    "dotnet": "dotnet",
    ".net": "dotnet",
    "node.js": "node",
    "nodejs": "node",
    "fastapi": "fastapi",
    "fast-api": "fastapi",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "mongodb": "mongodb",
    "mongo": "mongodb",
}

def normalize_tokens(tokens: List[str]) -> Set[str]:
    """Map synonym tokens to a unified form for matching consistency."""
    normalized = set()
    for t in tokens:
        t_clean = t.lower().strip()
        if t_clean in SYNONYM_MAP:
            normalized.add(SYNONYM_MAP[t_clean])
        else:
            normalized.add(t_clean)
    return normalized

def chunk_text(text: str, chunk_size: int = 4, overlap: int = 1) -> List[str]:
    """
    Chunks text by grouping consecutive lines together to preserve semantic context.
    Ensures LanceDB search can query localized chunks rather than the entire document.
    """
    lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 8]
    if not lines:
        return [text]
    
    chunks = []
    i = 0
    while i < len(lines):
        chunk = " ".join(lines[i : i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
        if i >= len(lines) - overlap:
            break
    return chunks

def extract_jd_requirements(jd_text: str) -> List[str]:
    """
    Extracts distinct job requirement statements from the Job Description text.
    First parses bullets, falls back to sentence splitting, and filters out boilerplate.
    """
    lines = []
    # Try parsing by bullets
    for line in jd_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Check standard bullet markers
        match = re.match(r"^([\-\*•\+]\s*|\d+[\.\)\s]+\s*)(.+)$", line)
        if match:
            lines.append(match.group(2).strip())
        elif len(line) > 30:
            lines.append(line)

    noise_keywords = [
        "about us", "equal opportunity", "we are", "apply", "recruit", "email", 
        "contact", "website", "join our", "our mission", "benefits", "salary", 
        "welfare", "chúng tôi", "yêu cầu", "mô tả", "quyền lợi", "nộp", "liên hệ",
        "hr", "hiring", "apply now"
    ]
    
    clean_reqs = []
    for line in lines:
        line_lower = line.lower()
        # Skip lines that look like boilerplate unless they name tech skills
        if any(kw in line_lower for kw in noise_keywords) and not any(tech in line_lower for tech in TECHNICAL_DICTIONARY):
            continue
        if len(line) > 15:
            clean_reqs.append(line)
            
    # Fallback to standard sentences if no clean lines were extracted
    if not clean_reqs:
        sentences = re.split(r"\.\s+", jd_text)
        for s in sentences:
            s = s.strip()
            if len(s) > 25 and not any(kw in s.lower() for kw in noise_keywords):
                clean_reqs.append(s)
                
    return clean_reqs[:15]

def scale_similarity(sim: float) -> float:
    """
    Scales cosine similarity into a realistic recruiter score [0.0, 1.0].
    Cosine similarity below 0.38 represents no fit, and above 0.76 is a full fit.
    """
    low = 0.38
    high = 0.76
    if sim <= low:
        return 0.0
    if sim >= high:
        return 1.0
    return (sim - low) / (high - low)

def detect_language(text: str) -> str:
    """Detect if the text is primarily Vietnamese or English."""
    vietnamese_keywords = [
        "kinh nghiệm", "học vấn", "dự án", "kỹ năng", "tóm tắt", 
        "mục tiêu", "liên hệ", "giới thiệu", "ngôn ngữ", "chứng chỉ",
        "lập trình viên", "phát triển", "hệ thống", "thành viên", "công nghệ"
    ]
    text_lower = text.lower()
    vi_count = 0
    for kw in vietnamese_keywords:
        if kw in text_lower:
            vi_count += 1
    # If we find 2 or more distinct Vietnamese keywords, assume Vietnamese
    return "vi" if vi_count >= 2 else "en"

def check_technology_casing(resume_text: str, lang: str) -> List[str]:
    """Check standard technical term capitalization."""
    recs = []
    
    # A selected dictionary of common tech terms and their standard casings
    TECH_CASING_MAP = {
        "python": "Python",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "golang": "Go",
        "java": "Java",
        "scala": "Scala",
        "rust": "Rust",
        "react": "React",
        "angular": "Angular",
        "vue": "Vue",
        "nextjs": "Next.js",
        "node": "Node.js",
        "express": "Express.js",
        "fastapi": "FastAPI",
        "django": "Django",
        "flask": "Flask",
        "sql": "SQL",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "sqlite": "SQLite",
        "duckdb": "DuckDB",
        "clickhouse": "ClickHouse",
        "mongodb": "MongoDB",
        "redis": "Redis",
        "lancedb": "LanceDB",
        "qdrant": "Qdrant",
        "pinecone": "Pinecone",
        "chromadb": "ChromaDB",
        "spark": "Apache Spark",
        "pyspark": "PySpark",
        "kafka": "Apache Kafka",
        "rabbitmq": "RabbitMQ",
        "airflow": "Apache Airflow",
        "dbt": "dbt",
        "databricks": "Databricks",
        "snowflake": "Snowflake",
        "bigquery": "BigQuery",
        "aws": "AWS",
        "gcp": "GCP",
        "kubernetes": "Kubernetes",
        "docker": "Docker",
        "terraform": "Terraform",
        "ansible": "Ansible",
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "pandas": "Pandas",
        "numpy": "NumPy",
        "polars": "Polars",
        "langchain": "LangChain",
        "llamaindex": "LlamaIndex",
        "agentops": "AgentOps",
        "mlflow": "MLflow",
        "git": "Git",
        "linux": "Linux",
        "graphql": "GraphQL"
    }
    
    wrong_casings = []
    for tech_lower, correct_casing in TECH_CASING_MAP.items():
        # Find occurrences using word boundaries to avoid matching partial words
        pattern = rf"\b{re.escape(tech_lower)}\b"
        matches = re.findall(pattern, resume_text, re.IGNORECASE)
        if matches:
            # Count how many matches do NOT have the correct casing
            incorrect_matches = [m for m in matches if m != correct_casing]
            if len(incorrect_matches) == len(matches):  # all matches of this tech are incorrect
                wrong_casings.append((incorrect_matches[0], correct_casing))
                
    if wrong_casings:
        # limit to top 3 to avoid cluttering recommendations
        examples = wrong_casings[:3]
        ex_str_wrong = ", ".join(f"'{w}'" for w, c in examples)
        ex_str_correct = ", ".join(f"'{c}'" for w, c in examples)
        if lang == "vi":
            recs.append(f"Nhất quán danh từ: Đồng nhất cách viết hoa của các công nghệ: viết là {ex_str_correct} thay vì {ex_str_wrong}.")
        else:
            recs.append(f"Casing Consistency: Standardize technology spelling/capitalization: use {ex_str_correct} instead of {ex_str_wrong}.")
    return recs

def check_passive_phrases(resume_text: str, lang: str) -> List[str]:
    """Check for passive or weak phrasing."""
    recs = []
    res_lower = resume_text.lower()
    
    en_weak_phrases = ["assisted in", "helped with", "responsible for", "participated in", "worked on"]
    vi_weak_phrases = ["chịu trách nhiệm", "hỗ trợ", "tham gia vào", "làm việc với", "phụ trách"]
    
    found_en = [p for p in en_weak_phrases if p in res_lower]
    found_vi = [p for p in vi_weak_phrases if p in res_lower]
    
    if lang == "vi" and found_vi:
        examples = ", ".join(f"'{p}'" for p in found_vi[:2])
        recs.append(f"Giọng văn chủ động: Tránh dùng các cụm từ thụ động/chung chung như {examples}. Hãy thay bằng các động từ thể hiện vai trò chủ chốt như 'Chủ trì', 'Thiết kế', 'Tối ưu hóa', 'Trực tiếp phát triển'.")
    elif lang == "en" and found_en:
        examples = ", ".join(f"'{p}'" for p in found_en[:2])
        recs.append(f"Active Voice: Avoid passive/weak phrasing like {examples}. Lead your bullet points with strong results-driven action verbs (e.g. 'Engineered', 'Orchestrated', 'Optimized').")
    return recs

def check_summary_section(resume_text: str, lang: str) -> List[str]:
    """Verify if a professional summary/profile section is included."""
    recs = []
    res_lower = resume_text.lower()
    summary_keywords = ["summary", "profile", "about me", "objective", "tóm tắt", "mục tiêu", "giới thiệu"]
    has_summary = any(k in res_lower for k in summary_keywords)
    if not has_summary:
        if lang == "vi":
            recs.append("Giới thiệu bản thân: Bổ sung một đoạn Tóm tắt chuyên môn (Professional Summary) ngắn từ 2-3 câu ở đầu CV để thu hút sự chú ý của nhà tuyển dụng.")
        else:
            recs.append("Summary Section: Add a 2-3 sentence Professional Summary/Profile at the top of your resume to capture the recruiter's interest.")
    return recs

def check_project_links(resume_text: str, lang: str) -> List[str]:
    """Verify if listed projects have clickable code repo or demo links."""
    recs = []
    res_lower = resume_text.lower()
    has_projects = any(k in res_lower for k in ["project", "dự án", "sản phẩm"])
    has_links = any(k in res_lower for k in ["http://", "https://", "github.com", "gitlab.com", "bitbucket.org"])
    if has_projects and not has_links:
        if lang == "vi":
            recs.append("Liên kết dự án: Bổ sung link demo hoặc link mã nguồn (GitHub) cho các dự án để nhà tuyển dụng có thể kiểm chứng trực quan.")
        else:
            recs.append("Project Links: Add active demo links or GitHub repository links for your listed projects to let recruiters verify your work.")
    return recs

def check_resume_quality_recs(resume_text: str, lang: str = None) -> List[str]:
    """
    Checks various resume writing best practices:
    - Quantifiable metrics (numbers, %, $, etc.)
    - Strong action verbs
    - Word count bounds
    - Clichés / generic buzzwords
    - Contact info visibility
    - Professional portfolio links
    - Technology casing / spelling standardization
    - Active vs passive phrasing
    - Missing crucial sections (Education, Experience, Projects, Skills)
    - Project links verification
    - Summary section presence
    """
    if lang is None:
        lang = detect_language(resume_text)
        
    recs = []
    res_lower = resume_text.lower()
    
    # 1. Language-based structural checks
    if "education" not in res_lower and "học vấn" not in res_lower:
        if lang == "vi":
            recs.append("Bố cục CV: Bổ sung mục 'Học Vấn' hoặc 'Education' để giới thiệu nền tảng đào tạo của bạn.")
        else:
            recs.append("Resume Formatting: Add an 'Education' or 'Học Vấn' section to highlight your academic background.")
            
    if "experience" not in res_lower and "kinh nghiệm" not in res_lower:
        if lang == "vi":
            recs.append("Bố cục CV: Bổ sung mục 'Kinh Nghiệm Làm Việc' hoặc 'Work Experience' rõ ràng kèm thời gian cụ thể.")
        else:
            recs.append("Resume Formatting: Structure a clear 'Work Experience' or 'Kinh Nghiệm' section with concrete dates and bullet points.")
            
    if "project" not in res_lower and "dự án" not in res_lower:
        if lang == "vi":
            recs.append("Bố cục CV: Bổ sung mục 'Dự Án' hoặc 'Projects' để làm nổi bật các sản phẩm thực tế bạn đã xây dựng.")
        else:
            recs.append("Resume Formatting: Highlight a 'Projects' or 'Dự Án' section to showcase your hands-on coding achievements.")
            
    if "skill" not in res_lower and "kỹ năng" not in res_lower:
        if lang == "vi":
            recs.append("Bố cục CV: Thêm mục 'Kỹ Năng' hoặc 'Skills' để liệt kê rõ ràng các công cụ và ngôn ngữ lập trình.")
        else:
            recs.append("Resume Formatting: Add a dedicated 'Skills' or 'Kỹ Năng' section to help ATS parse your technical profile.")

    # 2. Summary/Profile Verification
    recs.extend(check_summary_section(resume_text, lang))

    # 3. Project Links Verification
    recs.extend(check_project_links(resume_text, lang))

    # 4. Quantifiable metrics check
    metrics_matches = re.findall(r'\b(\d+%\s*|\$\s*\d+|\d+\s*\+|\d+\s*x|\d+\s*percent)\b', res_lower)
    if len(metrics_matches) < 2:
        if lang == "vi":
            recs.append("Đo lường kết quả: Thêm các số liệu đo lường được (ví dụ: tăng tốc độ tải trang 30%, giảm 20% chi phí server, mở rộng database) để minh chứng cho thành tựu.")
        else:
            recs.append("Quantifiable Impact: Add measurable metrics (e.g. performance speedups, cost reductions, database scaling numbers) to prove your achievements.")
            
    # 5. Action verbs check
    action_verbs = {
        "led", "developed", "implemented", "designed", "managed", "created", "built",
        "optimized", "increased", "reduced", "spearheaded", "accelerated",
        "established", "formulated", "engineered", "restructured", "achieved", "executed"
    }
    words = clean_and_tokenize(res_lower)
    action_words_found = [w for w in words if w in action_verbs]
    vi_action_verbs = ["chủ trì", "thiết kế", "xây dựng", "tối ưu", "phát triển", "triển khai", "quản lý", "nâng cấp", "cải tiến", "tích hợp"]
    vi_action_found = [v for v in vi_action_verbs if v in res_lower]
    
    if lang == "vi":
        if len(vi_action_found) < 3:
            recs.append("Động từ hành động: Bắt đầu các gạch đầu dòng kinh nghiệm bằng các động từ hành động mạnh mẽ (ví dụ: 'Tối ưu hóa', 'Thiết kế', 'Xây dựng', 'Chủ trì') thay vì các từ chung chung.")
    else:
        if len(action_words_found) < 3:
            recs.append("Action Verbs: Start your experience bullets with strong action verbs (e.g. 'Optimized', 'Engineered', 'Spearheaded') to sound more impact-oriented.")
            
    # 6. Resume Length
    word_count = len(words)
    if word_count > 1200:
        if lang == "vi":
            recs.append("Đo độ dài CV: CV của bạn quá dài (hơn 1200 từ). Hãy rút gọn xuống 1-2 trang và tập trung vào những thành tựu nổi bật nhất.")
        else:
            recs.append("Resume Length: Your resume is quite long (over 1200 words). Consider condensing it to 1-2 pages, focusing only on high-impact achievements.")
    elif word_count < 150:
        if lang == "vi":
            recs.append("Nội dung CV: CV của bạn quá ngắn (dưới 150 từ). Hãy mô tả chi tiết hơn về các dự án, trách nhiệm và công nghệ đã sử dụng.")
        else:
            recs.append("Resume Content: Your resume is very brief. Expand on your project details, responsibilities, and technologies used.")
            
    # 7. Overused Cliches/Buzzwords
    cliches = ["team player", "hard worker", "fast learner", "detail-oriented", "results-driven", "synergy", "think outside the box"]
    vi_cliches = ["chăm chỉ", "ham học hỏi", "hòa đồng", "năng động", "nhiệt huyết"]
    
    found_cliches = [c for c in cliches if c in res_lower]
    found_vi_cliches = [c for c in vi_cliches if c in res_lower]
    
    if lang == "vi" and found_vi_cliches:
        cliches_str = ", ".join(f"'{c}'" for c in found_vi_cliches[:3])
        recs.append(f"Tránh dùng sáo rỗng: Thay thế các từ sáo rỗng chung chung như {cliches_str} bằng các ví dụ thực tế thể hiện kỹ năng làm việc nhóm và giải quyết vấn đề của bạn.")
    elif lang == "en" and found_cliches:
        cliches_str = ", ".join(f"'{c}'" for c in found_cliches[:3])
        recs.append(f"Avoid Cliches: Replace generic buzzwords like {cliches_str} with direct examples of your collaboration and problem-solving skills.")
        
    # 8. Contact Information check
    has_email = re.search(r'\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b', res_lower)
    if not has_email:
        if lang == "vi":
            recs.append("Thông tin liên hệ: Đảm bảo địa chỉ email và số điện thoại được hiển thị rõ ràng ở đầu CV.")
        else:
            recs.append("Contact Info: Ensure your email address and phone number are clearly visible at the top of your resume.")
            
    # 9. Social/Github links
    if "github" not in res_lower and "linkedin" not in res_lower:
        if lang == "vi":
            recs.append("Liên kết chuyên nghiệp: Thêm link GitHub và LinkedIn để nhà tuyển dụng dễ dàng xem sản phẩm và hồ sơ của bạn.")
        else:
            recs.append("Professional Profile: Add links to your GitHub and LinkedIn profiles to make it easy for recruiters to see your portfolio.")
            
    # 10. Tech keyword capitalization
    recs.extend(check_technology_casing(resume_text, lang))

    # 11. Passive voice detection
    recs.extend(check_passive_phrases(resume_text, lang))

    return recs

def calculate_token_fallback(resume_text: str, jd_text: str) -> Dict:
    """
    Token-based fallback matching if SentenceTransformers model is unavailable.
    Uses synonym-normalized Jaccard overlap and exact keyword check.
    """
    # Clean accents
    r_unaccent = _clean_vietnamese_accents(resume_text)
    jd_unaccent = _clean_vietnamese_accents(jd_text)

    resume_tokens = normalize_tokens(clean_and_tokenize(r_unaccent))
    jd_tokens = normalize_tokens(clean_and_tokenize(jd_unaccent))
    
    lang = detect_language(resume_text)
    
    if not jd_tokens:
        no_kw_msg = "Không có từ khóa mô tả công việc để đối chiếu." if lang == "vi" else "No job description keywords provided to assess."
        return {
            "fit_score": 0.0,
            "matching_skills": [],
            "missing_skills": [],
            "recommendations": [no_kw_msg]
        }
        
    # Technical keyword check
    matching_tech = list(resume_tokens.intersection(jd_tokens).intersection(TECHNICAL_DICTIONARY))
    missing_tech = list(jd_tokens.difference(resume_tokens).intersection(TECHNICAL_DICTIONARY))
    
    # Sort lists to be deterministic
    matching_tech.sort()
    missing_tech.sort()

    # Jaccard overlap
    all_intersection = len(resume_tokens.intersection(jd_tokens))
    all_union = len(resume_tokens.union(jd_tokens))
    jaccard = (all_intersection / all_union) if all_union > 0 else 0.0
    
    # Technical match ratio
    tech_match_ratio = 1.0
    if len(matching_tech) + len(missing_tech) > 0:
        tech_match_ratio = len(matching_tech) / (len(matching_tech) + len(missing_tech))
        
    # Fit score: 70% technical keyword check, 30% overall overlap
    composite_fit = (tech_match_ratio * 0.7) + (jaccard * 0.3)
    fit_score = min(round(composite_fit * 100, 1), 100.0)
    
    recommendations = []
    if missing_tech:
        skills_str = ", ".join(missing_tech[:5])
        if lang == "vi":
            recommendations.append(f"Khoảng cách ATS: Thiếu các từ khóa kỹ thuật: {skills_str}. Hãy bổ sung chúng vào CV của bạn.")
        else:
            recommendations.append(f"ATS Gap: Missing technical keywords: {skills_str}. Consider adding experience with them to your resume.")
        
    # Add resume quality checks
    quality_recs = check_resume_quality_recs(resume_text, lang)
    recommendations.extend(quality_recs)
        
    if not recommendations:
        ok_msg = "Độ tương thích từ khóa tuyệt vời! Sẵn sàng ứng tuyển." if lang == "vi" else "Excellent keyword alignment! Ready to apply."
        recommendations.append(ok_msg)
        
    return {
        "fit_score": fit_score,
        "matching_skills": matching_tech,
        "missing_skills": missing_tech,
        "recommendations": recommendations
    }

def analyze_resume_fit(resume_text: str, jd_text: str) -> Dict:
    """
    Advanced ATS Matching engine:
    1. Extracts real JD expectations (excluding boilerplate).
    2. Overlap-chunks resume for optimal localized retrieval.
    3. Runs semantic vector matching in LanceDB.
    4. Normalizes cosine similarities to a realistic recruiter scale.
    5. Checks synonym-mapped tech checklist.
    6. Identifies specific weak-matching requirements to provide actionable tips.
    """
    model = get_embedding_model()
    
    # Fallback if embeddings are disabled/failed
    if model == "FALLBACK" or model is None:
        return calculate_token_fallback(resume_text, jd_text)
        
    try:
        db = lancedb.connect(LANCEDB_URI)
        
        # 1. Chunk resume
        resume_chunks = chunk_text(resume_text)
        
        # 2. Get embeddings
        resume_embeddings = get_embeddings(resume_chunks)
        if not resume_embeddings:
            return calculate_token_fallback(resume_text, jd_text)
            
        # Write to LanceDB
        data = [
            {"id": str(i), "vector": resume_embeddings[i], "text": resume_chunks[i]}
            for i in range(len(resume_chunks))
        ]
        
        if "resume_active" in db.table_names():
            db.drop_table("resume_active")
            
        table = db.create_table("resume_active", data=data)
        
        # 3. Extract JD requirements
        jd_lines = extract_jd_requirements(jd_text)
        if not jd_lines:
            return calculate_token_fallback(resume_text, jd_text)
            
        jd_embeddings = get_embeddings(jd_lines)
        if not jd_embeddings:
            return calculate_token_fallback(resume_text, jd_text)
            
        # 4. Perform semantic searches
        similarities = []
        low_match_reqs = []
        
        for jd_line, jd_vec in zip(jd_lines, jd_embeddings):
            results = table.search(jd_vec).limit(1).to_list()
            if results:
                best_match_vector = results[0]["vector"]
                sim = cosine_similarity(jd_vec, best_match_vector)
                similarities.append(sim)
                # Cosine similarity under 0.53 suggests weak semantic overlap
                if sim < 0.53:
                    low_match_reqs.append(jd_line)
                    
        # Calculate scaled semantic score
        scaled_similarities = [scale_similarity(s) for s in similarities]
        semantic_avg = np.mean(scaled_similarities) if scaled_similarities else 0.0
        
        # 5. Extract keyword fallback details (with synonym checks)
        fallback_data = calculate_token_fallback(resume_text, jd_text)
        
        # Composite score: 65% semantic fit, 35% exact technical keyword match
        final_score = (semantic_avg * 65.0) + (fallback_data["fit_score"] * 0.35)
        fit_score = min(round(final_score, 1), 100.0)
        
        # 6. Build highly customized actionable recommendations
        recommendations = []
        lang = detect_language(resume_text)
        
        # Highlighting missing skills
        if fallback_data["missing_skills"]:
            skills_str = ", ".join(fallback_data["missing_skills"][:5])
            if lang == "vi":
                recommendations.append(f"Khoảng cách ATS: Thiếu các từ khóa kỹ thuật: {skills_str}. Hãy bổ sung chúng vào mô tả dự án hoặc phần kỹ năng.")
            else:
                recommendations.append(f"ATS Gap: Missing technical keywords: {skills_str}. Try integrating them naturally.")
            
        # Highlight top 2 low-match semantic requirements
        for req in low_match_reqs[:2]:
            # Clean requirement text if too long
            req_short = req[:65] + "..." if len(req) > 65 else req
            if lang == "vi":
                recommendations.append(
                    f"Độ tương thích ngữ nghĩa yếu với yêu cầu: \"{req_short}\". "
                    "Hãy mô tả chi tiết hơn về các dự án hoặc công việc liên quan đến yêu cầu này."
                )
            else:
                recommendations.append(
                    f"Weak semantic match with requirement: \"{req_short}\". "
                    "Describe relevant projects or tasks in your resume addressing this."
                )
            
        # Add resume quality checks
        quality_recs = check_resume_quality_recs(resume_text, lang)
        recommendations.extend(quality_recs)
            
        if not recommendations:
            ok_msg = "Sự tương thích ngữ nghĩa và từ khóa tuyệt vời! Sẵn sàng ứng tuyển." if lang == "vi" else "Excellent semantic alignment and technical checklist matches! Ready to apply."
            recommendations.append(ok_msg)
    except Exception as e:
        print(f"[Matcher Error] LanceDB semantic matching failed: {e}. Defaulting to token parser.")
        return calculate_token_fallback(resume_text, jd_text)

if __name__ == "__main__":
    r_txt = "Senior Python developer with experience in Docker, PyTorch, LangChain, and DuckDB."
    j_txt = "Looking for a Python software engineer. Knowledge of SQL databases (DuckDB/PostgreSQL) and containerization with Docker is required. Familiarity with Kubernetes is a plus."
    res = analyze_resume_fit(r_txt, j_txt)
    print("Match Results:")
    print(f" - Fit Score: {res['fit_score']}%")
    print(f" - Matching Skills: {res['matching_skills']}")
    print(f" - Missing Skills: {res['missing_skills']}")
    print(f" - Recs: {res['recommendations']}")
