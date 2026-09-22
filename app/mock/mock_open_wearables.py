"""Mock Open Wearables API Server
用于本地/测试环境验证连接器全链路，无需部署 OW 真实实例。

启动: uvicorn app.mock.mock_open_wearables:app --host 0.0.0.0 --port 8001
"""
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Mock Open Wearables API", version="0.9")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# 模拟用户
_USERS = {
    str(uuid.uuid4()): {
        "id": None,
        "email": "demo@example.com",
        "name": "Demo User",
        "providers": ["garmin", "oura"],
    }
}
for uid in _USERS:
    _USERS[uid]["id"] = uid

_API_KEY = "mock-api-key-001"


def _check_key(x_open_wearables_api_key: str | None):
    if x_open_wearables_api_key != _API_KEY:
        return False
    return True


class DateRange(BaseModel):
    start_date: str = Query(None)
    end_date: str = Query(None)


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------
@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "0.9-mock", "timestamp": datetime.now(timezone.utc).isoformat()}


# ------------------------------------------------------------------
# Users
# ------------------------------------------------------------------
@app.get("/api/v1/users")
async def list_users(
    x_open_wearables_api_key: str | None = Header(None),
    search: str = "",
    limit: int = 50,
):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    users = list(_USERS.values())
    if search:
        users = [u for u in users if search.lower() in u.get("email", "").lower()]
    return {"users": users[:limit]}


# ------------------------------------------------------------------
# Summaries
# ------------------------------------------------------------------
def _gen_sleep_records(days: int = 7) -> list[dict]:
    records = []
    now = datetime.now(timezone.utc)
    for i in range(days):
        d = now - timedelta(days=i)
        records.append({
            "date": d.strftime("%Y-%m-%d"),
            "total_duration_min": random.randint(360, 540),
            "deep_sleep_min": random.randint(60, 120),
            "light_sleep_min": random.randint(180, 300),
            "rem_sleep_min": random.randint(90, 150),
            "awake_min": random.randint(10, 40),
            "sleep_efficiency": round(random.uniform(0.82, 0.95), 2),
            "hrv_avg": random.randint(35, 85),
            "bedtime": f"{random.randint(22, 23):02d}:{random.randint(0, 59):02d}",
            "wake_time": f"{random.randint(5, 8):02d}:{random.randint(0, 59):02d}",
        })
    return records


def _gen_activity_records(days: int = 7) -> list[dict]:
    records = []
    now = datetime.now(timezone.utc)
    for i in range(days):
        d = now - timedelta(days=i)
        records.append({
            "date": d.strftime("%Y-%m-%d"),
            "steps": random.randint(3000, 15000),
            "calories": random.randint(200, 800),
            "heart_rate_avg": random.randint(60, 90),
            "heart_rate_max": random.randint(120, 180),
            "distance": random.randint(2000, 12000),
            "intensity_minutes": random.randint(15, 90),
        })
    return records


def _gen_body_records(days: int = 7) -> list[dict]:
    records = []
    now = datetime.now(timezone.utc)
    for i in range(days):
        d = now - timedelta(days=i)
        records.append({
            "date": d.strftime("%Y-%m-%d"),
            "weight": round(random.uniform(65.0, 75.0), 1),
            "body_fat_pct": round(random.uniform(18.0, 25.0), 1),
            "systolic": random.randint(110, 130),
            "diastolic": random.randint(70, 85),
        })
    return records


def _gen_recovery_records(days: int = 7) -> list[dict]:
    records = []
    now = datetime.now(timezone.utc)
    for i in range(days):
        d = now - timedelta(days=i)
        records.append({
            "date": d.strftime("%Y-%m-%d"),
            "recovery_score": random.randint(40, 95),
            "stress_score": random.randint(20, 80),
            "sleep_score": random.randint(50, 95),
        })
    return records


@app.get("/api/v1/users/{user_id}/summaries/sleep")
async def sleep_summaries(
    user_id: str,
    x_open_wearables_api_key: str | None = Header(None),
    start_date: str = None,
    end_date: str = None,
):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    # Accept any user_id (mock mode: generate data for any user)
    days = 7
    try:
        if start_date and end_date:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            days = (ed - sd).days + 1
    except Exception:
        pass
    return {"records": _gen_sleep_records(days)}


@app.get("/api/v1/users/{user_id}/summaries/activity")
async def activity_summaries(
    user_id: str,
    x_open_wearables_api_key: str | None = Header(None),
    start_date: str = None,
    end_date: str = None,
):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    days = 7
    try:
        if start_date and end_date:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            days = (ed - sd).days + 1
    except Exception:
        pass
    return {"records": _gen_activity_records(days)}


