import re
import pdfplumber
import polars as pl
from io import BytesIO
from typing import List, Dict

# Standard English stop words + common resume noise to filter
STOP_WORDS = {
    "the", "and", "is", "of", "to", "in", "for", "a", "with", "on", "at", "by", "an",
    "be", "this", "that", "from", "as", "are", "it", "not", "but", "or", "as", "if",
    "your", "our", "their", "my", "me", "we", "us", "you", "he", "she", "they", "them",
    "will", "shall", "can", "could", "would", "should", "has", "have", "had", "having",
    "do", "does", "did", "doing", "about", "also", "with", "into", "through", "during",
    "under", "above", "such", "than", "then", "very", "too", "own", "other", "same"
}

# Known technical terms/skills we want to highlight in the keyword analysis
TECHNICAL_DICTIONARY = {
    "python", "javascript", "typescript", "golang", "java", "scala", "rust", "cpp", "c#",
    "react", "angular", "vue", "nextjs", "node", "express", "fastapi", "django", "flask",
    "sql", "postgresql", "mysql", "sqlite", "duckdb", "clickhouse", "mongodb", "redis",
    "lancedb", "qdrant", "pinecone", "chromadb", "pgvector", "milvus",
    "spark", "pyspark", "kafka", "redpanda", "rabbitmq", "flink", "beam",
    "airflow", "prefect", "dagster", "mage", "dbt", "databricks", "snowflake", "bigquery",
    "aws", "gcp", "azure", "kubernetes", "k8s", "docker", "terraform", "ansible", "ci/cd",
    "ml", "ai", "llm", "rag", "pytorch", "tensorflow", "scikit-learn", "xgboost", "pandas",
    "numpy", "polars", "embeddings", "transformers", "langchain", "llamaindex", "autogen",
    "agentops", "mlflow", "dvc", "git", "linux", "rest", "graphql", "grpc", "microservices"
}

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from resume PDF bytes using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"[Parser Error] Failed to extract text from PDF: {e}")
        # Return fallback text decode if pdfplumber fails
        try:
            text = pdf_bytes.decode("utf-8", errors="ignore")
        except:
            text = ""
    return text.strip()

def clean_and_tokenize(text: str) -> List[str]:
    """Clean text, remove punctuation, and return list of tokens."""
    # Replace newlines and non-alphanumeric chars (keep simple symbols like # and - or /)
    text_clean = re.sub(r"[^a-zA-Z0-9\s#\-\+/]", " ", text.lower())
    tokens = text_clean.split()
    return [t.strip() for t in tokens if t.strip()]

def extract_keywords_polars(text: str, limit: int = 25) -> List[Dict]:
    """
    Tải và tính toán độ quan trọng của từ khóa (Keywords) sử dụng thuật toán TF-IDF (Scikit-Learn).
    Falls back to Polars token calculations if sklearn is not loaded.
    """
    if not text:
        return []
        
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        tokens = clean_and_tokenize(text)
        cleaned_text = " ".join(tokens)
        
        # Khởi tạo mô hình học máy TF-IDF Vectorizer
        vectorizer = TfidfVectorizer(stop_words='english', token_pattern=r'(?u)\b[\w\-\+#/]+\b')
        tfidf_matrix = vectorizer.fit_transform([cleaned_text])
        feature_names = vectorizer.get_feature_names_out()
        scores = tfidf_matrix.toarray()[0]
        
        # Lọc các từ khóa có trong danh mục kỹ thuật hoặc có độ dài > 2
        kw_scores = []
        for word, score in zip(feature_names, scores):
            word_clean = word.strip()
            if word_clean not in STOP_WORDS and (word_clean in TECHNICAL_DICTIONARY or len(word_clean) > 2):
                # Count occurrences
                count = len(re.findall(r'\b' + re.escape(word_clean) + r'\b', text.lower()))
                kw_scores.append((word_clean, score, count))
                
        # Sắp xếp theo trọng số TF-IDF giảm dần
        kw_scores = sorted(kw_scores, key=lambda x: x[1], reverse=True)[:limit]
        if not kw_scores:
            return []
            
        max_score = kw_scores[0][1]
        result = []
        for kw, score, count in kw_scores:
            result.append({
                "token": kw,
                "count": count if count > 0 else 1,
                "importance": round((score / max_score) * 100, 1) if max_score > 0 else 0.0,
                "is_tech": kw in TECHNICAL_DICTIONARY
            })
        print(f"[TF-IDF Model] Extracted {len(result)} keywords successfully.")
        return result
    except Exception as e:
        print(f"[TF-IDF Parser Warning] Falling back to Polars parser due to: {e}")

    # Fallback to Polars grouped counts
    tokens = clean_and_tokenize(text)
    if not tokens:
        return []
    df = pl.DataFrame({"token": tokens})
    try:
        kw_df = (
            df.filter(
                (~pl.col("token").is_in(STOP_WORDS)) & 
                (pl.col("token").is_in(TECHNICAL_DICTIONARY) | (pl.col("token").str.len_chars() > 2))
            )
            .group_by("token")
            .agg(pl.len().alias("count"))
            .sort("count", descending=True)
            .limit(limit)
        )
        result = kw_df.to_dicts()
        if not result:
            return []
        max_count = result[0]["count"]
        for kw in result:
            kw["importance"] = round((kw["count"] / max_count) * 100, 1)
            kw["is_tech"] = kw["token"] in TECHNICAL_DICTIONARY
        return result
    except Exception as ex:
        print(f"[Polars Parser Error] DataFrame grouping failed: {ex}")
        freq = {}
        for t in tokens:
            if t not in STOP_WORDS and (t in TECHNICAL_DICTIONARY or len(t) > 2):
                freq[t] = freq.get(t, 0) + 1
        sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:limit]
        if not sorted_freq:
            return []
        max_c = sorted_freq[0][1]
        return [
            {
                "token": k, 
                "count": v, 
                "importance": round((v / max_c) * 100, 1), 
                "is_tech": k in TECHNICAL_DICTIONARY
            } 
            for k, v in sorted_freq
        ]

if __name__ == "__main__":
    # Quick debug run
    sample = "Python and PyTorch developer working on MLOps, LLM, RAG and Docker. We also use fastapi and SQL."
    kws = extract_keywords_polars(sample)
    print("Extracted Keywords:")
    for kw in kws:
        print(f" - {kw['token']}: count={kw['count']} importance={kw['importance']}% is_tech={kw['is_tech']}")
