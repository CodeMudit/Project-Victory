import os
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient

app = FastAPI(title="Project Nexus Tournament Engine")

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

# --- Static File Serving ---

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

# --- Schemas ---

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

def generate_random_password(length=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def normalize_text(text: str) -> str:
    return "".join(text.lower().split())

async def check_and_auto_close_round(round_number: int):
    round_doc = await round_state_col.find_one({"round_number": round_number})
    if not round_doc or not round_doc.get("is_open"):
        return

    logged_in_teams = await teams_col.find({
        "status": "QUALIFIED",
        "current_round": round_number,
        "is_logged_in": True
    }).to_list(length=1000)

    if not logged_in_teams:
        return

    team_ids = [t["team_id"] for t in logged_in_teams]
    submitted_count = await submissions_col.count_documents({
        "round_number": round_number,
        "team_id": {"$in": team_ids}
    })

    if submitted_count >= len(logged_in_teams):
        await round_state_col.update_one(
            {"round_number": round_number},
            {"$set": {"is_open": False, "auto_closed_at": datetime.now(timezone.utc)}}
        )

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
        if remaining_seconds <= 0 and is_open:
            is_open = False

    return {
        "is_open": is_open,
        "opened_at": opened_at.isoformat() if opened_at else None,
        "duration_minutes": duration,
        "expires_at": expires_at,
        "remaining_seconds": remaining_seconds
    }

async def authenticate_team(team_id: str, password: str):
    team = await teams_col.find_one({
        "team_id": team_id.strip().upper(),
        "password": password.strip().upper()
    })
    if not team:
        raise HTTPException(status_code=401, detail="Authentication failed.")
    return team

# --- Question APIS ---

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

    await questions_col.update_one(
        {"round_number": payload.round_number},
        {"$set": doc},
        upsert=True
    )
    return {"status": "success", "round": payload.round_number, "question_count": len(payload.questions), "hint_count": len(payload.hints)}

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

    safe_questions = []
    for q in doc.get("questions", []):
        safe_questions.append({
            "id": q["id"],
            "type": q["type"],
            "text": q["text"],
            "options": q.get("options", [])
        })

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

# --- Gate & Tournament Controls ---

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
            {"config_id": "main"},
            {"$set": {"r1_started": True, "allow_late_logins": False}},
            upsert=True
        )

    await round_state_col.update_one(
        {"round_number": round_number},
        {"$set": {
            "round_number": round_number,
            "is_open": True,
            "duration_minutes": duration,
            "opened_at": opened_at
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

# --- Bulk Creation & Analytics ---

@app.post("/api/admin/create-teams-bulk")
async def admin_create_teams_bulk(payload: CreateTeamsBulkRequest, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")

    names = [n.strip() for n in payload.team_names if n.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="No valid team names provided.")

    existing_ids = set()
    cursor = teams_col.find({}, {"team_id": 1})
    async for doc in cursor:
        existing_ids.add(doc["team_id"])

    created = []
    new_docs = []
    for t_name in names:
        team_id = f"NEX-{''.join(secrets.choice(string.digits) for _ in range(4))}"
        while team_id in existing_ids:
            team_id = f"NEX-{''.join(secrets.choice(string.digits) for _ in range(4))}"
        existing_ids.add(team_id)

        password = generate_random_password(6)
        new_docs.append({
            "team_id": team_id,
            "team_name": t_name,
            "password": password,
            "current_round": 1,
            "status": "QUALIFIED",
            "is_logged_in": False,
            "created_at": datetime.now(timezone.utc)
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
    logged_in_teams = await teams_col.count_documents({"is_logged_in": True})
    
    rounds_data = {}
    for r in range(1, 5):
        qualified = await teams_col.count_documents({"status": "QUALIFIED", "current_round": r})
        eliminated = await teams_col.count_documents({"status": "ELIMINATED", "current_round": r})
        submitted = await submissions_col.count_documents({"round_number": r})
        rounds_data[f"round_{r}"] = {
            "qualified": qualified,
            "eliminated": eliminated,
            "submitted": submitted
        }

    sys_conf = await system_config_col.find_one({"config_id": "main"}) or {}

    return {
        "status": "success",
        "total_teams_generated": total_teams,
        "total_authenticated_logins": logged_in_teams,
        "round_metrics": rounds_data,
        "r1_started": sys_conf.get("r1_started", False),
        "allow_late_logins": sys_conf.get("allow_late_logins", False)
    }

@app.post("/api/admin/toggle-late-logins")
async def admin_toggle_late_logins(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")

    conf = await system_config_col.find_one({"config_id": "main"}) or {}
    curr = conf.get("allow_late_logins", False)
    await system_config_col.update_one(
        {"config_id": "main"},
        {"$set": {"allow_late_logins": not curr}},
        upsert=True
    )
    return {"status": "success", "allow_late_logins": not curr}

# --- Universal Reset ---

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
        return {"status": "success", "message": "All teams deleted."}

    elif reset_type == "leaderboard_only":
        await submissions_col.delete_many({})
        return {"status": "success", "message": "Leaderboard submissions reset."}

    elif reset_type == "current_round_only":
        r = payload.round_number or 1
        await submissions_col.delete_many({"round_number": r})
        await sessions_col.delete_many({"round_number": r})
        await round_state_col.update_one({"round_number": r}, {"$set": {"is_open": False}}, upsert=True)
        await teams_col.update_many({"current_round": r}, {"$set": {"status": "QUALIFIED"}})
        return {"status": "success", "message": f"Round {r} logs reset."}

    elif reset_type == "full_reset_keep_questions":
        await teams_col.delete_many({})
        await submissions_col.delete_many({})
        await sessions_col.delete_many({})
        await round_state_col.update_many({}, {"$set": {"is_open": False}})
        await system_config_col.update_one(
            {"config_id": "main"},
            {"$set": {"r1_started": False, "allow_late_logins": False}},
            upsert=True
        )
        return {"status": "success", "message": "All tournament data reset. Question banks preserved."}

    raise HTTPException(status_code=400, detail="Invalid reset type.")

# --- Participant Login & Session ---

@app.post("/api/auth/login")
async def participant_login(payload: LoginRequest):
    team = await teams_col.find_one({
        "team_id": payload.team_id.strip().upper(),
        "password": payload.password.strip().upper()
    })

    if not team:
        raise HTTPException(status_code=401, detail="Invalid Team ID or Access Password.")

    if team.get("status") == "ELIMINATED":
        raise HTTPException(status_code=403, detail="Notice: Your team has been eliminated.")

    sys_conf = await system_config_col.find_one({"config_id": "main"}) or {}
    if sys_conf.get("r1_started") and not sys_conf.get("allow_late_logins") and not team.get("is_logged_in"):
        raise HTTPException(status_code=403, detail="Late logins are locked by admin.")

    current_round = team.get("current_round", 1)

    existing_sub = await submissions_col.find_one({
        "team_id": team["team_id"],
        "round_number": current_round
    })
    if existing_sub:
        raise HTTPException(status_code=400, detail=f"Already submitted Round {current_round}. Stand by for promotion.")

    round_doc = await round_state_col.find_one({"round_number": current_round})
    round_status = serialize_round_state(round_doc)

    await teams_col.update_one({"team_id": team["team_id"]}, {"$set": {"is_logged_in": True}})

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
                "team_id": team["team_id"],
                "round_number": current_round,
                "current_index": 0,
                "answers": {},
                "tab_switch_count": 0,
                "warned": False,
                "hints_used": [],
                "status": "ACTIVE",
                "started_at": datetime.now(timezone.utc),
                "last_updated_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        resume = {"current_index": 0, "answers": {}, "tab_switch_count": 0, "warned": False, "hints_used": [], "resumed": False}

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
    await teams_col.update_one({"team_id": team["team_id"]}, {"$set": {"is_logged_in": False}})
    return {"status": "success"}

@app.post("/api/admin/team/{team_id}/force-logout")
async def admin_force_logout(team_id: str, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    await teams_col.update_one({"team_id": team_id.upper()}, {"$set": {"is_logged_in": False}})
    return {"status": "success"}

# --- Submissions & Promotes ---

@app.post("/api/submit-quiz")
async def submit_quiz(payload: SubmitQuizRequest):
    team = await authenticate_team(payload.team_id, payload.password)

    existing_sub = await submissions_col.find_one({
        "team_id": team["team_id"],
        "round_number": payload.round_number
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

        is_correct = (
            user_ans.upper() == correct_ans.upper()
            or normalize_text(user_ans) == normalize_text(correct_ans)
        )
        if is_correct:
            score += q_points

        detailed_results[q_id] = {
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "is_correct": is_correct,
            "points_available": q_points
        }

    session = await sessions_col.find_one({"team_id": team["team_id"], "round_number": payload.round_number})
    hints_used = session.get("hints_used", []) if session else []
    hint_cost_map = {h["tier"]: h["point_cost"] for h in doc.get("hints", [])}
    hint_penalty = sum(hint_cost_map.get(t, 0) for t in hints_used)
    score = max(0, score - hint_penalty)

    if payload.submission_status == "DISQUALIFIED":
        await teams_col.update_one({"team_id": team["team_id"]}, {"$set": {"status": "ELIMINATED"}})

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

@app.get("/api/admin/leaderboard/{round_number}")
async def admin_get_leaderboard(round_number: int, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")

    cursor = submissions_col.find({"round_number": round_number}).sort([
        ("score", -1),
        ("time_taken_seconds", 1),
        ("tab_switch_count", 1)
    ])
    submissions = await cursor.to_list(length=300)

    leaderboard = []
    for rank, sub in enumerate(submissions, start=1):
        team_info = await teams_col.find_one({"team_id": sub["team_id"]})
        leaderboard.append({
            "rank": rank,
            "team_id": sub["team_id"],
            "team_name": team_info.get("team_name", "Unknown") if team_info else "Unknown",
            "score": sub["score"],
            "time_taken_seconds": sub.get("time_taken_seconds", 0),
            "tab_switch_count": sub.get("tab_switch_count", 0),
            "hint_penalty": sub.get("hint_penalty", 0),
            "hints_used": sub.get("hints_used", []),
            "submission_status": sub.get("submission_status", "NORMAL_COMPLETION"),
            "status": team_info.get("status", "QUALIFIED") if team_info else "UNKNOWN",
            "current_round": team_info.get("current_round", 1) if team_info else 1,
            "submitted_at_local": sub.get("submitted_at_local", "")
        })

    total_registered = await teams_col.count_documents({"status": "QUALIFIED", "current_round": round_number})
    active_logins = await teams_col.count_documents({"status": "QUALIFIED", "current_round": round_number, "is_logged_in": True})

    return {
        "round": round_number,
        "total_registered": total_registered,
        "active_logins": active_logins,
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
        session = await sessions_col.find_one({"team_id": t["team_id"], "round_number": t.get("current_round", 1)})
        result.append({
            "team_id": t["team_id"],
            "team_name": t.get("team_name", ""),
            "password": t.get("password", ""),
            "current_round": t.get("current_round", 1),
            "status": t.get("status", "QUALIFIED"),
            "is_logged_in": t.get("is_logged_in", False),
            "session_status": session.get("status", "NOT_STARTED") if session else "NOT_STARTED"
        })
    return {"status": "success", "total": len(result), "teams": result}

@app.post("/api/admin/promote-teams")
async def admin_promote_teams(payload: PromoteTeamsRequest, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")

    prev_round = payload.next_round - 1
    cursor = submissions_col.find({"round_number": prev_round}).sort([
        ("score", -1),
        ("time_taken_seconds", 1),
        ("tab_switch_count", 1)
    ])
    ranked_subs = await cursor.to_list(length=300)

    if not ranked_subs:
        raise HTTPException(status_code=400, detail="No submissions found to promote.")

    promoted_count = 0
    eliminated_count = 0

    for idx, sub in enumerate(ranked_subs):
        t_id = sub["team_id"]
        if idx < payload.top_n_teams:
            await teams_col.update_one(
                {"team_id": t_id},
                {"$set": {"current_round": payload.next_round, "status": "QUALIFIED"}}
            )
            promoted_count += 1
        else:
            await teams_col.update_one(
                {"team_id": t_id},
                {"$set": {"status": "ELIMINATED"}}
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

@app.post("/api/session/progress")
async def save_session_progress(payload: SessionProgressRequest):
    team = await authenticate_team(payload.team_id, payload.password)
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
    doc = await questions_col.find_one({"round_number": payload.round_number})
    if not doc:
        raise HTTPException(status_code=404, detail="Question bank not found.")

    hint = next((h for h in doc.get("hints", []) if h["tier"] == payload.tier), None)
    if not hint:
        raise HTTPException(status_code=404, detail="Hint tier not found.")

    session = await sessions_col.find_one({"team_id": team["team_id"], "round_number": payload.round_number})
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
        "current_round": current_round,
        "round_open": round_status["is_open"],
        "remaining_seconds": round_status["remaining_seconds"]
    }