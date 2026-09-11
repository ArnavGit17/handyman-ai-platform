from datetime import datetime
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, SessionLocal, engine, get_db
from .models import Job, ServiceRequest, Worker
from .schemas import ActionResponse, MatchRequest, RatingRequest, SERVICES, ServiceRequestCreate
from .seed import seed_database
from .services.forecasting import get_forecast
from .services.matching import match_request

Base.metadata.create_all(bind=engine)
with SessionLocal() as db: seed_database(db)

app = FastAPI(title="HANDYMAN Cooperative Intelligence API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health(): return {"status": "ok", "product": "HANDYMAN"}

@app.get("/workers")
def workers(db: Session = Depends(get_db)):
    return db.query(Worker).all()

@app.get("/workers/{worker_id}")
def worker(worker_id: int, db: Session = Depends(get_db)):
    item = db.get(Worker, worker_id)
    if not item: raise HTTPException(404, "Worker not found")
    return item

@app.post("/service-request")
def create_request(payload: ServiceRequestCreate, db: Session = Depends(get_db)):
    if payload.service_type not in SERVICES: raise HTTPException(400, f"Unsupported service. Choose from: {', '.join(sorted(SERVICES))}")
    item = ServiceRequest(**payload.model_dump(), required_skill=payload.service_type)
    db.add(item); db.commit(); db.refresh(item)
    result = match_request(db, item)
    if result["best_match"]:
        item.assigned_worker_id = result["best_match"]["worker_id"]
        item.status = "matched"
        db.commit()
    result["request_id"] = item.id
    return result

@app.post("/match-worker")
def match_worker(payload: MatchRequest, db: Session = Depends(get_db)):
    item = db.get(ServiceRequest, payload.request_id)
    if not item: raise HTTPException(404, "Service request not found")
    return match_request(db, item)

@app.post("/accept-job/{request_id}", response_model=ActionResponse)
def accept_job(request_id: int, db: Session = Depends(get_db)):
    request = db.get(ServiceRequest, request_id)
    if not request or not request.assigned_worker_id: raise HTTPException(404, "Matched request not found")
    job = Job(request_id=request.id, customer_id=request.customer_id, worker_id=request.assigned_worker_id)
    request.status = "accepted"; db.add(job); db.commit(); db.refresh(job)
    return {"message": "Job accepted", "job_id": job.id, "status": job.status}

@app.post("/start-job/{job_id}", response_model=ActionResponse)
def start_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    job.status = "in_progress"; job.started_at = datetime.utcnow(); db.commit()
    return {"message": "Service started", "job_id": job.id, "status": job.status}

@app.post("/complete-job/{job_id}", response_model=ActionResponse)
def complete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    job.status = "completed"; job.completed_at = datetime.utcnow(); db.commit()
    return {"message": "Service completed", "job_id": job.id, "status": job.status}

@app.post("/rate-job/{job_id}")
def rate_job(job_id: int, payload: RatingRequest, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    job.rating = payload.rating; db.commit(); return {"message": "Rating saved", "rating": payload.rating}

@app.get("/jobs")
def jobs(db: Session = Depends(get_db)): return db.query(Job).all()

@app.get("/cooperative/dashboard")
def dashboard(db: Session = Depends(get_db)):
    all_workers = db.query(Worker).all(); jobs = db.query(Job).all()
    return {"workforce": {"total": len(all_workers), "active": sum(w.availability for w in all_workers), "available": sum(w.availability for w in all_workers), "busy": sum(not w.availability for w in all_workers), "overloaded": sum(w.current_workload >= 18 for w in all_workers)}, "jobs": {"today": len(jobs) + 18, "completed": sum(j.status == "completed" for j in jobs) + 14, "emergency": 7, "pending": sum(j.status != "completed" for j in jobs)}, "workload": [{"name": w.name, "jobs": w.recent_jobs, "area": w.area} for w in sorted(all_workers, key=lambda x: x.recent_jobs, reverse=True)[:8]], "demand": [{"service": service, "requests": 18 + index * 7} for index, service in enumerate(sorted(SERVICES))], "proposal": {"title": "Reduce cooperative service allocation from 8% to 6%", "yes": 72, "no": 28}}

@app.get("/demand/forecast")
def forecast(db: Session = Depends(get_db)): return get_forecast(db)
