import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from starlette.middleware.sessions import SessionMiddleware

from excel_store import ensure_workbooks, read_users, write_users, read_faqs, add_faq, read_queries, read_announcements, add_query, update_query_status

load_dotenv()

PORT = int(os.getenv("PORT", "8000"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5500")
ALLOWED_FRONTEND_ORIGINS = list(dict.fromkeys([FRONTEND_URL, "http://localhost:5500", "http://127.0.0.1:5500"]))
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-change-this-secret")
password_hash = PasswordHash.recommended()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_workbooks()
    yield


app = FastAPI(
    title="Salesforce-style Backend API",
    description="Demo backend with login, registration, and Excel-based FAQs.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="salesforce_session",
    same_site="lax",
    https_only=os.getenv("NODE_ENV") == "production",
    max_age=60 * 60 * 8,
)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class FAQCreateRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    answer: str = Field(min_length=2, max_length=5000)
    category: str = Field(default="General", max_length=100)


class QueryStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=30)


class QueryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    message: str = Field(min_length=5, max_length=3000)
    phone: str = Field(default="", max_length=30)


def public_user(user: dict) -> dict:
    return {
        "id": int(user["id"]),
        "name": str(user["name"]),
        "email": str(user["email"]),
        "role": str(user.get("role", "user")),
    }


def current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="You are not logged in.")
    return user


@app.get("/")
def root():
    return {"message": "Salesforce-style FastAPI backend is running", "status": "ok"}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest, request: Request):
    name = payload.name.strip()
    email = str(payload.email).strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")

    users = read_users()
    if any(str(user.get("email", "")).lower() == email for user in users):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    next_id = max((int(user.get("id", 0) or 0) for user in users), default=0) + 1
    user = {
        "id": next_id,
        "name": name,
        "email": email,
        "passwordHash": password_hash.hash(payload.password),
        "role": "user",
    }
    users.append(user)
    write_users(users)

    request.session.clear()
    request.session["user"] = public_user(user)
    return {"message": "Registration successful.", "user": public_user(user)}


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request):
    email = str(payload.email).strip().lower()
    user = next(
        (item for item in read_users() if str(item.get("email", "")).lower() == email),
        None,
    )
    stored_hash = str(user.get("passwordHash", "")) if user else ""
    if not user or not stored_hash or not password_hash.verify(payload.password, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    request.session.clear()
    request.session["user"] = public_user(user)
    return {"message": "Login successful.", "user": public_user(user)}


@app.get("/api/auth/me")
def me(request: Request):
    return {"user": current_user(request)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    request.session.clear()
    response.delete_cookie("salesforce_session", httponly=True, samesite="lax")
    return {"message": "Logged out successfully."}


@app.get("/api/faqs")
def get_faqs(
    category: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
):
    faqs = read_faqs()
    if category:
        faqs = [
            faq for faq in faqs
            if str(faq.get("category", "")).lower() == category.strip().lower()
        ]
    if search:
        term = search.strip().lower()
        faqs = [
            faq for faq in faqs
            if term in str(faq.get("question", "")).lower()
            or term in str(faq.get("answer", "")).lower()
        ]
    return faqs


@app.post("/api/faqs", status_code=201)
def create_faq(payload: FAQCreateRequest):
    """Add an FAQ row to the FAQs sheet in data/college_data.xlsx."""
    question = payload.question.strip()
    answer = payload.answer.strip()
    if not question or not answer:
        raise HTTPException(status_code=400, detail="Question and answer are required.")
    existing = read_faqs()
    if any(str(item.get("question", "")).strip().lower() == question.lower() for item in existing):
        raise HTTPException(status_code=409, detail="That FAQ question already exists.")
    return add_faq(question, answer, payload.category)


@app.get("/api/queries")
def get_queries():
    return read_queries()


@app.patch("/api/queries/{query_id}/status")
def set_query_status(query_id: int, payload: QueryStatusUpdateRequest):
    """Update a support query status in the Excel workbook (demo admin endpoint)."""
    allowed_statuses = {"Open", "In Progress", "Resolved"}
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Status must be Open, In Progress, or Resolved.")
    try:
        updated = update_query_status(query_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if updated is None:
        raise HTTPException(status_code=404, detail="Support query not found.")
    return {"message": "Query status updated.", "query": updated}


@app.post("/api/queries", status_code=201)
def create_query(payload: QueryCreateRequest):
    """Save a support request to the Queries sheet in college_data.xlsx."""
    name = payload.name.strip()
    message = payload.message.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    if len(message) < 5:
        raise HTTPException(status_code=400, detail="Please provide more detail about your issue.")
    return {"message": "Your support query was submitted successfully.", "query": add_query(name, str(payload.email), message, payload.phone)}


@app.get("/api/announcements")
def get_announcements():
    return read_announcements()


@app.get("/api/faqs/{faq_id}")
def get_faq(faq_id: int):
    faq = next((item for item in read_faqs() if str(item.get("id")) == str(faq_id)), None)
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    return faq
