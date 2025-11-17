import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import smtplib
from email.message import EmailMessage

from database import create_document, get_documents, db
from schemas import Lead

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hesham Hamdy Media Buying Course API"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


def _smtp_configured() -> bool:
    return all([
        os.getenv("SMTP_HOST"),
        os.getenv("SMTP_PORT"),
        os.getenv("EMAIL_FROM"),
        os.getenv("EMAIL_TO"),
    ])


def _send_email(subject: str, body: str, to_email: str):
    """Best-effort email sending. If SMTP is not configured, no-op."""
    if not os.getenv("SMTP_HOST"):
        # Not configured; silently skip
        return

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    sender = os.getenv("EMAIL_FROM")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    except Exception:
        # Fail silently to not block lead creation
        pass


# Lead creation
@app.post("/api/leads")
def create_lead(lead: Lead):
    try:
        lead_id = create_document("lead", lead)

        # Send notification email to admin (if configured)
        if _smtp_configured():
            admin_to = os.getenv("EMAIL_TO")
            subject_admin = f"New Lead: {lead.name}"
            body_admin = (
                f"New lead submitted for 1:1 Media Buying Program\n\n"
                f"Name: {lead.name}\n"
                f"Email: {lead.email}\n"
                f"Phone: {lead.phone or '-'}\n"
                f"Experience: {lead.experience_level or '-'}\n"
                f"Goals: {lead.goals or '-'}\n"
                f"Platforms: {', '.join(lead.platforms or []) or '-'}\n"
                f"Timezone: {lead.timezone or '-'}\n"
                f"Preferred Times: {', '.join(lead.preferred_times or []) or '-'}\n"
                f"Consent: {'Yes' if lead.consent else 'No'}\n"
                f"ID: {lead_id}\n"
            )
            _send_email(subject_admin, body_admin, admin_to)

            # Confirmation to applicant
            subject_user = "Thanks for applying — Hesham Hamdy 1:1 Program"
            body_user = (
                f"Hi {lead.name},\n\n"
                "Thanks for applying to the one-to-one Media Buying program. "
                "I've received your details and will get back to you shortly to schedule the first session.\n\n"
                f"Your selections:\n- Experience: {lead.experience_level or '-'}\n- Platforms: {', '.join(lead.platforms or []) or '-'}\n- Preferred Times: {', '.join(lead.preferred_times or []) or '-'}\n- Timezone: {lead.timezone or '-'}\n\n"
                "If you need to update anything, just reply to this email.\n\n— Hesham"
            )
            _send_email(subject_user, body_user, lead.email)

        return {"ok": True, "id": lead_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Admin-protected list leads
@app.get("/api/leads")
def list_leads(limit: int = 50, x_admin_key: Optional[str] = Header(default=None)):
    try:
        admin_key_env = os.getenv("ADMIN_KEY")
        if admin_key_env:
            if x_admin_key != admin_key_env:
                raise HTTPException(status_code=401, detail="Unauthorized")
        # if no ADMIN_KEY set, allow for development convenience

        docs = get_documents("lead", {}, limit)
        # Convert ObjectId to string
        for d in docs:
            if "_id" in d:
                d["id"] = str(d.pop("_id"))
        # Sort by created_at desc if present
        try:
            docs.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        except Exception:
            pass
        return {"ok": True, "results": docs}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
