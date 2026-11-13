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
    """Find the closest matching FAQ answer."""
    import re

    words = {
        word for word in re.findall(r"[a-z0-9]+", question.casefold())
        if len(word) > 2
    }

    faqs = get_faqs()
    best_answer = None
    best_score = 0

    for faq in faqs:
        text = (
            str(faq.get("question", "")) + " " +
            str(faq.get("answer", ""))
        ).casefold()

        score = sum(1 for word in words if word in text)

        if score > best_score:
            best_answer = faq.get("answer")
            best_score = score

    if best_answer and best_score:
        return str(best_answer)

    return "I couldn't find an exact answer in the FAQ database. Please contact the administrator."


def sync_excel_storage():
    import hashlib
    import json
    from io import BytesIO
    from datetime import datetime, timezone
    from openpyxl import load_workbook

    bucket = os.getenv("EXCEL_STORAGE_BUCKET", "aryan-connect-excel")
    path = os.getenv("EXCEL_STORAGE_PATH", "college_data.xlsx")

    client = _client()

    # Download Excel from Supabase Storage
    raw = client.storage.from_(bucket).download(path)
    wb = load_workbook(BytesIO(raw))

    if "FAQs" not in wb.sheetnames:
        raise RuntimeError("FAQs sheet not found.")

    sheet = wb["FAQs"]

    headers = [
        str(cell.value).strip() if cell.value else ""
        for cell in sheet[1]
    ]

    for name in ["supabase_id", "sync_hash"]:
        if name not in headers:
            headers.append(name)
            sheet.cell(1, len(headers)).value = name

    def col(name):
        return headers.index(name) + 1

    def cell_value(row, name):
        return sheet.cell(row, col(name)).value or ""

    def digest(question, answer, category):
        data = [
            str(question).strip(),
            str(answer).strip(),
            str(category or "General").strip()
        ]
        return hashlib.sha256(
            json.dumps(data, ensure_ascii=False).encode()
        ).hexdigest()

    result = client.table("faqs").select(
        "id,excel_id,question,answer,category,status,sync_hash"
    ).execute()

    db_rows = result.data or []

    by_id = {str(row["id"]): row for row in db_rows}
    by_excel = {
        str(row["excel_id"]): row
        for row in db_rows
        if row.get("excel_id") is not None
    }

    imported = 0
    exported = 0
    updated_db = 0
    updated_excel = 0
    conflicts = 0
    matched_ids = set()

    now = datetime.now(timezone.utc).isoformat()

    # Excel to Supabase
    for r in range(2, sheet.max_row + 1):

        question = cell_value(r, "question")
        answer = cell_value(r, "answer")
        category = cell_value(r, "category") or "General"

        if not str(question).strip() or not str(answer).strip():
            continue

        excel_id = str(cell_value(r, "id")).strip()
        supabase_id = str(cell_value(r, "supabase_id")).strip()

        db = (
            by_id.get(supabase_id)
            or by_excel.get(excel_id)
        )

        excel_hash = digest(question, answer, category)

        # New Excel FAQ
        if not db:
            inserted = client.table("faqs").insert({
                "question": str(question).strip(),
                "answer": str(answer).strip(),
                "category": str(category).strip(),
                "status": "Active",
                "excel_id": int(excel_id) if excel_id.isdigit() else None,
                "sync_hash": excel_hash,
                "updated_at": now
            }).execute()

            if not inserted.data:
                raise RuntimeError("Could not insert Excel FAQ.")

            db = inserted.data[0]
            imported += 1

        else:
            base_hash = db.get("sync_hash")

            db_hash = digest(
                db.get("question"),
                db.get("answer"),
                db.get("category")
            )

            # First sync: establish a baseline from Supabase
            if not base_hash:
                excel_hash = db_hash
                sheet.cell(r, col("question")).value = db["question"]
                sheet.cell(r, col("answer")).value = db["answer"]
                sheet.cell(r, col("category")).value = db.get("category") or "General"

            # Excel changed, Supabase unchanged
            elif excel_hash != base_hash and db_hash == base_hash:
                client.table("faqs").update({
                    "question": str(question).strip(),
                    "answer": str(answer).strip(),
                    "category": str(category).strip(),
                    "sync_hash": excel_hash,
                    "updated_at": now
                }).eq("id", db["id"]).execute()

                db.update({
                    "question": question,
                    "answer": answer,
                    "category": category,
                    "sync_hash": excel_hash
                })

                updated_db += 1

            # Supabase changed, Excel unchanged
            elif db_hash != base_hash and excel_hash == base_hash:
                sheet.cell(r, col("question")).value = db["question"]
                sheet.cell(r, col("answer")).value = db["answer"]
                sheet.cell(r, col("category")).value = db.get("category") or "General"
                updated_excel += 1

            # Both changed differently
            elif db_hash != base_hash and excel_hash != base_hash and db_hash != excel_hash:
                conflicts += 1
                sheet.cell(r, col("question")).value = db["question"]
                sheet.cell(r, col("answer")).value = db["answer"]
                sheet.cell(r, col("category")).value = db.get("category") or "General"

            final_hash = digest(
                db.get("question"),
                db.get("answer"),
                db.get("category")
            )

            client.table("faqs").update({
                "excel_id": int(excel_id) if excel_id.isdigit() else db.get("excel_id"),
                "sync_hash": final_hash,
                "updated_at": now
            }).eq("id", db["id"]).execute()

        final_hash = digest(
            db.get("question"),
            db.get("answer"),
            db.get("category")
        )

        sheet.cell(r, col("supabase_id")).value = db["id"]
        sheet.cell(r, col("sync_hash")).value = final_hash

        matched_ids.add(str(db["id"]))

    # Supabase to Excel
    for db in db_rows:

        if str(db["id"]) in matched_ids:
            continue

        if db.get("status") == "Inactive":
            continue

        new_excel_id = max(
            [
                int(sheet.cell(i, col("id")).value or 0)
                for i in range(2, sheet.max_row + 1)
                if str(sheet.cell(i, col("id")).value or "").isdigit()
            ] + [0]
        ) + 1

        h = digest(
            db["question"],
            db["answer"],
            db.get("category")
        )

        new_row = {
            "id": new_excel_id,
            "question": db["question"],
            "answer": db["answer"],
            "category": db.get("category") or "General",
            "supabase_id": db["id"],
            "sync_hash": h
        }

        sheet.append([
            new_row.get(name, "") for name in headers
        ])

        client.table("faqs").update({
            "excel_id": new_excel_id,
            "sync_hash": h,
            "updated_at": now
        }).eq("id", db["id"]).execute()

        exported += 1

    # Upload updated Excel workbook
    output = BytesIO()
    wb.save(output)
    wb.close()

    client.storage.from_(bucket).upload(
        path,
        output.getvalue(),
        {
            "upsert": "true",
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
    )

    return {
        "message": "Excel and Supabase sync finished.",
        "excel_to_supabase": imported + updated_db,
        "supabase_to_excel": exported + updated_excel,
        "conflicts": conflicts,
        "storage_file": path
    }
    
