import os
import re
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient

app = FastAPI(title="Level 04 : The Last Login Tournament Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is not set.")

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY")
if not ADMIN_SECRET_KEY:
    raise RuntimeError("ADMIN_SECRET_KEY environment variable is not set.")

client = AsyncIOMotorClient(MONGO_URI)
db = client["nexus_event_db"]
teams_col = db["teams"]
submissions_col = db["submissions"]
questions_col = db["round_questions"]
round_state_col = db["round_state"]
sessions_col = db["sessions"]
system_config_col = db["system_config"]
pending_registrations_col = db["pending_registrations"]

# ---------- Static file serving ----------

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)

@app.get("/retro", response_class=HTMLResponse)
@app.get("/index-retro.html", response_class=HTMLResponse)
async def serve_retro():
    if os.path.exists("index-retro.html"):
        return FileResponse("index-retro.html")
    return HTMLResponse("<h1>index-retro.html not found</h1>", status_code=404)

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin.html", response_class=HTMLResponse)
async def serve_admin():
    if os.path.exists("admin.html"):
        return FileResponse("admin.html")
    return HTMLResponse("<h1>admin.html not found</h1>", status_code=404)

@app.get("/admin-retro", response_class=HTMLResponse)
@app.get("/admin-retro.html", response_class=HTMLResponse)
async def serve_admin_retro():
    if os.path.exists("admin-retro.html"):
        return FileResponse("admin-retro.html")
    return HTMLResponse("<h1>admin-retro.html not found</h1>", status_code=404)

@app.get("/leaderboard", response_class=HTMLResponse)
@app.get("/leaderboard.html", response_class=HTMLResponse)
async def serve_leaderboard():
    if os.path.exists("leaderboard.html"):
        return FileResponse("leaderboard.html")
    return HTMLResponse("<h1>leaderboard.html not found</h1>", status_code=404)

@app.get("/leaderboard-retro", response_class=HTMLResponse)
@app.get("/leaderboard-retro.html", response_class=HTMLResponse)
async def serve_leaderboard_retro():
    if os.path.exists("leaderboard-retro.html"):
        return FileResponse("leaderboard-retro.html")
    return HTMLResponse("<h1>leaderboard-retro.html not found</h1>", status_code=404)

@app.get("/invite", response_class=HTMLResponse)
@app.get("/invite.html", response_class=HTMLResponse)
async def serve_invite():
    if os.path.exists("invite.html"):
        return FileResponse("invite.html")
    return HTMLResponse("<h1>invite.html not found</h1>", status_code=404)

@app.get("/invite_1", response_class=HTMLResponse)
@app.get("/invite_1.html", response_class=HTMLResponse)
async def serve_invite_1():
    if os.path.exists("invite_1.html"):
        return FileResponse("invite_1.html")
    return HTMLResponse("<h1>invite_1.html not found</h1>", status_code=404)

@app.get("/register", response_class=HTMLResponse)
@app.get("/register.html", response_class=HTMLResponse)
async def serve_register():
    if os.path.exists("register.html"):
        return FileResponse("register.html")
    return HTMLResponse("<h1>register.html not found</h1>", status_code=404)

@app.get("/pending", response_class=HTMLResponse)
@app.get("/pending.html", response_class=HTMLResponse)
async def serve_pending():
    if os.path.exists("pending.html"):
        return FileResponse("pending.html")
    return HTMLResponse("<h1>pending.html not found</h1>", status_code=404)

# ---------- Pydantic models ----------

class TeamMemberModel(BaseModel):
    name: str
    roll_no: str
    course: str = "B.Tech"
    year: str

class PublicRegistrationRequest(BaseModel):
    team_name: str
    leader_name: str
    leader_phone: str
    leader_roll: str
    course: str = "B.Tech"
    year: str
    members: List[TeamMemberModel] = []
    payer_name: str
    transaction_ref: Optional[str] = ""
    payment_screenshot: Optional[str] = ""  # base64 data URL of payment receipt

class QuestionModel(BaseModel):
    id: str
    type: str
    text: str
    options: Optional[List[Dict[str, str]]] = None
    correct_answer: str
    points: Optional[int] = None

class HintModel(BaseModel):
    tier: int
    point_cost: int
    text: str

class SaveRoundQuestionsRequest(BaseModel):
    round_number: int
    questions: List[QuestionModel]
    hints: List[HintModel] = []
    briefing: str = ""

class CreateTeamsBulkRequest(BaseModel):
    team_names: List[str]

class LoginRequest(BaseModel):
    team_id: str
    password: str

class LogoutRequest(BaseModel):
    team_id: str
    password: str

class SessionProgressRequest(BaseModel):
    team_id: str
    password: str
    round_number: int
    current_index: int
    answers: Dict[str, Any]
    tab_switch_count: int
    warned: bool = False

class HintRequestModel(BaseModel):
    team_id: str
    password: str
    round_number: int
    tier: int

class SubmitQuizRequest(BaseModel):
    team_id: str
    password: str
    round_number: int
    answers: Dict[str, Any]
    tab_switch_count: int
    time_taken_seconds: int
    submission_status: str

class PromoteTeamsRequest(BaseModel):
    top_n_teams: int
    next_round: int

class OpenRoundRequest(BaseModel):
    duration_minutes: Optional[int] = 10

class UniversalResetRequest(BaseModel):
    reset_type: str
    round_number: Optional[int] = 1

class StatusCheckRequest(BaseModel):
    claim_token: str

# ---------- Utilities ----------

