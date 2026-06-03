"""
Production-grade Job Scrapers — TopCV & VietnamWorks
=====================================================
Strategy:
  - TopCV   : Uses the hidden JSON POST API (as captured from browser DevTools)
               Phase 1: POST /tim-viec-lam-<slug>?type_keyword=1&sba=1 → JSON listing
               Phase 2: Extract real job detail URLs from the JSON payload
  - VNWorks : HTTP requests + BeautifulSoup (lightweight, no Selenium needed)

Anti-detection:
  - Real Chrome/Linux User-Agent
  - Randomized delays between requests
  - Session-based requests (cookie persistence)

NLP Fallback:
  If HTTP requests fail (blocked / offline), a TF-IDF / cosine-similarity
  engine ranks an offline Vietnamese tech-job pool and returns the top-N
  most relevant listings.
"""

from __future__ import annotations

import uuid
import time
import re
import random
import logging
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

# curl_cffi: impersonates real Chrome TLS fingerprint → bypasses Cloudflare
try:
    from curl_cffi import requests as cf_requests
    _CURL_CFFI_AVAILABLE = True
except ImportError:
    _CURL_CFFI_AVAILABLE = False
    logger_import = logging.getLogger("scrapers")
    logger_import.warning("curl_cffi not installed. TopCV scraping may fail (Cloudflare blocked).")

logger = logging.getLogger("scrapers")

# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────
BATCH_SIZE = 8           # max results to return
REQUEST_TIMEOUT = 15     # seconds per HTTP request

TOPCV_BASE_URL   = "https://www.topcv.vn"
VNWORKS_BASE_URL = "https://www.vietnamworks.com"

# Real Linux Chrome UA matching the curl sample
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

