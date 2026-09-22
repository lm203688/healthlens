"""Standalone mock OW server - no app package dependency"""
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Mock Open Wearables API", version="0.9")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_API_KEY = "mock-api-key-001"

def _check_key(x_open_wearables_api_key):
    return x_open_wearables_api_key == _API_KEY

def _gen_sleep(days=7):
    now = datetime.now(timezone.utc)
    return [{"date": (now-timedelta(days=i)).strftime("%Y-%m-%d"), "total_duration_min": random.randint(360,540), "deep_sleep_min": random.randint(60,120), "light_sleep_min": random.randint(180,300), "rem_sleep_min": random.randint(90,150), "awake_min": random.randint(10,40), "sleep_efficiency": round(random.uniform(0.82,0.95),2), "hrv_avg": random.randint(35,85), "bedtime": f"{random.randint(22,23):02d}:{random.randint(0,59):02d}", "wake_time": f"{random.randint(5,8):02d}:{random.randint(0,59):02d}"} for i in range(days)]

def _gen_activity(days=7):
    now = datetime.now(timezone.utc)
    return [{"date": (now-timedelta(days=i)).strftime("%Y-%m-%d"), "steps": random.randint(3000,15000), "calories": random.randint(200,800), "heart_rate_avg": random.randint(60,90), "heart_rate_max": random.randint(120,180), "distance": random.randint(2000,12000), "intensity_minutes": random.randint(15,90)} for i in range(days)]

def _gen_body(days=7):
    now = datetime.now(timezone.utc)
    return [{"date": (now-timedelta(days=i)).strftime("%Y-%m-%d"), "weight": round(random.uniform(65.0,75.0),1), "body_fat_pct": round(random.uniform(18.0,25.0),1), "systolic": random.randint(110,130), "diastolic": random.randint(70,85)} for i in range(days)]

def _gen_recovery(days=7):
    now = datetime.now(timezone.utc)
    return [{"date": (now-timedelta(days=i)).strftime("%Y-%m-%d"), "recovery_score": random.randint(40,95), "stress_score": random.randint(20,80), "sleep_score": random.randint(50,95)} for i in range(days)]

def _gen_workouts(days=7):
    now = datetime.now(timezone.utc)
    sports = ["running","cycling","swimming","walking","yoga"]
    return [{"start": (now-timedelta(days=i)).replace(hour=random.randint(6,18)).isoformat(), "sport": random.choice(sports), "duration_min": random.randint(20,120), "calories": random.randint(150,600)} for i in range(days) if random.random()>0.4]

def _gen_sleep_events(days=7):
    now = datetime.now(timezone.utc)
    return [{"start": (now-timedelta(days=i)).replace(hour=random.randint(22,23)).isoformat(), "duration_min": random.randint(360,540), "deep_duration_min": random.randint(60,120), "rem_duration_min": random.randint(90,150), "efficiency": round(random.uniform(0.82,0.95),2)} for i in range(days)]

def _gen_timeseries(days=7):
    now = datetime.now(timezone.utc)
    records = []
    for i in range(days):
        d = now - timedelta(days=i)
        for h in range(0, 24, 2):
            records.append({"timestamp": d.replace(hour=h).isoformat(), "heart_rate": random.randint(50,100), "hrv": random.randint(20,100), "spo2": random.randint(95,99), "respiratory_rate": random.randint(12,20), "steps": random.randint(50,500)})
    return records

def _get_days(start_date, end_date, default=7):
    try:
        if start_date and end_date:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            return (ed - sd).days + 1
    except:
        pass
    return default

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "0.9-mock", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/providers")
async def list_providers():
    return {"providers": ["garmin","oura","whoop","polar","suunto","strava","fitbit","ultrahuman","withings","google_health"]}

@app.get("/api/v1/users")
async def list_users(x_open_wearables_api_key=Header(None), search="", limit=50):
    if not _check_key(x_open_wearables_api_key):
        return {"error": "Unauthorized"}
    return {"users": [{"id": str(uuid.uuid4()), "email": "demo@example.com", "name": "Demo User", "providers": ["garmin","oura"]}]}

@app.get("/api/v1/users/{user_id}/summaries/sleep")
async def sleep_summaries(user_id: str, x_open_wearables_api_key=Header(None), start_date=None, end_date=None):
    if not _check_key(x_open_wearables_api_key): return {"error": "Unauthorized"}
    return {"records": _gen_sleep(_get_days(start_date, end_date))}

@app.get("/api/v1/users/{user_id}/summaries/activity")
async def activity_summaries(user_id: str, x_open_wearables_api_key=Header(None), start_date=None, end_date=None):
    if not _check_key(x_open_wearables_api_key): return {"error": "Unauthorized"}
    return {"records": _gen_activity(_get_days(start_date, end_date))}

@app.get("/api/v1/users/{user_id}/summaries/body")
async def body_summaries(user_id: str, x_open_wearables_api_key=Header(None), start_date=None, end_date=None):
    if not _check_key(x_open_wearables_api_key): return {"error": "Unauthorized"}
    return {"records": _gen_body(_get_days(start_date, end_date))}

@app.get("/api/v1/users/{user_id}/summaries/recovery")
async def recovery_summaries(user_id: str, x_open_wearables_api_key=Header(None), start_date=None, end_date=None):
    if not _check_key(x_open_wearables_api_key): return {"error": "Unauthorized"}
    return {"records": _gen_recovery(_get_days(start_date, end_date))}

@app.get("/api/v1/users/{user_id}/events/workouts")
async def workout_events(user_id: str, x_open_wearables_api_key=Header(None), start_date=None, end_date=None):
    if not _check_key(x_open_wearables_api_key): return {"error": "Unauthorized"}
    return {"records": _gen_workouts(_get_days(start_date, end_date))}

@app.get("/api/v1/users/{user_id}/events/sleep")
async def sleep_events(user_id: str, x_open_wearables_api_key=Header(None), start_date=None, end_date=None):
    if not _check_key(x_open_wearables_api_key): return {"error": "Unauthorized"}
    return {"records": _gen_sleep_events(_get_days(start_date, end_date))}

@app.get("/api/v1/users/{user_id}/timeseries")
async def timeseries(user_id: str, x_open_wearables_api_key=Header(None), start_date=None, end_date=None):
    if not _check_key(x_open_wearables_api_key): return {"error": "Unauthorized"}
    return {"records": _gen_timeseries(_get_days(start_date, end_date))}

@app.post("/api/v1/webhooks/endpoints")
async def create_webhook(x_open_wearables_api_key=Header(None)):
    if not _check_key(x_open_wearables_api_key): return {"error": "Unauthorized"}
    return {"id": str(uuid.uuid4()), "status": "active"}