@app.get("/api/v1/users/{user_id}/summaries/body")
async def body_summaries(
    user_id: str,
    x_open_wearables_api_key: str | None = Header(None),
    start_date: str = None,
    end_date: str = None,
):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    days = 7
    try:
        if start_date and end_date:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            days = (ed - sd).days + 1
    except Exception:
        pass
    return {"records": _gen_body_records(days)}


@app.get("/api/v1/users/{user_id}/summaries/recovery")
async def recovery_summaries(
    user_id: str,
    x_open_wearables_api_key: str | None = Header(None),
    start_date: str = None,
    end_date: str = None,
):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    days = 7
    try:
        if start_date and end_date:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            days = (ed - sd).days + 1
    except Exception:
        pass
    return {"records": _gen_recovery_records(days)}


# ------------------------------------------------------------------
# Events
# ------------------------------------------------------------------
def _gen_workout_events(days: int = 7) -> list[dict]:
    events = []
    sports = ["running", "cycling", "swimming", "walking", "yoga"]
    now = datetime.now(timezone.utc)
    for i in range(days):
        d = now - timedelta(days=i)
        if random.random() > 0.4:  # 60% days have workouts
            events.append({
                "start": d.replace(hour=random.randint(6, 18)).isoformat(),
                "sport": random.choice(sports),
                "duration_min": random.randint(20, 120),
                "calories": random.randint(150, 600),
            })
    return events


def _gen_sleep_events(days: int = 7) -> list[dict]:
    events = []
    now = datetime.now(timezone.utc)
    for i in range(days):
        d = now - timedelta(days=i)
        events.append({
            "start": d.replace(hour=random.randint(22, 23), minute=random.randint(0, 59)).isoformat(),
            "duration_min": random.randint(360, 540),
            "deep_duration_min": random.randint(60, 120),
            "rem_duration_min": random.randint(90, 150),
            "efficiency": round(random.uniform(0.82, 0.95), 2),
        })
    return events


@app.get("/api/v1/users/{user_id}/events/workouts")
async def workout_events(
    user_id: str,
    x_open_wearables_api_key: str | None = Header(None),
    start_date: str = None,
    end_date: str = None,
):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    days = 7
    try:
        if start_date and end_date:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            days = (ed - sd).days + 1
    except Exception:
        pass
    return {"records": _gen_workout_events(days)}


@app.get("/api/v1/users/{user_id}/events/sleep")
async def sleep_events(
    user_id: str,
    x_open_wearables_api_key: str | None = Header(None),
    start_date: str = None,
    end_date: str = None,
):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    days = 7
    try:
        if start_date and end_date:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            days = (ed - sd).days + 1
    except Exception:
        pass
    return {"records": _gen_sleep_events(days)}


# ------------------------------------------------------------------
# Timeseries
# ------------------------------------------------------------------
def _gen_timeseries(days: int = 7) -> list[dict]:
    records = []
    now = datetime.now(timezone.utc)
    for i in range(days):
        d = now - timedelta(days=i)
        # 每小时一个采样点
        for h in range(0, 24, 2):
            ts = d.replace(hour=h, minute=0)
            records.append({
                "timestamp": ts.isoformat(),
                "heart_rate": random.randint(50, 100),
                "hrv": random.randint(20, 100),
                "spo2": random.randint(95, 99),
                "respiratory_rate": random.randint(12, 20),
                "steps": random.randint(50, 500),
            })
    return records


@app.get("/api/v1/users/{user_id}/timeseries")
async def timeseries(
    user_id: str,
    x_open_wearables_api_key: str | None = Header(None),
    start_date: str = None,
    end_date: str = None,
):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    days = 7
    try:
        if start_date and end_date:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            days = (ed - sd).days + 1
    except Exception:
        pass
    return {"records": _gen_timeseries(days)}


# ------------------------------------------------------------------
# Providers
# ------------------------------------------------------------------
@app.get("/api/v1/providers")
async def list_providers():
    return {
        "providers": [
            "garmin", "oura", "whoop", "polar", "suunto",
            "strava", "fitbit", "ultrahuman", "withings", "google_health",
        ]
    }


# ------------------------------------------------------------------
# Webhook endpoints
# ------------------------------------------------------------------
@app.post("/api/v1/webhooks/endpoints")
async def create_webhook(x_open_wearables_api_key: str | None = Header(None)):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    return {"id": str(uuid.uuid4()), "status": "active"}