# ──────────────────────────────────────────────────────────
# Offline Vietnamese Tech Job Pool (NLP fallback)
# ──────────────────────────────────────────────────────────
VN_JOB_POOL: List[Dict] = [
    {
        "company_name": "VNG Corporation",
        "job_title": "AI Engineer (Recommendation Systems)",
        "job_url": "https://www.topcv.vn/viec-lam/ai-engineer-recommendation-systems-vng/1001",
        "job_description": "Phát triển hệ thống gợi ý và xử lý ngôn ngữ tự nhiên (NLP) cho sản phẩm Zalo. Yêu cầu Python, PyTorch, SQL và tối ưu hóa vector database.",
        "salary_range": "35,000,000 - 55,000,000 VND",
    },
    {
        "company_name": "Techcombank",
        "job_title": "Senior Data Engineer (Lakehouse Team)",
        "job_url": "https://www.topcv.vn/viec-lam/senior-data-engineer-lakehouse-techcombank/1002",
        "job_description": "Xây dựng hạ tầng Data Lakehouse cho mảng ngân hàng số. Thiết kế pipeline dữ liệu lớn sử dụng PySpark, DuckDB, Prefect và mô hình hóa dbt.",
        "salary_range": "40,000,000 - 65,000,000 VND",
    },
    {
        "company_name": "FPT Software",
        "job_title": "Python Software Engineer (FastAPI/Docker)",
        "job_url": "https://www.topcv.vn/viec-lam/python-software-engineer-fastapi-docker-fpt/1003",
        "job_description": "Phát triển các dịch vụ API hiệu năng cao sử dụng FastAPI, Django và quản lý container hóa bằng Docker/Kubernetes.",
        "salary_range": "25,000,000 - 45,000,000 VND",
    },
    {
        "company_name": "OneMount Group",
        "job_title": "Data Analyst (VinShop Team)",
        "job_url": "https://www.topcv.vn/viec-lam/data-analyst-vinshop-onemount/1004",
        "job_description": "Phân tích hành vi mua sắm và tối ưu hóa chuỗi cung ứng VinShop. Sử dụng SQL, Python pandas/polars và trực quan hóa dữ liệu.",
        "salary_range": "22,000,000 - 35,000,000 VND",
    },
    {
        "company_name": "VTI Cloud",
        "job_title": "Cloud DevOps Engineer (AWS/Terraform)",
        "job_url": "https://www.topcv.vn/viec-lam/cloud-devops-engineer-aws-terraform-vti/1005",
        "job_description": "Thiết kế hạ tầng đám mây AWS sử dụng Terraform, thiết lập CI/CD và tối ưu hóa chi phí vận hành dịch vụ.",
        "salary_range": "30,000,000 - 50,000,000 VND",
    },
    {
        "company_name": "MoMo (M-Service)",
        "job_title": "Senior Backend Engineer (NodeJS/Go)",
        "job_url": "https://www.topcv.vn/viec-lam/senior-backend-engineer-golang-momo/1006",
        "job_description": "Xây dựng microservices hiệu năng cao chịu tải hàng triệu giao dịch mỗi ngày. Yêu cầu Golang hoặc NodeJS, Redis, Kafka và Kubernetes.",
        "salary_range": "38,000,000 - 58,000,000 VND",
    },
    {
        "company_name": "Shopee Vietnam",
        "job_title": "Senior Frontend Engineer (React/TypeScript)",
        "job_url": "https://www.topcv.vn/viec-lam/senior-frontend-engineer-react-shopee/1007",
        "job_description": "Tối ưu hóa giao diện web thương mại điện tử Shopee. Thành thạo ReactJS, Next.js, Redux, TypeScript và tối ưu tốc độ tải trang SEO.",
        "salary_range": "35,000,000 - 60,000,000 VND",
    },
    {
        "company_name": "Viettel AI Centre",
        "job_title": "Deep Learning Scientist (NLP/Speech)",
        "job_url": "https://www.topcv.vn/viec-lam/deep-learning-scientist-nlp-speech-viettel/1008",
        "job_description": "Nghiên cứu các mô hình ngôn ngữ lớn (LLM), Generative AI và xử lý tiếng nói tiếng Việt. Yêu cầu PyTorch, Transformers, Python và Docker.",
        "salary_range": "45,000,000 - 75,000,000 VND",
    },
    {
        "company_name": "NAB Innovation Centre Vietnam",
        "job_title": "Python Cloud Developer (AWS/FastAPI)",
        "job_url": "https://www.topcv.vn/viec-lam/python-cloud-developer-aws-fastapi-nab/1009",
        "job_description": "Phát triển hệ thống tài chính ngân hàng trên AWS. Sử dụng Python, FastAPI, Terraform, AWS Lambda, RDS và lập trình hướng sự kiện.",
        "salary_range": "32,000,000 - 52,000,000 VND",
    },
    {
        "company_name": "KMS Technology",
        "job_title": "Data Scientist (Machine Learning)",
        "job_url": "https://www.topcv.vn/viec-lam/data-scientist-machine-learning-kms/1010",
        "job_description": "Phát triển các mô hình học máy phân tích dữ liệu kinh doanh và dự báo xu hướng. Sử dụng Python scikit-learn, XGBoost, pandas và SQL.",
        "salary_range": "28,000,000 - 45,000,000 VND",
    },
    {
        "company_name": "VinAI",
        "job_title": "AI Research Intern (Computer Vision)",
        "job_url": "https://www.topcv.vn/viec-lam/ai-research-intern-computer-vision-vinai/1011",
        "job_description": "Thực tập sinh nghiên cứu thị giác máy tính và học máy cho xe tự hành. Đòi hỏi kỹ năng Python tốt, nắm vững OpenCV, PyTorch, TensorFlow.",
        "salary_range": "5,000,000 - 9,000,000 VND",
    },
    {
        "company_name": "FPT Software",
        "job_title": "ReactJS Developer Intern",
        "job_url": "https://www.topcv.vn/viec-lam/reactjs-developer-intern-fpt-software/1012",
        "job_description": "Thực tập sinh lập trình giao diện ReactJS. Được đào tạo bài bản về HTML, CSS, JavaScript, ES6, React hooks và Redux Toolkit.",
        "salary_range": "5,000,000 - 8,000,000 VND",
    },
    {
        "company_name": "VNG Corporation",
        "job_title": "Machine Learning Engineering Intern",
        "job_url": "https://www.topcv.vn/viec-lam/machine-learning-engineering-intern-vng/1013",
        "job_description": "Thực tập sinh kỹ sư học máy. Hỗ trợ chuẩn bị dữ liệu, huấn luyện mô hình cơ bản sử dụng Python, numpy, pandas và scikit-learn.",
        "salary_range": "6,000,000 - 9,000,000 VND",
    },
    {
        "company_name": "MoMo (M-Service)",
        "job_title": "Data Analyst Intern",
        "job_url": "https://www.topcv.vn/viec-lam/data-analyst-intern-momo/1014",
        "job_description": "Thực tập sinh phân tích dữ liệu. Tham gia chuẩn bị báo cáo dashboard, viết truy vấn SQL trích xuất dữ liệu và phân tích hành vi cơ bản.",
        "salary_range": "5,000,000 - 8,000,000 VND",
    },
    {
        "company_name": "FPT Software",
        "job_title": "Data Engineer Intern",
        "job_url": "https://www.topcv.vn/viec-lam/data-engineer-intern-fpt-software/1015",
        "job_description": "Thực tập sinh kỹ sư dữ liệu. Hỗ trợ xây dựng pipeline ETL đơn giản, làm quen với SQL, Python, Spark và lập lịch quy trình.",
        "salary_range": "5,500,000 - 8,500,000 VND",
    },
    {
        "company_name": "Grab Vietnam",
        "job_title": "Software Engineering Intern (Backend)",
        "job_url": "https://www.topcv.vn/viec-lam/software-engineering-intern-backend-grab/1016",
        "job_description": "Thực tập sinh phát triển backend cho nền tảng gọi xe. Làm việc với Go, gRPC, Docker, PostgreSQL và thiết kế hệ thống phân tán.",
        "salary_range": "7,000,000 - 11,000,000 VND",
    },
    {
        "company_name": "Tiki Corporation",
        "job_title": "PHP Developer (Laravel/Symfony)",
        "job_url": "https://www.topcv.vn/viec-lam/php-developer-laravel-symfony-tiki/1017",
        "job_description": "Phát triển hệ thống e-commerce quy mô lớn với PHP, Laravel, Symfony. Tối ưu hiệu năng MySQL, Redis cache và tích hợp third-party payment gateway.",
        "salary_range": "20,000,000 - 38,000,000 VND",
    },
    {
        "company_name": "Sendo",
        "job_title": "PHP Backend Engineer",
        "job_url": "https://www.topcv.vn/viec-lam/php-backend-engineer-sendo/1018",
        "job_description": "Lập trình viên PHP backend cho nền tảng thương mại điện tử. Kỹ năng PHP 8+, MySQL, Redis, RabbitMQ và thiết kế RESTful API.",
        "salary_range": "18,000,000 - 32,000,000 VND",
    },
    {
        "company_name": "Sky Mavis",
        "job_title": "Java Backend Engineer (Spring Boot)",
        "job_url": "https://www.topcv.vn/viec-lam/java-backend-engineer-spring-boot-skymavis/1019",
        "job_description": "Phát triển backend Java với Spring Boot, Microservices cho game blockchain Axie Infinity. Yêu cầu Java 17+, Kubernetes, PostgreSQL.",
        "salary_range": "35,000,000 - 60,000,000 VND",
    },
    {
        "company_name": "Sapo Technology",
        "job_title": "Java Developer (Fresher/Junior)",
        "job_url": "https://www.topcv.vn/viec-lam/java-developer-fresher-junior-sapo/1020",
        "job_description": "Lập trình viên Java mới tốt nghiệp hoặc dưới 2 năm kinh nghiệm. Làm quen với Spring Framework, Java Core, OOP và SQL cơ bản.",
        "salary_range": "12,000,000 - 22,000,000 VND",
    },
]


