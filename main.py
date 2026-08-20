import os
import secrets
import string
from datetime import datetime, timezone
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

# 1. MongoDB Connection Setup
# MONGO_URI and ADMIN_SECRET_KEY must be set as real environment variables on Railway.
# No hardcoded fallbacks: if they're missing, fail loudly instead of running with a
# known/default secret.
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

# --- STATIC FRONTEND FILE SERVING ---

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return HTMLResponse("<h1>Index file not found on server</h1>", status_code=404)

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin.html", response_class=HTMLResponse)
async def serve_admin():
    if os.path.exists("admin.html"):
        return FileResponse("admin.html")
    return HTMLResponse("<h1>Admin file not found on server</h1>", status_code=404)

# --- Schemas ---
class QuestionModel(BaseModel):
    id: str
    type: str
    text: str
    options: Optional[List[Dict[str, str]]] = None
    correct_answer: str

class SaveRoundQuestionsRequest(BaseModel):
    round_number: int
    questions: List[QuestionModel]

class CreateTeamRequest(BaseModel):
    team_name: str

class CreateTeamsBulkRequest(BaseModel):
    team_names: List[str]

class LoginRequest(BaseModel):
    team_id: str
    password: str
    target_round: int = 1

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

def generate_random_password(length=6):
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def normalize_text(text: str) -> str:
    return "".join(text.lower().split())

# --- ADMIN QUESTION MANAGER ---

