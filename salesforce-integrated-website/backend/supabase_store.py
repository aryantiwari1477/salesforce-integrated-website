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
    
def sync_excel_storage():
    import hashlib
    import json
    from io import BytesIO
    from datetime import datetime, timezone
    from openpyxl import load_workbook

    bucket = os.getenv("EXCEL_STORAGE_BUCKET", "aryan-connect-excel")
    path = os.getenv("EXCEL_STORAGE_PATH", "college_data (1).xlsx")
    client = _client()

    # Download the existing Excel workbook from private Supabase Storage.
    raw = client.storage.from_(bucket).download(path)
    wb = load_workbook(BytesIO(raw))
    if "FAQs" not in wb.sheetnames:
        raise RuntimeError("FAQs sheet not found in Excel workbook.")

    sheet = wb["FAQs"]
    headers = [str(c.value).strip() if c.value else "" for c in sheet[1]]

    for name in ["supabase_id", "sync_hash"]:
        if name not in headers:
            sheet.cell(1, len(headers) + 1).value = name
            headers.append(name)

    def col(name):
        return headers.index(name) + 1

    def value(row, name):
        return sheet.cell(row, col(name)).value or ""

    def digest(q, a, c):
        data = [str(q).strip(), str(a).strip(), str(c or "General").strip()]
        return hashlib.sha256(json.dumps(data).encode()).hexdigest()

    result = client.table("faqs").select(
        "id,excel_id,question,answer,category,status,sync_hash"
    ).execute()
    db_rows = result.data or []
    by_id = {str(x["id"]): x for x in db_rows}
    by_excel = {str(x["excel_id"]): x for x in db_rows if x.get("excel_id") is not None}
    by_question = {
        str(x["question"]).strip().casefold(): x for x in db_rows
    }

    excel_ids = set()
    imported = exported = updated_db = updated_excel = conflicts = 0
    now = datetime.now(timezone.utc).isoformat()

    for r in range(2, sheet.max_row + 1):
        q, a, category = value(r, "question"), value(r, "answer"), value(r, "category")
        if not str(q).strip() or not str(a).strip():
            continue

        excel_id = str(value(r, "id")).strip()
        supabase_id = str(value(r, "supabase_id")).strip()
        db = by_id.get(supabase_id) or by_excel.get(excel_id) or by_question.get(str(q).strip().casefold())

        if not db:
            h = digest(q, a, category)
            inserted = client.table("faqs").insert({
                "question": str(q).strip(),
                "answer": str(a).strip(),
                "category": str(category or "General").strip(),
                "status": "Active",
                "excel_id": int(excel_id) if excel_id.isdigit() else None,
                "sync_hash": h,
                "updated_at": now,
            }).execute()
            db = inserted.data[0]
            imported += 1
        else:
            base = db.get("sync_hash")
            excel_hash = digest(q, a, category)
            db_hash = digest(db.get("question"), db.get("answer"), db.get("category"))
            if not base:
                # First sync: preserve the live Supabase version.
                excel_hash = db_hash
            elif excel_hash != base and db_hash == base:
                client.table("faqs").update({
                    "question": str(q).strip(),
                    "answer": str(a).strip(),
                    "category": str(category or "General").strip(),
                    "excel_id": int(excel_id) if excel_id.isdigit() else None,
                    "sync_hash": excel_hash,
                    "updated_at": now,
                }).eq("id", db["id"]).execute()
                db.update({"question": q, "answer": a, "category": category, "sync_hash": excel_hash})
                updated_db += 1
            elif db_hash != base and excel_hash == base:
                updated_excel += 1
            elif db_hash != base and excel_hash != base and db_hash != excel_hash:
                conflicts += 1
                continue

            h = digest(db.get("question"), db.get("answer"), db.get("category"))
            client.table("faqs").update({
                "excel_id": int(excel_id) if excel_id.isdigit() else db.get("excel_id"),
                "sync_hash": h,
                "updated_at": now,
            }).eq("id", db["id"]).execute()
            sheet.cell(r, col("supabase_id")).value = db["id"]
            sheet.cell(r, col("sync_hash")).value = h

            if base is None or db_hash != base and excel_hash == base:
                sheet.cell(r, col("question")).value = db.get("question")
                sheet.cell(r, col("answer")).value = db.get("answer")
                sheet.cell(r, col("category")).value = db.get("category") or "General"
                sheet.cell(r, col("sync_hash")).value = h

        sheet.cell(r, col("supabase_id")).value = db["id"]
        excel_ids.add(str(db["id"]))

    # Export Supabase FAQs that do not yet have a matching Excel row.
    for db in db_rows:
        if str(db["id"]) in excel_ids:
            continue
        if db.get("status") == "Inactive":
            continue
        new_excel_id = max(
            [int(sheet.cell(i, col("id")).value or 0)
             for i in range(2, sheet.max_row + 1)
             if str(sheet.cell(i, col("id")).value or "").isdigit()]
            + [0]
        ) + 1
        h = digest(db["question"], db["answer"], db.get("category"))
        row = {name: "" for name in headers}
        row.update({
            "id": new_excel_id,
            "question": db["question"],
            "answer": db["answer"],
            "category": db.get("category") or "General",
            "supabase_id": db["id"],
            "sync_hash": h,
        })
        sheet.append([row.get(name, "") for name in headers])
        client.table("faqs").update({
            "excel_id": new_excel_id,
            "sync_hash": h,
            "updated_at": now,
        }).eq("id", db["id"]).execute()
        exported += 1

    output = BytesIO()
    wb.save(output)
    wb.close()
    client.storage.from_(bucket).upload(
        path,
        output.getvalue(),
        {"upsert": "true", "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )

    return {
        "message": "Excel and Supabase sync finished.",
        "excel_to_supabase": imported + updated_db,
        "supabase_to_excel": exported + updated_excel,
        "conflicts": conflicts,
        "storage_file": path,
    }

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