# ──────────────────────────────────────────────────────────
# HTTP Session Factory
# ──────────────────────────────────────────────────────────

def _make_cf_session():
    """
    Returns a curl_cffi Session impersonating Chrome124 TLS fingerprint.
    This is the key to bypassing Cloudflare's bot detection on TopCV.
    Falls back to standard requests.Session if curl_cffi is unavailable.
    """
    if _CURL_CFFI_AVAILABLE:
        session = cf_requests.Session(impersonate="chrome124")
    else:
        session = requests.Session()
    session.headers.update({
        "Accept-Language": "en-US,en;q=0.9",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
    })
    return session


def _make_session() -> requests.Session:
    """Standard requests Session for VietnamWorks (no CF protection)."""
    session = requests.Session()
    session.headers.update(BASE_HEADERS)
    return session


def _random_delay(min_s: float = 0.5, max_s: float = 1.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


# ──────────────────────────────────────────────────────────
# TopCV Keyword → URL Slug Converter
# ──────────────────────────────────────────────────────────

# Maps common Vietnamese IT keywords to their TopCV URL slug
_TOPCV_SLUG_MAP: Dict[str, str] = {
    "php": "lap-trinh-vien-php",
    "python": "lap-trinh-vien-python",
    "java": "lap-trinh-vien-java",
    "javascript": "lap-trinh-vien-javascript",
    "nodejs": "lap-trinh-vien-nodejs",
    "react": "lap-trinh-vien-reactjs",
    "reactjs": "lap-trinh-vien-reactjs",
    "frontend": "lap-trinh-vien-frontend",
    "backend": "lap-trinh-vien-backend",
    "fullstack": "lap-trinh-vien-fullstack",
    "data engineer": "data-engineer",
    "data analyst": "data-analyst",
    "data scientist": "data-scientist",
    "machine learning": "ky-su-machine-learning",
    "ai engineer": "ky-su-ai",
    "devops": "ky-su-devops",
    "mobile": "lap-trinh-vien-mobile",
    "android": "lap-trinh-vien-android",
    "ios": "lap-trinh-vien-ios",
    "sql": "lap-trinh-vien-sql",
    "golang": "lap-trinh-vien-golang",
    "go": "lap-trinh-vien-golang",
    "ruby": "lap-trinh-vien-ruby",
    "c#": "lap-trinh-vien-c-sharp",
    "dotnet": "lap-trinh-vien-dotnet",
    ".net": "lap-trinh-vien-dotnet",
    "flutter": "lap-trinh-vien-flutter",
    "kotlin": "lap-trinh-vien-kotlin",
    "swift": "lap-trinh-vien-swift",
    "intern": "thuc-tap-sinh-cntt",
    "thực tập": "thuc-tap-sinh-cntt",
    "fresher": "fresher-cntt",
}


def _clean_vietnamese_accents(text: str) -> str:
    """
    Removes Vietnamese diacritics/accents from a string.
    """
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


# ──────────────────────────────────────────────────────────
# TopCV Scraper — curl_cffi (Cloudflare bypass)
# ──────────────────────────────────────────────────────────

def _extract_topcv_job_urls(html: str) -> List[str]:
    """
    Extracts clean job detail URLs from a TopCV listing page HTML.
    Uses the confirmed selector: h3.title a[href]
    Strips tracking query params (?ta_source=...) from URLs.
    """
    soup = BeautifulSoup(html, "lxml")
    urls: List[str] = []

    # Primary: proven selector from live testing
    for a_tag in soup.select("h3.title a[href]"):
        href = a_tag.get("href", "")
        if not href:
            continue
        # Strip tracking params, keep only the base URL
        clean_url = re.sub(r"\?.*", "", href)
        if not clean_url.startswith("http"):
            clean_url = f"{TOPCV_BASE_URL}{clean_url}"
        if "/viec-lam/" in clean_url and clean_url not in urls:
            urls.append(clean_url)
        if len(urls) >= BATCH_SIZE:
            break

    # Fallback selectors if primary fails
    if not urls:
        for a_tag in soup.select(".job-item__title a[href], a.job-title[href]"):
            href = a_tag.get("href", "")
            clean_url = re.sub(r"\?.*", "", href)
            if not clean_url.startswith("http"):
                clean_url = f"{TOPCV_BASE_URL}{clean_url}"
            if "/viec-lam/" in clean_url and clean_url not in urls:
                urls.append(clean_url)
            if len(urls) >= BATCH_SIZE:
                break

    return urls


def _parse_topcv_detail_page(html: str, job_url: str) -> Dict:
    """
    Parses a TopCV job detail page.
    Selectors verified from live page inspection.
    """
    soup = BeautifulSoup(html, "lxml")
    info: Dict = {
        "title": "N/A",
        "company": "N/A",
        "salary": "Thỏa thuận",
        "description": "",
        "experience": "",
        "location": "",
    }

    # Title — h1 is always present
    h1 = soup.select_one("h1")
    if h1:
        info["title"] = h1.get_text(strip=True)

    # Company — confirmed selector: [class*="company-name"]
    for sel in [
        "[class*='company-name']",
        "a.employer-title",
        "a[href*='/nha-tuyen-dung/']",
        ".employer-name",
    ]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            # Avoid short/generic texts
            if text and len(text) > 3 and text.lower() not in ("quy mô:", "quy mo:"):
                info["company"] = text
                break

    # Salary + Experience + Location — from .job-detail__info--section items
    for section in soup.select(".job-detail__info--section"):
        label_el = section.select_one(".job-detail__info--section-content-title, [class*='label']")
        value_el = section.select_one(".job-detail__info--section-content-value, [class*='value']")
        if not label_el:
            # Sometimes the section itself has label+value as text
            text = section.get_text(" ", strip=True)
            if "Mức lương" in text:
                parts = text.replace("Mức lương", "").strip()
                if parts and parts != "Thoả thuận":
                    info["salary"] = parts
                elif "Thoả thuận" in text:
                    info["salary"] = "Thỏa thuận"
            elif "Kinh nghiệm" in text or "Kinh nghiem" in text:
                info["experience"] = text.replace("Kinh nghiệm", "").strip()
            elif "Địa điểm" in text or "Dia diem" in text:
                info["location"] = text.replace("Địa điểm", "").strip()
            continue
        label = label_el.get_text(strip=True)
        value = value_el.get_text(strip=True) if value_el else ""
        if "lương" in label.lower() or "salary" in label.lower():
            info["salary"] = value or "Thỏa thuận"
        elif "nghiệm" in label.lower() or "experience" in label.lower():
            info["experience"] = value
        elif "điểm" in label.lower() or "location" in label.lower():
            info["location"] = value

    # Description — job-description blocks
    desc_parts = []
    for sel in [
        ".job-description__item--content",
        ".job-description",
        ".job-detail__body",
    ]:
        for el in soup.select(sel):
            text = el.get_text(" ", strip=True)
            if text and len(text) > 50:
                desc_parts.append(text)
        if desc_parts:
            break

    info["description"] = " ".join(desc_parts)[:700]
    return info


def scrape_topcv(keyword: str) -> List[Dict]:
    """
    TopCV scraper powered by curl_cffi (Chrome TLS impersonation).

    URL pattern: https://www.topcv.vn/tim-viec-lam-<keyword-slug>
    e.g. 'java developer' → /tim-viec-lam-java-developer  (50 jobs)
         'data engineer'  → /tim-viec-lam-data-engineer
         'php'            → /tim-viec-lam-php

    Slug is built by lowercasing + replacing spaces/special chars with dashes.
    The optional _TOPCV_SLUG_MAP overrides for Vietnamese category pages.
    """
    if not _CURL_CFFI_AVAILABLE:
        logger.warning("[TopCV] curl_cffi not available — skipping TopCV scrape")
        return []

    session = _make_cf_session()
    jobs: List[Dict] = []

    # Build slug: exact map match only → otherwise direct conversion
    # e.g. 'php' → 'lap-trinh-vien-php' (category page, more results)
    #      'java developer' → 'java-developer' (direct, works great)
    #      'data engineer' → 'data-engineer'
    kw_clean = _clean_vietnamese_accents(keyword).strip()
    if kw_clean in _TOPCV_SLUG_MAP:
        slug = _TOPCV_SLUG_MAP[kw_clean]
    else:
        # Direct conversion — no partial map, avoid wrong slug matches
        slug = re.sub(r"[^a-z0-9]+", "-", kw_clean).strip("-")

    listing_url = f"{TOPCV_BASE_URL}/tim-viec-lam-{slug}?type_keyword=1&sba=1&saturday_status=0"

    # ── Phase 1: POST listing page ──
    try:
        logger.info("[TopCV] POST %s", listing_url)
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-length": "0",
            "origin": "https://www.topcv.vn",
            "priority": "u=1, i",
            "referer": f"https://www.topcv.vn/tim-viec-lam-{slug}?type_keyword=1&sba=1",
            "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            "x-csrf-token": "pSqW4lXvqZKKSWvjzxYJzT9SVeq3C40LWtH958st",
            "x-requested-with": "XMLHttpRequest",
        }
        cookies = {
            "_tafp": "4e9c6a607b9bcab238471204b9113f64",
            "popup-ebook-cv": "1",
            "_taid": "xw0eUT2pXo.1780462354047",
            "_tasid": "wqc5nQxI9t.1780462354048",
            "cf_clearance": "Z48QuPmd4Oa9D1ezs7AIg327r2BNPmN6RLbAGXTnLYY-1780462354-1.2.1.1-fzlksdIvhXrxBsVAmyfuYP6.Tb6DM0MipHPGFBKsng4mRRuccCHTLNYPXqnpMWfZ6DUykA.3OqWz6eJigGK96Kplga86ozXbk04dOPkwipXHsDuniy45rKrej0gUX1u_jr5RXX.uV3uZnsCa4Qqf2GyJUmNDClkqXq_oZ2zupPURWM3Mdohrc_9nb5A6j6yh45_HBXgiFkrTcpOm0yfK5iIJLoARaiK58v1OhBDTsC3V52sZHucUW56zVEtL4I9yceqRStTp8r0ve_gLtmlMRTaUGT9Yvk0KbRoR8HKhN9c2LsXY.ImhVTXHCftyzRkvkcM4SJdbOAbYC8U7RsjZtA",
            "appier": "%7B%22event%22%3A%22job_searched%22%2C%22payload%22%3A%7B%22searched_keyword%22%3A%22%22%2C%22job_category%22%3A%22%22%2C%22company_category%22%3A%22%22%2C%22work_location%22%3A%22%22%7D%7D",
            "g_state": '{"i_l":0,"i_ll":1780462363295,"i_b":"iYsQK0VRLmSN6GYIHa/7958L/zmxg7UZntidRWIxMhw","i_e":{"enable_itp_optimization":0},"i_et":1780462354192}',
            "ref_source_tracking_id": "eyJpdiI6InZ1RVVhV3J3aFFGTTdyS1NvOTVUa0E9PSIsInZhbHVlIjoiOG1aTnlPNnpYYWRDV21uQXlkUHBOaVZENklGeHo1TjA5ZnJZQW9ublhuSEx6bHNCUWZ4Ky9OU0ozSHY2Z01hM1Q3NWVjb04vYnZ6SmQ5aXNIK29VZzduOWJxOCsyUlcrMk1BMzJqMTFDMnc9IiwibWFjIjoiODgxNDFhYjM2N2IxZDkwOTU0ZGMzMTNlNjdhMzIxYmE5OWNhZmI0YzNjMGM5YjZiNTY3ZjI4MTg4ODZiZTgxOCIsInRhZyI6IiJ9",
            "XSRF-TOKEN": "eyJpdiI6IkwxVTRZbW11NXVPZVdNeTBSNjVEZlE9PSIsInZhbHVlIjoiRlNkd0ZsVmRrdktLWlMzTW9HRnpsNXNHU2pkbHlkSHpNYU1ic2ExL1FjbUpLakt5b3dTbVhUWkkycS9JNm9kbWNvZGZuRjhOcis0SFlBY2xVaEUrSXJxcVRDMlZNa2dseGkwUGJGR2dXMG1zeE93b0dqWU92TTFIWDd1dFo3K1QiLCJtYWMiOiIzNWViODljZmI5MGM2NmIzNTg1NjUzNTRlOGMzYWRhYjVhZjk4YzM4MDM4ODUzMTJhNzM2NjZmN2MzZDdiNzc4IiwidGFnIjoiIn0%3D",
            "topcv_session": "eyJpdiI6IjdlZHRlMWJwam03MjdibG1WSDJlRVE9PSIsInZhbHVlIjoiNTFFcjBnekZoQ0YxS3Nzek95Y2N6emlacVRYelRjU3k4T2dLOXUzcTRGMTlqOHluRFc1a2hveEkzLzVUbVcrT3BEaDlRNm1hUW4zOWNoZlpETDh4c0ZadU1aTFlUT210aVlSNlU5MHo4NXc4UnJuaXdLV0k3MnI2UnRsaUw1cm0iLCJtYWMiOiI4OGEwZTg3NmRiZWNiYWVlZmFkMDc0NGVlMDU5OTljYjk5NmNhMmU3YmQxMGYxM2YwOWYzZDdlOTdiZTdjM2JjIiwidGFnIjoiIn0%3D",
            "_tasla": "1780462368126",
            "is_save_log_keyword": "true",
        }

        resp = cf_requests.post(
            listing_url,
            headers=headers,
            cookies=cookies,
            data="",
            timeout=REQUEST_TIMEOUT,
            impersonate="chrome124",
        )
        if resp.status_code != 200:
            logger.warning("[TopCV] Listing page returned HTTP %d", resp.status_code)
            return []

        try:
            res_json = resp.json()
            html_content = res_json.get("data", {}).get("html_job", "")
        except Exception:
            html_content = resp.text

        job_urls = _extract_topcv_job_urls(html_content)
        logger.info("[TopCV] Extracted %d job URLs from listing page", len(job_urls))

    except Exception as exc:
        logger.warning("[TopCV] Listing page failed: %s", exc)
        return []

    # ── Phase 2: Parse each job detail page ──
    for url in job_urls[:BATCH_SIZE]:
        try:
            _random_delay(0.4, 0.9)
            detail_resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if detail_resp.status_code != 200:
                logger.debug("[TopCV] Detail page %s returned %d", url, detail_resp.status_code)
                continue

            parsed = _parse_topcv_detail_page(detail_resp.text, url)

            desc = parsed["description"]
            if not desc:
                desc = f"Tuyển dụng vị trí {parsed['title']} tại {parsed['company']}. Xem chi tiết tại TopCV."

            exp_note = parsed["experience"]
            loc_note = parsed["location"]
            notes_parts = ["[TopCV Live]"]
            if exp_note:
                notes_parts.append(f"KN: {exp_note}")
            if loc_note:
                notes_parts.append(f"Địa điểm: {loc_note}")

            jobs.append({
                "id": str(uuid.uuid4()),
                "company_name": parsed["company"],
                "job_title": parsed["title"],
                "job_url": url,
                "job_description": desc,
                "status": "WISHLIST",
                "salary_range": parsed["salary"],
                "notes": " | ".join(notes_parts),
                "source": "TopCV",
            })

        except Exception as exc:
            logger.debug("[TopCV] Detail parse failed for %s: %s", url, exc)

    logger.info("[TopCV] Scraped %d jobs for keyword='%s'", len(jobs), keyword)
    return jobs