@app.post("/api/admin/questions")
async def admin_save_questions(payload: SaveRoundQuestionsRequest, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    
    doc = {
        "round_number": payload.round_number,
        "questions": [q.dict() for q in payload.questions],
        "updated_at": datetime.now(timezone.utc)
    }
    
    await questions_col.update_one(
        {"round_number": payload.round_number},
        {"$set": doc},
        upsert=True
    )
    return {"status": "success", "round": payload.round_number, "question_count": len(payload.questions)}

@app.get("/api/admin/questions/{round_number}")
async def admin_get_questions(round_number: int, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    
    doc = await questions_col.find_one({"round_number": round_number})
    if not doc:
        return {"round_number": round_number, "questions": []}
    
    doc.pop("_id", None)
    return doc

# --- PARTICIPANT QUESTION FETCHER ---

@app.get("/api/questions/{round_number}")
async def get_questions_for_round(round_number: int):
    doc = await questions_col.find_one({"round_number": round_number})
    if not doc:
        return {"questions": []}
    
    safe_questions = []
    for q in doc.get("questions", []):
        safe_questions.append({
            "id": q["id"],
            "type": q["type"],
            "text": q["text"],
            "options": q.get("options", [])
        })
    return {"round_number": round_number, "questions": safe_questions}

# --- ADMIN TOURNAMENT CONTROLS ---

@app.post("/api/admin/create-team")
async def admin_create_team(payload: CreateTeamRequest, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")
    
    t_name = payload.team_name.strip()
    if not t_name:
        raise HTTPException(status_code=400, detail="Team name cannot be blank.")

    team_id = f"NEX-{''.join(secrets.choice(string.digits) for _ in range(4))}"
    password = generate_random_password(6)

    new_team = {
        "team_id": team_id,
        "team_name": t_name,
        "password": password,
        "current_round": 1,
        "status": "QUALIFIED",
        "created_at": datetime.now(timezone.utc)
    }

    await teams_col.insert_one(new_team)
    return {"status": "success", "team_id": team_id, "team_name": t_name, "password": password}

@app.post("/api/admin/create-teams-bulk")
async def admin_create_teams_bulk(payload: CreateTeamsBulkRequest, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")

    names = [n.strip() for n in payload.team_names if n.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="No valid team names provided.")

    # Avoid team_id collisions within this batch (extremely unlikely but cheap to guard)
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
            "created_at": datetime.now(timezone.utc)
        })
        created.append({"team_id": team_id, "team_name": t_name, "password": password})

    if new_docs:
        await teams_col.insert_many(new_docs)

    return {"status": "success", "created_count": len(created), "teams": created}

@app.get("/api/admin/teams")
async def admin_list_teams(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized Admin Access.")

    cursor = teams_col.find({}).sort("created_at", 1)
    teams = await cursor.to_list(length=1000)

    result = []
    for t in teams:
        result.append({
            "team_id": t["team_id"],
            "team_name": t.get("team_name", ""),
            "password": t.get("password", ""),
            "current_round": t.get("current_round", 1),
            "status": t.get("status", "QUALIFIED")
        })
    return {"status": "success", "total": len(result), "teams": result}

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
            "submission_status": sub.get("submission_status", "NORMAL_COMPLETION"),
            "status": team_info.get("status", "QUALIFIED") if team_info else "UNKNOWN",
            "current_round": team_info.get("current_round", 1) if team_info else 1,
            "submitted_at_local": sub.get("submitted_at_local", "")
        })

    total_registered = await teams_col.count_documents({})
    all_submitted = len(submissions) >= total_registered if total_registered > 0 else False

    return {
        "round": round_number,
        "all_teams_submitted": all_submitted,
        "total_registered": total_registered,
        "total_submitted": len(submissions),
        "leaderboard": leaderboard
    }

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

    return {
        "status": "success",
        "promoted_count": promoted_count,
        "eliminated_count": eliminated_count,
        "next_round": payload.next_round
    }

# --- PARTICIPANT AUTH & SUBMISSION ---

@app.post("/api/auth/login")
async def participant_login(payload: LoginRequest):
    team = await teams_col.find_one({
        "team_id": payload.team_id.strip().upper(),
        "password": payload.password.strip()
    })
    
    if not team:
        raise HTTPException(status_code=401, detail="Invalid Team ID or Access Password.")

    if team.get("status") == "ELIMINATED":
        raise HTTPException(status_code=403, detail="Notice: Your team has been eliminated.")

    if team.get("current_round", 1) < payload.target_round:
        raise HTTPException(status_code=403, detail=f"Your team has not advanced to Round {payload.target_round}.")

    existing_sub = await submissions_col.find_one({
        "team_id": team["team_id"],
        "round_number": payload.target_round
    })
    if existing_sub:
        raise HTTPException(status_code=400, detail=f"Already submitted Round {payload.target_round}.")

    return {
        "status": "success",
        "team_id": team["team_id"],
        "team_name": team["team_name"],
        "current_round": team.get("current_round", 1)
    }

@app.get("/api/team/status/{team_id}")
async def check_team_status(team_id: str):
    team = await teams_col.find_one({"team_id": team_id.strip().upper()})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    
    total_teams = await teams_col.count_documents({})
    round_submissions = await submissions_col.count_documents({"round_number": team.get("current_round", 1)})
    all_finished = (round_submissions >= total_teams) and (total_teams > 0)

    return {
        "team_id": team["team_id"],
        "status": team.get("status", "QUALIFIED"),
        "current_round": team.get("current_round", 1),
        "all_teams_finished": all_finished
    }

@app.post("/api/submit-quiz")
async def submit_quiz(payload: SubmitQuizRequest):
    team = await teams_col.find_one({
        "team_id": payload.team_id.strip().upper(),
        "password": payload.password.strip()
    })
    if not team:
        raise HTTPException(status_code=401, detail="Authentication failed.")

    doc = await questions_col.find_one({"round_number": payload.round_number})
    if not doc:
        raise HTTPException(status_code=400, detail="Round question bank not found.")

    score = 0
    detailed_results = {}
    
    for q in doc.get("questions", []):
        q_id = q["id"]
        correct_ans = q.get("correct_answer", "")
        user_ans = str(payload.answers.get(q_id, "")).strip()

        is_correct = (
            user_ans.upper() == correct_ans.upper()
            or normalize_text(user_ans) == normalize_text(correct_ans)
        )
        if is_correct:
            score += 4

        detailed_results[q_id] = {
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "is_correct": is_correct
        }

    if payload.submission_status == "DISQUALIFIED":
        await teams_col.update_one({"team_id": team["team_id"]}, {"$set": {"status": "ELIMINATED"}})

    record = {
        "team_id": team["team_id"],
        "round_number": payload.round_number,
        "score": score,
        "max_score": len(doc.get("questions", [])) * 4,
        "time_taken_seconds": payload.time_taken_seconds,
        "tab_switch_count": payload.tab_switch_count,
        "submission_status": payload.submission_status,
        "detailed_results": detailed_results,
        "submitted_at_utc": datetime.now(timezone.utc),
        "submitted_at_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    await submissions_col.insert_one(record)
    return {"status": "success", "score": score, "team_id": team["team_id"]}