def generate_random_password(length=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def generate_claim_token():
    return "NX-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))

def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(text).lower())

def is_answer_correct(user_ans: str, correct_ans: str) -> bool:
    u = str(user_ans).strip()
    c = str(correct_ans).strip()
    if u.upper() == c.upper():
        return True
    norm_u = normalize_text(u)
    norm_c = normalize_text(c)
    if norm_u and norm_u == norm_c:
        return True
    norm_u_no_zeros = re.sub(r'\b0+(\d+)', r'\1', norm_u)
    norm_c_no_zeros = re.sub(r'\b0+(\d+)', r'\1', norm_c)
    return bool(norm_u_no_zeros and norm_u_no_zeros == norm_c_no_zeros)

def serialize_round_state(doc):
    if not doc:
        return {"is_open": False, "opened_at": None, "duration_minutes": 10, "expires_at": None, "remaining_seconds": 0}
    opened_at = doc.get("opened_at")
    duration = doc.get("duration_minutes", 10)
    is_open = doc.get("is_open", False)
    expires_at = None
    remaining_seconds = 0
    if opened_at and is_open:
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        exp = opened_at + timedelta(minutes=duration)
        expires_at = exp.isoformat()
        now = datetime.now(timezone.utc)
        remaining_seconds = max(0, int((exp - now).total_seconds()))
        if remaining_seconds <= 0:
            is_open = False
    return {
        "is_open": is_open,
        "opened_at": opened_at.isoformat() if opened_at else None,
        "duration_minutes": duration,
        "expires_at": expires_at,
        "remaining_seconds": remaining_seconds
    }

async def assert_round_open(round_number: int):
    doc = await round_state_col.find_one({"round_number": round_number})
    status = serialize_round_state(doc)
    if not status["is_open"]:
        if doc and doc.get("is_open"):
            await round_state_col.update_one(
                {"round_number": round_number},
                {"$set": {"is_open": False}}
            )
        raise HTTPException(status_code=423, detail=f"Round {round_number} is LOCKED.")
    return status

async def check_and_auto_close_round(round_number: int):
    round_doc = await round_state_col.find_one({"round_number": round_number})
    if not round_doc or not round_doc.get("is_open"):
        return
    total_eligible = await teams_col.count_documents({
        "status": "QUALIFIED",
        "current_round": round_number,
        "has_logged_in": True
    })
    if total_eligible == 0:
        return
    total_submitted = await submissions_col.count_documents({"round_number": round_number})
    if total_submitted >= total_eligible:
        await round_state_col.update_one(
            {"round_number": round_number},
            {"$set": {"is_open": False, "auto_closed_at": datetime.now(timezone.utc)}}
        )

async def authenticate_team(team_id: str, password: str):
    team = await teams_col.find_one({
        "team_id": team_id.strip().upper(),
        "password": password.strip().upper()
    })
    if not team:
        raise HTTPException(status_code=401, detail="Authentication failed.")
    return team

# ---------- Public leaderboard ----------

@app.get("/api/public/active-round")
async def get_active_round():
    for r in range(1, 5):
        doc = await round_state_col.find_one({"round_number": r})
        if doc and doc.get("is_open"):
            return {"active_round": r, "is_open": True}
    return {"active_round": 1, "is_open": False}

@app.get("/api/public/leaderboard/{round_number}")
async def get_public_leaderboard(round_number: int):
    try:
        cursor = submissions_col.find({"round_number": round_number}).sort([
            ("score", -1), ("time_taken_seconds", 1), ("tab_switch_count", 1)
        ])
        submissions = await cursor.to_list(length=500)
        leaderboard = []
        for rank, sub in enumerate(submissions, start=1):
            team_info = await teams_col.find_one({"team_id": sub.get("team_id")})
            hints = sub.get("hints_used") or []
            leaderboard.append({
                "rank": rank,
                "team_id": sub.get("team_id", ""),
                "team_name": team_info.get("team_name", "Unknown") if team_info else "Unknown",
                "score": sub.get("score", 0),
                "time_taken_seconds": sub.get("time_taken_seconds", 0),
                "tab_switch_count": sub.get("tab_switch_count", 0),
                "hints_used": hints,
                "hints_used_count": len(hints) if isinstance(hints, list) else 0,
                "submission_status": sub.get("submission_status", "NORMAL_COMPLETION"),
                "status": team_info.get("status", "QUALIFIED") if team_info else "UNKNOWN",
                "elimination_reason": team_info.get("elimination_reason", "") if team_info else ""
            })
        round_doc = await round_state_col.find_one({"round_number": round_number})
        round_status = serialize_round_state(round_doc)
        total_reg = await teams_col.count_documents({
            "status": "QUALIFIED", "current_round": round_number, "has_logged_in": True
        })
        return {
            "status": "success",
            "round": round_number,
            "is_open": round_status["is_open"],
            "remaining_seconds": round_status["remaining_seconds"],
            "total_registered": total_reg,
            "total_submitted": len(submissions),
            "leaderboard": leaderboard
        }
    except Exception as e:
        return {
            "status": "error", "round": round_number, "is_open": False,
            "remaining_seconds": 0, "total_registered": 0, "total_submitted": 0,
            "leaderboard": [], "error_detail": str(e)
        }

# ---------- Public registration (Claim Key) ----------