# ──────────────────────────────────────────────────────────
# VietnamWorks Scraper — HTTP requests + BeautifulSoup
# ──────────────────────────────────────────────────────────

def _parse_vnworks_card(card: BeautifulSoup) -> Optional[Dict]:
    """Parses a single VietnamWorks job card from HTML."""
    title_el = card.select_one("h3 a, h2 a, .job-title a")
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    link = href if href.startswith("http") else f"{VNWORKS_BASE_URL}{href}"

    comp_el = card.select_one('a[href*="/nha-tuyen-dung/"], .company-name a, .employer-name')
    company = comp_el.get_text(strip=True) if comp_el else "N/A"

    salary = "Thương lượng"
    for sel in [".salary", "[class*='salary']", ".compensation"]:
        el = card.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text and len(text) < 80:
                salary = text
                break

    return {"title": title, "link": link, "company": company, "salary": salary}


def scrape_vietnamworks(keyword: str) -> List[Dict]:
    """HTTP + BeautifulSoup VietnamWorks scraper."""
    session = _make_session()
    jobs: List[Dict] = []

    try:
        kw_clean = _clean_vietnamese_accents(keyword).strip()
        kw_slug = re.sub(r"[^a-z0-9]+", "-", kw_clean).strip("-")
        search_urls = [
            f"{VNWORKS_BASE_URL}/viec-lam/{kw_slug}",
            f"{VNWORKS_BASE_URL}/tim-viec-lam",
        ]
        params_list = [
            {"l": "0"},
            {"q": keyword, "l": "0"},
        ]

        soup = None
        for url, params in zip(search_urls, params_list):
            try:
                logger.info("[VNWorks] GET %s params=%s", url, params)
                _random_delay(0.5, 1.0)
                resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")
                cards = soup.select(".view_job_item:not(.top_company)")
                if not cards:
                    cards = soup.select("article.job-item, div[class*='job-item']:not([class*='top'])")
                if cards:
                    logger.info("[VNWorks] Found %d cards at %s", len(cards), url)
                    break
            except Exception as e:
                logger.debug("[VNWorks] URL failed %s: %s", url, e)
                soup = None

        if not soup:
            return []

        cards = soup.select(".view_job_item:not(.top_company)")
        if not cards:
            cards = soup.select("article.job-item, div[class*='job-item']:not([class*='top'])")

        logger.info("[VNWorks] Processing %d cards", len(cards))

        for card in cards[:BATCH_SIZE * 2]:
            parsed = _parse_vnworks_card(card)
            if not parsed:
                continue

            desc = (
                f"Tuyển dụng vị trí {parsed['title']} tại {parsed['company']}. "
                "Chi tiết mô tả công việc và nộp đơn ứng tuyển tại VietnamWorks."
            )
            jobs.append({
                "id": str(uuid.uuid4()),
                "company_name": parsed["company"],
                "job_title": parsed["title"],
                "job_url": parsed["link"],
                "job_description": desc,
                "status": "WISHLIST",
                "salary_range": parsed["salary"],
                "notes": "[VietnamWorks Live]",
                "source": "VietnamWorks",
            })
            if len(jobs) >= BATCH_SIZE:
                break

    except Exception as exc:
        logger.warning("[VNWorks] Scraping failed: %s", exc)

    logger.info("[VNWorks] Total: %d jobs for keyword='%s'", len(jobs), keyword)
    return jobs


