import os
from functools import lru_cache
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()


def is_supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


@lru_cache(maxsize=1)
def _client():
    if not is_supabase_configured():
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def check_supabase() -> bool:
    _client().table("faqs").select("id").limit(1).execute()
    return True


def migrate_default_faqs() -> int:
    """Insert default FAQs only when their normalized question is not already present."""
    from excel_store import DEFAULT_FAQS

    client = _client()
    result = client.table("faqs").select("question").execute()
    known = {
        str(row.get("question", "")).strip().casefold()
        for row in (result.data or [])
    }
    inserted = 0
    for row in DEFAULT_FAQS:
        question, answer, category = str(row[1]).strip(), str(row[2]).strip(), str(row[3]).strip()
        if question.casefold() not in known:
            client.table("faqs").insert({
                "question": question,
                "answer": answer,
                "category": category or "General",
                "status": "Active",
            }).execute()
            known.add(question.casefold())
            inserted += 1
    return inserted


def get_faqs(category=None, search=None):
    query = _client().table("faqs").select("id,question,answer,category,status,created_at").eq("status", "Active").order("id")
    result = query.execute()
    rows = result.data or []
    if category:
        target = category.strip().casefold()
        rows = [row for row in rows if str(row.get("category", "")).casefold() == target]
    if search:
        term = search.strip().casefold()
        rows = [row for row in rows if term in str(row.get("question", "")).casefold()
                or term in str(row.get("answer", "")).casefold()]
    return rows


def get_faq_by_id(faq_id: int):
    result = _client().table("faqs").select("*").eq("id", faq_id).limit(1).execute()
    return result.data[0] if result.data else None


def add_faq(question: str, answer: str, category: str = "General"):
    client = _client()
    existing = client.table("faqs").select("id,question").execute()
    normalized = question.strip().casefold()
    if any(str(row.get("question", "")).strip().casefold() == normalized for row in (existing.data or [])):
        raise ValueError("That FAQ question already exists.")
    result = client.table("faqs").insert({
        "question": question.strip(),
        "answer": answer.strip(),
        "category": category.strip() or "General",
        "status": "Active",
    }).execute()
    if not result.data:
        raise RuntimeError("Supabase did not return the inserted FAQ.")
    return result.data[0]


def log_login_activity(name: str, email: str, source: str = "Website", ip_address: str = ""):
    result = _client().table("login_activities").insert({
        "name": name.strip(),
        "email": email.strip().lower(),
        "source": source.strip() or "Website",
        "ip_address": ip_address,
    }).execute()
    return result.data[0] if result.data else {}


def save_chat(question: str, answer: str):
    result = _client().table("chat_history").insert({
        "question": question.strip(),
        "answer": answer.strip(),
    }).execute()
    return result.data[0] if result.data else {}


def find_chat_answer(question: str) -> str:
    """Simple FAQ matching chatbot; this is retrieval, not a generative AI model."""
    import re

    words = {word for word in re.findall(r"[a-z0-9]+", question.casefold()) if len(word) > 2}
    faqs = get_faqs()
    best_answer, best_score = None, 0
    for faq in faqs:
        haystack = (str(faq.get("question", "")) + " " + str(faq.get("answer", ""))).casefold()
        score = sum(1 for word in words if word in haystack)
        if score > best_score:
            best_answer, best_score = faq.get("answer"), score
    return (str(best_answer) if best_answer and best_score else
            "I couldn't find an exact answer in the FAQ database. Please contact the administrator.")