@app.post("/api/public/register")
async def public_register_team(payload: PublicRegistrationRequest):
    t_name = payload.team_name.strip()
    l_name = payload.leader_name.strip()
    l_phone = payload.leader_phone.strip()
    l_roll = payload.leader_roll.strip()
    payer = payload.payer_name.strip()
    screenshot = (payload.payment_screenshot or "").strip()

    if not t_name or not l_name or not l_phone or not l_roll or not payer:
        raise HTTPException(status_code=400, detail="Please fill in all required fields.")
    if len(l_phone) != 10 or not l_phone.isdigit():
        raise HTTPException(status_code=400, detail="WhatsApp number must be a valid 10-digit number.")
    if not l_roll.isdigit() or len(l_roll) < 3:
        raise HTTPException(status_code=400, detail="Roll number must be a valid numeric value (at least 3 digits).")
    if len(payload.members) > 2:
        raise HTTPException(status_code=400, detail="A team can have a maximum of 3 participants (Leader + 2 Members).")
    for m in payload.members:
        if not str(m.roll_no).strip().isdigit() or len(str(m.roll_no).strip()) < 3:
            raise HTTPException(status_code=400, detail="All member roll numbers must be valid numeric values.")
    if not screenshot or not screenshot.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Payment receipt screenshot is required (image upload).")
    if len(screenshot) > 3_500_000:
        raise HTTPException(status_code=400, detail="Screenshot too large. Please compress and retry (max ~2.5 MB).")

    existing_pending = await pending_registrations_col.find_one({
        "leader.phone": l_phone, "status": "PENDING"
    })
    if existing_pending:
        raise HTTPException(status_code=400, detail="A pending registration already exists for this phone number.")

    existing_team = await teams_col.find_one({"leader.phone": l_phone})
    if existing_team:
        raise HTTPException(status_code=400, detail="This phone number is already linked to a registered team.")

    claim_token = generate_claim_token()
    while await pending_registrations_col.find_one({"claim_token": claim_token}) or \
          await teams_col.find_one({"claim_token": claim_token}):
        claim_token = generate_claim_token()

    now = datetime.now(timezone.utc)
    course = (payload.course or "").strip() or "Other"
    if len(course) > 60:
        raise HTTPException(status_code=400, detail="Course name is too long.")
    members_clean = []
    for m in payload.members:
        md = m.dict()
        md["course"] = (md.get("course") or course or "Other").strip()
        md["roll_no"] = str(md.get("roll_no", "")).strip()
        members_clean.append(md)

    pending_doc = {
        "team_name": t_name,
        "leader": {
            "name": l_name, "phone": l_phone, "roll_no": l_roll,
            "course": course, "year": payload.year
        },
        "members": members_clean,
        "payment": {
            "payer_name": payer,
            "transaction_ref": payload.transaction_ref or "",
            "amount_inr": 100,
            "status": "SUBMITTED",
            "screenshot": screenshot
        },
        "status": "PENDING",
        "claim_token": claim_token,
        "created_at": now,
        "created_at_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    result = await pending_registrations_col.insert_one(pending_doc)
    return {
        "status": "pending",
        "message": "Registration submitted. Save your Claim Key — you will need it to retrieve credentials after admin approval.",
        "pending_id": str(result.inserted_id),
        "team_name": t_name,
        "phone": l_phone,
        "claim_token": claim_token
    }

@app.post("/api/public/check-status")
async def public_check_status(payload: StatusCheckRequest):
    token = payload.claim_token.strip().upper()
    if not token or len(token) < 6:
        raise HTTPException(status_code=400, detail="Enter a valid Claim Key.")

    team = await teams_col.find_one({"claim_token": token})
    if team:
        return {
            "status": "APPROVED",
            "team_id": team["team_id"],
            "password": team["password"],
            "team_name": team["team_name"],
            "message": "Your registration is approved. Save these credentials."
        }

    pending = await pending_registrations_col.find_one({
        "claim_token": token, "status": "PENDING"
    })
    if pending:
        return {
            "status": "PENDING",
            "team_name": pending["team_name"],
            "submitted_at": pending.get("created_at_local", ""),
            "message": "Still waiting for admin payment verification."
        }

    rejected = await pending_registrations_col.find_one({
        "claim_token": token, "status": "REJECTED"
    })
    if rejected:
        return {
            "status": "REJECTED",
            "team_name": rejected["team_name"],
            "message": rejected.get("rejection_reason", "Registration was not approved.")
        }

    raise HTTPException(status_code=404, detail="No registration found for this Claim Key.")

# ---------- Admin pending review ----------

@app.get("/api/admin/pending-registrations")
async def admin_list_pending(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    cursor = pending_registrations_col.find({"status": "PENDING"}).sort("created_at", -1)
    items = await cursor.to_list(length=500)
    result = []
    for p in items:
        payment = p.get("payment", {}) or {}
        has_ss = bool(payment.get("screenshot"))
        result.append({
            "id": str(p["_id"]),
            "team_name": p.get("team_name", ""),
            "leader_name": p.get("leader", {}).get("name", ""),
            "leader_phone": p.get("leader", {}).get("phone", ""),
            "leader_roll": p.get("leader", {}).get("roll_no", ""),
            "course": p.get("leader", {}).get("course", "B.Tech"),
            "year": p.get("leader", {}).get("year", ""),
            "members": p.get("members", []),
            "payer_name": payment.get("payer_name", ""),
            "transaction_ref": payment.get("transaction_ref", ""),
            "submitted_at": p.get("created_at_local", ""),
            "claim_token": p.get("claim_token", ""),
            "status": p.get("status", "PENDING"),
            "has_screenshot": has_ss
        })
    return {"status": "success", "total": len(result), "pending": result}


@app.get("/api/admin/pending/{pending_id}/screenshot")
async def admin_get_pending_screenshot(pending_id: str, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    from bson import ObjectId
    try:
        oid = ObjectId(pending_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pending ID.")
    pending = await pending_registrations_col.find_one({"_id": oid})
    if not pending:
        raise HTTPException(status_code=404, detail="Pending registration not found.")
    screenshot = (pending.get("payment") or {}).get("screenshot") or ""
    if not screenshot:
        raise HTTPException(status_code=404, detail="No payment screenshot attached.")
    return {"status": "success", "screenshot": screenshot, "team_name": pending.get("team_name", "")}

@app.post("/api/admin/pending/{pending_id}/approve")
async def admin_approve_pending(pending_id: str, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    from bson import ObjectId
    try:
        oid = ObjectId(pending_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pending ID.")
    pending = await pending_registrations_col.find_one({"_id": oid, "status": "PENDING"})
    if not pending:
        raise HTTPException(status_code=404, detail="Pending registration not found or already processed.")

    existing_ids = set()
    async for doc in teams_col.find({}, {"team_id": 1}):
        existing_ids.add(doc["team_id"])

    team_id = f"NEX-{''.join(secrets.choice(string.digits) for _ in range(4))}"
    while team_id in existing_ids:
        team_id = f"NEX-{''.join(secrets.choice(string.digits) for _ in range(4))}"

    password = generate_random_password(6)
    now = datetime.now(timezone.utc)
    team_doc = {
        "team_id": team_id,
        "team_name": pending["team_name"],
        "password": password,
        "current_round": 1,
        "status": "QUALIFIED",
        "elimination_reason": "",
        "has_logged_in": False,
        "leader": pending.get("leader", {}),
        "members": pending.get("members", []),
        "payment": {**pending.get("payment", {}), "status": "VERIFIED", "verified_at": now},
        "registration_type": "PUBLIC_INVITE",
        "claim_token": pending.get("claim_token", ""),
        "created_at": now
    }
    await teams_col.insert_one(team_doc)
    await pending_registrations_col.update_one(
        {"_id": oid},
        {"$set": {
            "status": "APPROVED",
            "approved_at": now,
            "team_id": team_id,
            "password": password
        }}
    )
    leader_phone = (pending.get("leader") or {}).get("phone", "")
    return {
        "status": "success",
        "team_id": team_id,
        "password": password,
        "team_name": pending["team_name"],
        "leader_phone": leader_phone,
        "claim_token": pending.get("claim_token", ""),
        "message": f"Team {team_id} approved and credentials generated."
    }

@app.post("/api/admin/pending/{pending_id}/reject")
async def admin_reject_pending(pending_id: str, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    from bson import ObjectId
    try:
        oid = ObjectId(pending_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pending ID.")
    pending = await pending_registrations_col.find_one({"_id": oid, "status": "PENDING"})
    if not pending:
        raise HTTPException(status_code=404, detail="Pending registration not found or already processed.")
    await pending_registrations_col.update_one(
        {"_id": oid},
        {"$set": {
            "status": "REJECTED",
            "rejection_reason": "Payment not verified / Invalid details",
            "rejected_at": datetime.now(timezone.utc)
        }}
    )
    return {"status": "success", "message": "Registration rejected."}

# ---------- Questions ----------

@app.post("/api/admin/questions")
async def admin_save_questions(payload: SaveRoundQuestionsRequest, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    doc = {
        "round_number": payload.round_number,
        "questions": [q.dict() for q in payload.questions],
        "hints": [h.dict() for h in payload.hints],
        "briefing": payload.briefing,
        "updated_at": datetime.now(timezone.utc)
    }
    await questions_col.update_one({"round_number": payload.round_number}, {"$set": doc}, upsert=True)
    return {"status": "success", "round": payload.round_number,
            "question_count": len(payload.questions), "hint_count": len(payload.hints)}

@app.get("/api/admin/questions/{round_number}")
async def admin_get_questions(round_number: int, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    doc = await questions_col.find_one({"round_number": round_number})
    if not doc:
        return {"round_number": round_number, "questions": [], "hints": [], "briefing": ""}
    doc.pop("_id", None)
    doc.setdefault("hints", [])
    doc.setdefault("briefing", "")
    return doc

@app.get("/api/questions/{round_number}")
async def get_questions_for_round(round_number: int):
    doc = await questions_col.find_one({"round_number": round_number})
    if not doc:
        return {"questions": [], "hints": [], "briefing": ""}
    safe_questions = [{
        "id": q["id"], "type": q["type"], "text": q["text"],
        "options": q.get("options", [])
    } for q in doc.get("questions", [])]
    safe_hints = [
        {"tier": h["tier"], "point_cost": h["point_cost"]}
        for h in sorted(doc.get("hints", []), key=lambda h: h["tier"])
    ]
    return {
        "round_number": round_number,
        "questions": safe_questions,
        "hints": safe_hints,
        "briefing": doc.get("briefing", "")
    }

# ---------- Round gate ----------

@app.get("/api/round/{round_number}/status")
async def get_round_status(round_number: int):
    doc = await round_state_col.find_one({"round_number": round_number})
    return {"round_number": round_number, **serialize_round_state(doc)}

@app.post("/api/admin/round/{round_number}/open")
async def admin_open_round(round_number: int, payload: OpenRoundRequest = None, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    duration = payload.duration_minutes if payload and payload.duration_minutes else 10
    opened_at = datetime.now(timezone.utc)
    await round_state_col.update_many({"round_number": {"$ne": round_number}}, {"$set": {"is_open": False}})
    if round_number == 1:
        await system_config_col.update_one(
            {"config_id": "main"}, {"$set": {"r1_started": True}}, upsert=True
        )
    await round_state_col.update_one(
        {"round_number": round_number},
        {"$set": {
            "round_number": round_number, "is_open": True,
            "duration_minutes": duration, "opened_at": opened_at
        }},
        upsert=True
    )
    doc = await round_state_col.find_one({"round_number": round_number})
    return {"status": "success", "round_number": round_number, **serialize_round_state(doc)}

@app.post("/api/admin/round/{round_number}/close")
async def admin_close_round(round_number: int, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    await round_state_col.update_one(
        {"round_number": round_number},
        {"$set": {"round_number": round_number, "is_open": False}},
        upsert=True
    )
    return {"status": "success", "round_number": round_number, "is_open": False}

@app.post("/api/admin/round/{round_number}/force-submit")
async def admin_force_submit_round(round_number: int, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    doc = await questions_col.find_one({"round_number": round_number})
    if not doc:
        raise HTTPException(status_code=400, detail="Round questions missing.")

    hint_cost_map = {h["tier"]: h["point_cost"] for h in doc.get("hints", [])}
    now = datetime.now(timezone.utc)

    cursor = teams_col.find({
        "status": "QUALIFIED",
        "current_round": round_number,
        "has_logged_in": True
    })
    teams = await cursor.to_list(length=1000)

    forced_count = 0
    for team in teams:
        existing_sub = await submissions_col.find_one({
            "team_id": team["team_id"], "round_number": round_number
        })
        if existing_sub:
            continue

        session = await sessions_col.find_one({
            "team_id": team["team_id"], "round_number": round_number
        })
        answers = session.get("answers", {}) if session else {}
        tab_switch_count = session.get("tab_switch_count", 0) if session else 0
        hints_used = session.get("hints_used", []) if session else []

        score = 0
        detailed_results = {}
        for q in doc.get("questions", []):
            q_id = q["id"]
            correct_ans = q.get("correct_answer", "")
            user_ans = str(answers.get(q_id, "")).strip()
            q_points = q.get("points") or 4
            is_correct = is_answer_correct(user_ans, correct_ans) if user_ans else False
            if is_correct:
                score += q_points
            detailed_results[q_id] = {
                "user_answer": user_ans, "correct_answer": correct_ans,
                "is_correct": is_correct, "points_available": q_points
            }

        hint_penalty = sum(hint_cost_map.get(t, 0) for t in hints_used)
        score = max(0, score - hint_penalty)

        round_doc = await round_state_col.find_one({"round_number": round_number})
        if round_doc and round_doc.get("opened_at"):
            opened_at = round_doc["opened_at"]
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=timezone.utc)
            server_time_taken = max(0, int((now - opened_at).total_seconds()))
        else:
            server_time_taken = 0

        record = {
            "team_id": team["team_id"],
            "round_number": round_number,
            "score": score,
            "max_score": sum((q.get("points") or 4) for q in doc.get("questions", [])),
            "hint_penalty": hint_penalty,
            "hints_used": hints_used,
            "time_taken_seconds": server_time_taken,
            "client_reported_time_seconds": server_time_taken,
            "tab_switch_count": tab_switch_count,
            "submission_status": "ADMIN_FORCE_SUBMITTED",
            "detailed_results": detailed_results,
            "submitted_at_utc": now,
            "submitted_at_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        await submissions_col.insert_one(record)
        await sessions_col.update_one(
            {"team_id": team["team_id"], "round_number": round_number},
            {"$set": {"status": "SUBMITTED", "last_updated_at": now}},
            upsert=True
        )
        forced_count += 1

    await round_state_col.update_one(
        {"round_number": round_number},
        {"$set": {"round_number": round_number, "is_open": False, "auto_closed_at": now}},
        upsert=True
    )
    return {"status": "success", "round_number": round_number, "force_submitted_count": forced_count}

@app.post("/api/admin/team/{team_id}/revive")
async def admin_revive_team(team_id: str, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    team = await teams_col.find_one({"team_id": team_id.strip().upper()})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    current_round = team.get("current_round", 1)
    await submissions_col.delete_many({"team_id": team["team_id"], "round_number": current_round})
    await sessions_col.delete_many({"team_id": team["team_id"], "round_number": current_round})
    await teams_col.update_one(
        {"team_id": team["team_id"]},
        {"$set": {"status": "QUALIFIED", "elimination_reason": "", "has_logged_in": False}}
    )
    return {"status": "success", "team_id": team["team_id"], "current_round": current_round,
            "message": "Team revived / force-unlocked."}

# ---------- Bulk + analytics ----------

@app.post("/api/admin/create-teams-bulk")
async def admin_create_teams_bulk(payload: CreateTeamsBulkRequest, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    names = [n.strip() for n in payload.team_names if n.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="No valid team names provided.")
    existing_ids = set()
    async for doc in teams_col.find({}, {"team_id": 1}):
        existing_ids.add(doc["team_id"])
    created, new_docs = [], []
    for t_name in names:
        team_id = f"NEX-{''.join(secrets.choice(string.digits) for _ in range(4))}"
        while team_id in existing_ids:
            team_id = f"NEX-{''.join(secrets.choice(string.digits) for _ in range(4))}"
        existing_ids.add(team_id)
        password = generate_random_password(6)
        new_docs.append({
            "team_id": team_id, "team_name": t_name, "password": password,
            "current_round": 1, "status": "QUALIFIED", "elimination_reason": "",
            "has_logged_in": False, "created_at": datetime.now(timezone.utc)
        })
        created.append({"team_id": team_id, "team_name": t_name, "password": password})
    if new_docs:
        await teams_col.insert_many(new_docs)
    return {"status": "success", "created_count": len(created), "teams": created}

@app.get("/api/admin/analytics")
async def admin_get_analytics(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    total_teams = await teams_col.count_documents({})
    logged_in_teams = await teams_col.count_documents({"has_logged_in": True})
    rounds_data = {}
    for r in range(1, 5):
        qualified = await teams_col.count_documents({"status": "QUALIFIED", "current_round": r})
        eliminated = await teams_col.count_documents({"status": "ELIMINATED", "current_round": r})
        submitted = await submissions_col.count_documents({"round_number": r})
        rounds_data[f"round_{r}"] = {"qualified": qualified, "eliminated": eliminated, "submitted": submitted}
    sys_conf = await system_config_col.find_one({"config_id": "main"}) or {}
    pending_count = await pending_registrations_col.count_documents({"status": "PENDING"})
    return {
        "status": "success",
        "total_teams_generated": total_teams,
        "total_authenticated_logins": logged_in_teams,
        "round_metrics": rounds_data,
        "r1_started": sys_conf.get("r1_started", False),
        "allow_late_logins": sys_conf.get("allow_late_logins", False),
        "pending_registrations": pending_count
    }

@app.post("/api/admin/toggle-late-logins")
async def admin_toggle_late_logins(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    conf = await system_config_col.find_one({"config_id": "main"}) or {}
    new_state = not conf.get("allow_late_logins", False)
    await system_config_col.update_one(
        {"config_id": "main"}, {"$set": {"allow_late_logins": new_state}}, upsert=True
    )
    return {"status": "success", "allow_late_logins": new_state}

# ---------- Universal reset ----------

@app.post("/api/admin/universal-reset")
async def admin_universal_reset(payload: UniversalResetRequest, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    reset_type = payload.reset_type
    if reset_type == "teams_only":
        await teams_col.delete_many({})
        await sessions_col.delete_many({})
        await submissions_col.delete_many({})
        await system_config_col.delete_many({})
        return {"status": "success", "message": "All teams and credentials removed."}
    elif reset_type == "leaderboard_only":
        await submissions_col.delete_many({})
        await sessions_col.delete_many({})
        await teams_col.update_many({}, {
            "$set": {"has_logged_in": False, "status": "QUALIFIED", "elimination_reason": ""}
        })
        return {"status": "success", "message": "Submissions cleared."}
    elif reset_type == "current_round_only":
        r = payload.round_number or 1
        await submissions_col.delete_many({"round_number": r})
        await sessions_col.delete_many({"round_number": r})
        await round_state_col.update_one({"round_number": r}, {"$set": {"is_open": False}}, upsert=True)
        await teams_col.update_many({"current_round": r}, {
            "$set": {"status": "QUALIFIED", "has_logged_in": False, "elimination_reason": ""}
        })
        return {"status": "success", "message": f"Round {r} logs reset."}
    elif reset_type == "full_reset_keep_questions":
        await submissions_col.delete_many({})
        await sessions_col.delete_many({})
        await teams_col.update_many({}, {
            "$set": {"current_round": 1, "status": "QUALIFIED",
                     "has_logged_in": False, "elimination_reason": ""}
        })
        await round_state_col.update_many({}, {"$set": {"is_open": False}})
        await system_config_col.update_one(
            {"config_id": "main"},
            {"$set": {"r1_started": False, "allow_late_logins": False}},
            upsert=True
        )
        return {"status": "success", "message": "Full tournament reset completed."}
    raise HTTPException(status_code=400, detail="Invalid reset type.")

# ---------- Auth ----------

@app.post("/api/auth/login")
async def participant_login(payload: LoginRequest):
    team = await teams_col.find_one({
        "team_id": payload.team_id.strip().upper(),
        "password": payload.password.strip().upper()
    })
    if not team:
        raise HTTPException(status_code=401, detail="Invalid Team ID or Access Password.")
    if team.get("status") == "ELIMINATED":
        elim_reason = team.get("elimination_reason", "Disqualification / Cutoff")
        raise HTTPException(status_code=403, detail=f"Notice: Your team has been eliminated ({elim_reason}).")

    current_round = team.get("current_round", 1)
    sys_conf = await system_config_col.find_one({"config_id": "main"}) or {}
    if (current_round == 1 and sys_conf.get("r1_started")
            and not sys_conf.get("allow_late_logins") and not team.get("has_logged_in")):
        raise HTTPException(status_code=403, detail="Late registrations are currently locked by the administrator.")

    existing_sub = await submissions_col.find_one({
        "team_id": team["team_id"], "round_number": current_round
    })
    if existing_sub:
        raise HTTPException(status_code=400, detail=f"Already submitted Round {current_round}. Stand by for promotion.")

    await teams_col.update_one(
        {"team_id": team["team_id"]},
        {"$set": {"has_logged_in": True, "last_login": datetime.now(timezone.utc)}}
    )

    round_doc = await round_state_col.find_one({"round_number": current_round})
    round_status = serialize_round_state(round_doc)
    if not round_status["is_open"]:
        raise HTTPException(status_code=423, detail=f"Round {current_round} is currently LOCKED by admin.")

    session = await sessions_col.find_one({"team_id": team["team_id"], "round_number": current_round})
    if session and session.get("status") == "ACTIVE":
        resume = {
            "current_index": session.get("current_index", 0),
            "answers": session.get("answers", {}),
            "tab_switch_count": session.get("tab_switch_count", 0),
            "warned": session.get("warned", False),
            "hints_used": session.get("hints_used", []),
            "resumed": True
        }
    else:
        await sessions_col.update_one(
            {"team_id": team["team_id"], "round_number": current_round},
            {"$set": {
                "team_id": team["team_id"], "round_number": current_round,
                "current_index": 0, "answers": {}, "tab_switch_count": 0,
                "warned": False, "hints_used": [], "status": "ACTIVE",
                "started_at": datetime.now(timezone.utc),
                "last_updated_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        resume = {"current_index": 0, "answers": {}, "tab_switch_count": 0,
                  "warned": False, "hints_used": [], "resumed": False}

    return {
        "status": "success",
        "team_id": team["team_id"],
        "team_name": team["team_name"],
        "current_round": current_round,
        "round_opened_at": round_status["opened_at"],
        "round_remaining_seconds": round_status["remaining_seconds"],
        "round_duration_minutes": round_status["duration_minutes"],
        "resume": resume
    }

@app.post("/api/auth/logout")
async def participant_logout(payload: LogoutRequest):
    team = await authenticate_team(payload.team_id, payload.password)
    await teams_col.update_one({"team_id": team["team_id"]}, {"$set": {"has_logged_in": False}})
    return {"status": "success"}

# ---------- Submit / Progress / Hint ----------

@app.post("/api/submit-quiz")
async def submit_quiz(payload: SubmitQuizRequest):
    team = await authenticate_team(payload.team_id, payload.password)
    await assert_round_open(payload.round_number)

    existing_sub = await submissions_col.find_one({
        "team_id": team["team_id"], "round_number": payload.round_number
    })
    if existing_sub:
        raise HTTPException(status_code=400, detail="Round already submitted.")

    doc = await questions_col.find_one({"round_number": payload.round_number})
    if not doc:
        raise HTTPException(status_code=400, detail="Round questions missing.")

    score = 0
    detailed_results = {}
    for q in doc.get("questions", []):
        q_id = q["id"]
        correct_ans = q.get("correct_answer", "")
        user_ans = str(payload.answers.get(q_id, "")).strip()
        q_points = q.get("points") or 4
        is_correct = is_answer_correct(user_ans, correct_ans)
        if is_correct:
            score += q_points
        detailed_results[q_id] = {
            "user_answer": user_ans, "correct_answer": correct_ans,
            "is_correct": is_correct, "points_available": q_points
        }

    session = await sessions_col.find_one({
        "team_id": team["team_id"], "round_number": payload.round_number
    })
    hints_used = session.get("hints_used", []) if session else []
    hint_cost_map = {h["tier"]: h["point_cost"] for h in doc.get("hints", [])}
    hint_penalty = sum(hint_cost_map.get(t, 0) for t in hints_used)
    score = max(0, score - hint_penalty)

    if payload.submission_status in ["DISQUALIFIED", "TERMINATED_DUE_TO_TAB_SWITCHING"]:
        await teams_col.update_one(
            {"team_id": team["team_id"]},
            {"$set": {"status": "ELIMINATED", "elimination_reason": payload.submission_status}}
        )

    round_doc = await round_state_col.find_one({"round_number": payload.round_number})
    now = datetime.now(timezone.utc)
    if round_doc and round_doc.get("opened_at"):
        opened_at = round_doc["opened_at"]
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        server_time_taken = max(0, int((now - opened_at).total_seconds()))
    else:
        server_time_taken = payload.time_taken_seconds

    record = {
        "team_id": team["team_id"],
        "round_number": payload.round_number,
        "score": score,
        "max_score": sum((q.get("points") or 4) for q in doc.get("questions", [])),
        "hint_penalty": hint_penalty,
        "hints_used": hints_used,
        "time_taken_seconds": server_time_taken,
        "client_reported_time_seconds": payload.time_taken_seconds,
        "tab_switch_count": payload.tab_switch_count,
        "submission_status": payload.submission_status,
        "detailed_results": detailed_results,
        "submitted_at_utc": now,
        "submitted_at_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    await submissions_col.insert_one(record)
    await sessions_col.update_one(
        {"team_id": team["team_id"], "round_number": payload.round_number},
        {"$set": {"status": "SUBMITTED", "last_updated_at": now}}
    )
    await check_and_auto_close_round(payload.round_number)
    return {"status": "success", "score": score, "hint_penalty": hint_penalty, "team_id": team["team_id"]}

@app.post("/api/session/progress")
async def save_session_progress(payload: SessionProgressRequest):
    team = await authenticate_team(payload.team_id, payload.password)
    await assert_round_open(payload.round_number)
    await sessions_col.update_one(
        {"team_id": team["team_id"], "round_number": payload.round_number},
        {"$set": {
            "current_index": payload.current_index,
            "answers": payload.answers,
            "tab_switch_count": payload.tab_switch_count,
            "warned": payload.warned,
            "last_updated_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    return {"status": "success"}

@app.post("/api/hint/request")
async def request_hint(payload: HintRequestModel):
    team = await authenticate_team(payload.team_id, payload.password)
    await assert_round_open(payload.round_number)
    doc = await questions_col.find_one({"round_number": payload.round_number})
    if not doc:
        raise HTTPException(status_code=404, detail="Question bank not found.")
    hint = next((h for h in doc.get("hints", []) if h["tier"] == payload.tier), None)
    if not hint:
        raise HTTPException(status_code=404, detail="Hint tier not found.")
    session = await sessions_col.find_one({
        "team_id": team["team_id"], "round_number": payload.round_number
    })
    hints_used = session.get("hints_used", []) if session else []
    if payload.tier > 1 and (payload.tier - 1) not in hints_used:
        raise HTTPException(status_code=400, detail="Unlock previous hint tier first.")
    if payload.tier not in hints_used:
        hints_used = sorted(hints_used + [payload.tier])
        await sessions_col.update_one(
            {"team_id": team["team_id"], "round_number": payload.round_number},
            {"$set": {"hints_used": hints_used, "last_updated_at": datetime.now(timezone.utc)}},
            upsert=True
        )
    return {"status": "success", "tier": hint["tier"], "point_cost": hint["point_cost"], "text": hint["text"]}

# ---------- Admin leaderboard / teams / promote ----------

@app.get("/api/admin/leaderboard/{round_number}")
async def admin_get_leaderboard(round_number: int, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    cursor = submissions_col.find({"round_number": round_number}).sort([
        ("score", -1), ("time_taken_seconds", 1), ("tab_switch_count", 1)
    ])
    submissions = await cursor.to_list(length=300)
    leaderboard = []
    for rank, sub in enumerate(submissions, start=1):
        team_info = await teams_col.find_one({"team_id": sub.get("team_id")})
        hints = sub.get("hints_used") or []
        leaderboard.append({
            "rank": rank,
            "team_id": sub.get("team_id", ""),
            "team_name": team_info.get("team_name", "Unknown") if team_info else "Unknown",
            "score": sub.get("score", 0),
            "time_taken_seconds": sub.get("time_taken_seconds", 0),
            "tab_switch_count": sub.get("tab_switch_count", 0),
            "hint_penalty": sub.get("hint_penalty", 0),
            "hints_used": hints,
            "hints_used_count": len(hints) if isinstance(hints, list) else 0,
            "submission_status": sub.get("submission_status", "NORMAL_COMPLETION"),
            "status": team_info.get("status", "QUALIFIED") if team_info else "UNKNOWN",
            "elimination_reason": team_info.get("elimination_reason", "") if team_info else "",
            "current_round": team_info.get("current_round", 1) if team_info else 1,
            "submitted_at_local": sub.get("submitted_at_local", "")
        })
    total_registered = await teams_col.count_documents({
        "status": "QUALIFIED", "current_round": round_number, "has_logged_in": True
    })
    return {
        "round": round_number,
        "total_registered": total_registered,
        "active_logins": total_registered,
        "total_submitted": len(submissions),
        "leaderboard": leaderboard
    }

@app.get("/api/admin/teams")
async def admin_list_teams(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    cursor = teams_col.find({}).sort("created_at", 1)
    teams = await cursor.to_list(length=1000)
    result = []
    for t in teams:
        session = await sessions_col.find_one({"team_id": t["team_id"]})
        result.append({
            "team_id": t["team_id"],
            "team_name": t.get("team_name", ""),
            "password": t.get("password", ""),
            "current_round": t.get("current_round", 1),
            "status": t.get("status", "QUALIFIED"),
            "elimination_reason": t.get("elimination_reason", ""),
            "has_logged_in": t.get("has_logged_in", False),
            "session_status": session.get("status", "NOT_STARTED") if session else "NOT_STARTED",
            "leader": t.get("leader", {}),
            "payment": t.get("payment", {}),
            "registration_type": t.get("registration_type", "MANUAL")
        })
    return {"status": "success", "total": len(result), "teams": result}

@app.post("/api/admin/promote-teams")
async def admin_promote_teams(payload: PromoteTeamsRequest, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    prev_round = payload.next_round - 1
    cursor = submissions_col.find({"round_number": prev_round}).sort([
        ("score", -1), ("time_taken_seconds", 1), ("tab_switch_count", 1)
    ])
    ranked_subs = await cursor.to_list(length=300)
    if not ranked_subs:
        raise HTTPException(status_code=400, detail="No submissions found to promote.")
    promoted_count = eliminated_count = 0
    for idx, sub in enumerate(ranked_subs):
        t_id = sub["team_id"]
        if idx < payload.top_n_teams:
            await teams_col.update_one(
                {"team_id": t_id},
                {"$set": {"current_round": payload.next_round, "status": "QUALIFIED",
                          "elimination_reason": "", "has_logged_in": True}}
            )
            promoted_count += 1
        else:
            await teams_col.update_one(
                {"team_id": t_id},
                {"$set": {"status": "ELIMINATED",
                          "elimination_reason": f"Cutoff at Round {prev_round} (Rank #{idx+1})"}}
            )
            eliminated_count += 1
    await round_state_col.update_one(
        {"round_number": payload.next_round},
        {"$set": {"round_number": payload.next_round, "is_open": False}},
        upsert=True
    )
    return {
        "status": "success",
        "promoted_count": promoted_count,
        "eliminated_count": eliminated_count,
        "next_round": payload.next_round
    }

@app.get("/api/team/status/{team_id}")
async def check_team_status(team_id: str):
    team = await teams_col.find_one({"team_id": team_id.strip().upper()})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    current_round = team.get("current_round", 1)
    round_doc = await round_state_col.find_one({"round_number": current_round})
    round_status = serialize_round_state(round_doc)
    return {
        "team_id": team["team_id"],
        "status": team.get("status", "QUALIFIED"),
        "elimination_reason": team.get("elimination_reason", ""),
        "current_round": current_round,
        "round_open": round_status["is_open"],
        "remaining_seconds": round_status["remaining_seconds"]
    }