# ──────────────────────────────────────────────────────────
# Relevance Filter
# ──────────────────────────────────────────────────────────

_SENIOR_TOKENS = {
    "senior", "lead", "principal", "manager", "head",
    "director", "architect", "trưởng", "giám đốc",
}
_INTERN_TOKENS = {
    "intern", "trainee", "thực tập", "thuctap", "fresher", "junior",
}


def _is_intern_search(kw: str) -> bool:
    kw_lower = kw.lower()
    return any(tok in kw_lower for tok in _INTERN_TOKENS)


def _is_senior_title(title: str) -> bool:
    title_lower = title.lower()
    return any(tok in title_lower for tok in _SENIOR_TOKENS)


def _relevance_filter(jobs: List[Dict], keyword: str) -> List[Dict]:
    """
    Soft relevance filter:
     - Removes Senior roles when searching for Intern/Fresher positions
     - For tech keywords, requires at least one token in job title (not description)
       to avoid false positives from unrelated VNWorks listings
    """
    kw_clean = keyword.lower().strip()
    kw_tokens = set(re.split(r"[\s\-_/]+", kw_clean))
    kw_tokens = {t for t in kw_tokens if len(t) > 1}  # drop single-char tokens
    intern_search = _is_intern_search(kw_clean)

    filtered = []
    for j in jobs:
        title_lower = j["job_title"].lower()
        desc_lower = j["job_description"].lower()
        company_lower = j["company_name"].lower()

        # Mutual exclusivity: no senior roles in intern searches
        if intern_search and _is_senior_title(title_lower):
            continue

        # For live-scraped results from VNWorks, title must contain at least
        # one keyword token to filter irrelevant results
        if j.get("source") == "VietnamWorks":
            if any(tok in title_lower for tok in kw_tokens):
                filtered.append(j)
        else:
            # For TopCV and offline, be lenient (check title + description + company)
            combined = f"{title_lower} {desc_lower} {company_lower}"
            if any(tok in combined for tok in kw_tokens):
                filtered.append(j)

    return filtered


# ──────────────────────────────────────────────────────────
# NLP TF-IDF Fallback Recommender
# ──────────────────────────────────────────────────────────

def _nlp_recommend(keyword: str) -> List[Dict]:
    """
    When live scraping returns nothing (blocked / offline), rank the
    offline VN_JOB_POOL using TF-IDF cosine similarity and return
    the top-BATCH_SIZE results.
    """
    kw_clean = keyword.lower().strip()
    intern_search = _is_intern_search(kw_clean)

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as cs

        corpus = [
            f"{j['job_title']} {j['company_name']} {j['job_description']}"
            for j in VN_JOB_POOL
        ]
        vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1)
        tfidf = vec.fit_transform(corpus)
        query_vec = vec.transform([keyword])
        scores = cs(query_vec, tfidf)[0]

        ranked = []
        for idx, score in enumerate(scores):
            job = VN_JOB_POOL[idx]
            if intern_search and _is_senior_title(job["job_title"]):
                continue
            if score > 0.05:
                ranked.append((score, job))

        ranked.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, j in ranked[:BATCH_SIZE]:
            results.append({
                "id": str(uuid.uuid4()),
                "company_name": j["company_name"],
                "job_title": j["job_title"],
                "job_url": j["job_url"],
                "job_description": j["job_description"],
                "status": "WISHLIST",
                "salary_range": j["salary_range"],
                "notes": f"[NLP Gợi ý] Độ phù hợp: {score:.0%}",
                "source": "Offline Pool",
            })
        return results

    except Exception as exc:
        logger.warning("[NLP] TF-IDF failed (%s), using token fallback", exc)

    # Simple token overlap fallback
    kw_tokens = set(re.split(r"[\s\-_/]+", kw_clean))
    results = []
    for j in VN_JOB_POOL:
        if intern_search and _is_senior_title(j["job_title"]):
            continue
        title_tokens = set(re.split(r"[\s\-_/()\[\]]+", j["job_title"].lower()))
        if kw_tokens & title_tokens:
            results.append({
                "id": str(uuid.uuid4()),
                "company_name": j["company_name"],
                "job_title": j["job_title"],
                "job_url": j["job_url"],
                "job_description": j["job_description"],
                "status": "WISHLIST",
                "salary_range": j["salary_range"],
                "notes": "[Gợi ý từ kho dữ liệu]",
                "source": "Offline Pool",
            })
        if len(results) >= BATCH_SIZE:
            break
    return results


# ──────────────────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────────────────

def crawl_vietnamese_jobs(keyword: str) -> List[Dict]:
    """
    Orchestrates the full job search pipeline:
      1. Live scrape TopCV (HTTP POST JSON API → HTML fallback)
      2. Live scrape VietnamWorks (HTTP + BeautifulSoup)
      3. Filter for relevance
      4. If still empty → NLP TF-IDF offline recommender

    Returns up to BATCH_SIZE * 2 = 16 results max.
    """
    logger.info("[Pipeline] Starting job crawl for keyword='%s'", keyword)

    live_results: List[Dict] = []
    live_results.extend(scrape_topcv(keyword))
    live_results.extend(scrape_vietnamworks(keyword))

    if live_results:
        filtered = _relevance_filter(live_results, keyword)
        if filtered:
            logger.info("[Pipeline] Returning %d live filtered results", len(filtered))
            return filtered[:BATCH_SIZE * 2]
        # Return unfiltered if filter is too strict
        if live_results:
            logger.info("[Pipeline] Filter returned 0; returning unfiltered %d results", len(live_results))
            return live_results[:BATCH_SIZE * 2]

    logger.info("[Pipeline] No live results – triggering NLP fallback")
    return _nlp_recommend(keyword)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    kw = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "PHP developer"
    results = crawl_vietnamese_jobs(kw)
    print(f"\n{'='*60}")
    print(f"Kết quả cho: '{kw}'  ({len(results)} việc làm)")
    print("=" * 60)
    for job in results:
        print(f"  [{job['source']}] [{job['company_name']}] {job['job_title']}")
        print(f"    💰 {job['salary_range']}")
        print(f"    🔗 {job['job_url']}")
        print(f"    📝 {job['notes']}")
        print()
