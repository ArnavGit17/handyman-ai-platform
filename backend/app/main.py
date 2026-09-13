import hashlib
import os
from datetime import datetime, timedelta
from math import sqrt

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, ensure_schema, engine, get_db
from .models import Customer, Job, Payment, ServiceRequest, User, Worker, SOSAlert, MatchingEvaluation
from .schemas import (
    MatchingEvaluationResponse,
    MatchingEvaluationSummary,
    ActionResponse,
    AuthLogin,
    AuthRegister,
    CustomerProfileUpdate,
    MatchRequest,
    PaymentConfirm,
    RatingRequest,
    SERVICES,
    ServiceRequestCreate,
    WorkerAvailabilityUpdate,
    WorkerProfileUpdate,
    SOSAlertResponse,
)
from .seed import AREAS, seed_database
from .services.forecasting import get_forecast
from .services.matching import distance_km, match_request
from .services.benchmark import run_benchmark
from .services.payments import ensure_payment_for_job, payment_history_item, payment_response
from .services.request_understanding import RequestUnderstandingService

ENV = os.getenv("ENVIRONMENT", "development")
SECRET_KEY = os.getenv("JWT_SECRET_KEY") or os.getenv("HANDYMAN_SECRET_KEY")
if not SECRET_KEY:
    if ENV == "production":
        raise ValueError("JWT_SECRET_KEY environment variable is required in production.")
    SECRET_KEY = "handyman-demo-secret"
ALGORITHM = "HS256"

ensure_schema()
with SessionLocal() as db:
    seed_database(db)

app = FastAPI(title="HANDYMAN Cooperative Intelligence API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
request_understanding = RequestUnderstandingService()


def hash_password(password: str) -> str:
    salt = b"handyman-auth-salt"
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120000)
    return hashed.hex()


def verify_password(password: str, stored_hash: str) -> bool:
    return hash_password(password) == stored_hash


def create_token(user: User) -> str:
    payload = {"sub": str(user.id), "email": user.email, "role": user.role, "exp": datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_current_user_optional(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    return db.get(User, int(payload["sub"]))


def get_customer_for_user(db: Session, user: User) -> Customer | None:
    return db.query(Customer).filter(Customer.user_id == user.id).first()


def get_worker_for_user(db: Session, user: User) -> Worker | None:
    return db.query(Worker).filter(Worker.user_id == user.id).first()


def sync_worker_availability(worker: Worker):
    if worker.availability_status not in {"Available", "Unavailable"}:
        worker.availability_status = "Available" if worker.availability else "Unavailable"
    worker.availability = worker.availability_status == "Available"
    if worker.max_concurrent_jobs is None or worker.max_concurrent_jobs <= 0:
        worker.max_concurrent_jobs = 3
    if worker.last_status_update is None:
        worker.last_status_update = datetime.utcnow()
    return worker


@app.post("/auth/register")
def register(payload: AuthRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if existing:
        raise HTTPException(409, "User with this email already exists")

    user = User(
        name=payload.name.strip(),
        email=payload.email.lower().strip(),
        phone=payload.phone or "",
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if payload.role == "customer":
        area = payload.area or "Area A"
        location = payload.location or {"latitude": 12.9716, "longitude": 77.5946}
        customer = Customer(
            user_id=user.id,
            name=user.name,
            phone=user.phone or "",
            area=area,
            latitude=float(location.get("latitude", 12.9716)),
            longitude=float(location.get("longitude", 77.5946)),
            is_demo=False,
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return {"user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}, "customer": {"id": customer.id, "area": customer.area}}

    worker_area = payload.area or (payload.service_areas[0] if payload.service_areas else "Area A")
    loc = payload.location or {"latitude": 12.9716, "longitude": 77.5946}
    skill_value = payload.skills or payload.skill or "General"
    certifications = payload.certifications or (f"{skill_value} Level 3" if skill_value and skill_value.lower() != "general" else "")
    status_value = payload.availability_status or ("Available" if payload.availability is not False else "Unavailable")
    worker = Worker(
        user_id=user.id,
        name=user.name,
        phone=user.phone or "",
        skills=skill_value,
        certifications=certifications,
        experience_years=payload.experience or 5,
        latitude=float(loc.get("latitude", 12.9716)),
        longitude=float(loc.get("longitude", 77.5946)),
        area=worker_area,
        availability=status_value == "Available",
        availability_status=status_value,
        current_workload=0,
        max_concurrent_jobs=payload.max_concurrent_jobs or 3,
        available_from=datetime.utcnow() if status_value == "Available" else None,
        last_status_update=datetime.utcnow(),
        rating=4.9,
        jobs_completed=0,
        earnings=0,
        verification_status="Verified",
        recent_jobs=0,
        is_demo=False,
        service_areas=", ".join(payload.service_areas) if payload.service_areas else worker_area,
        hourly_rate=float(payload.rate or 0),
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return {"user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}, "worker": {"id": worker.id, "skills": worker.skills, "area": worker.area, "availability": worker.availability}}


@app.post("/auth/login")
def login(payload: AuthLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_token(user)
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}}


@app.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email, "role": current_user.role}


@app.get("/customers/me")
def customers_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can access this profile")
    customer = get_customer_for_user(db, current_user)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return {"id": customer.id, "user_id": customer.user_id, "name": customer.name, "phone": customer.phone, "area": customer.area, "latitude": customer.latitude, "longitude": customer.longitude}


@app.put("/customers/me")
def update_customer_profile(payload: CustomerProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can update this profile")
    customer = get_customer_for_user(db, current_user)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return {"id": customer.id, "user_id": customer.user_id, "name": customer.name, "phone": customer.phone, "area": customer.area, "latitude": customer.latitude, "longitude": customer.longitude}


@app.get("/workers/me")
def worker_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can access this profile")
    worker = get_worker_for_user(db, current_user)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    sync_worker_availability(worker)
    db.commit()
    return {
        "id": worker.id,
        "user_id": worker.user_id,
        "name": worker.name,
        "phone": worker.phone,
        "skills": worker.skills,
        "certifications": worker.certifications,
        "area": worker.area,
        "availability": worker.availability,
        "availability_status": worker.availability_status,
        "current_workload": worker.current_workload,
        "max_concurrent_jobs": worker.max_concurrent_jobs,
        "experience_years": worker.experience_years,
        "hourly_rate": worker.hourly_rate,
        "verification_status": worker.verification_status,
        "service_areas": worker.service_areas,
        "jobs_completed": worker.jobs_completed,
        "earnings": worker.earnings,
        "rating": worker.rating,
        "latitude": worker.latitude,
        "longitude": worker.longitude,
    }


@app.put("/workers/me")
def update_worker_profile(payload: WorkerProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can update this profile")
    worker = get_worker_for_user(db, current_user)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    updates = payload.model_dump(exclude_none=True)
    for field, value in updates.items():
        if field == "experience_years":
            setattr(worker, "experience_years", value)
        elif field == "service_areas":
            setattr(worker, "service_areas", ", ".join(value) if isinstance(value, list) else str(value))
        elif field == "certifications" and value is not None:
            setattr(worker, "certifications", str(value))
        elif field == "availability_status" and value is not None:
            setattr(worker, "availability_status", value)
            setattr(worker, "availability", value == "Available")
            worker.last_status_update = datetime.utcnow()
        elif field == "max_concurrent_jobs" and value is not None:
            setattr(worker, "max_concurrent_jobs", max(1, int(value)))
        else:
            setattr(worker, field, value)
    sync_worker_availability(worker)
    db.commit(); db.refresh(worker)
    return {"id": worker.id, "name": worker.name, "skills": worker.skills, "certifications": worker.certifications, "area": worker.area, "availability": worker.availability, "availability_status": worker.availability_status, "current_workload": worker.current_workload, "max_concurrent_jobs": worker.max_concurrent_jobs, "experience_years": worker.experience_years, "service_areas": worker.service_areas, "hourly_rate": worker.hourly_rate, "latitude": worker.latitude, "longitude": worker.longitude}


@app.get("/workers/me/requests")
def worker_requests(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can access this inbox")
    worker = get_worker_for_user(db, current_user)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    jobs = db.query(Job).filter(Job.worker_id == worker.id).order_by(Job.assigned_at.desc()).all()
    rows = []
    for job in jobs:
        request = db.get(ServiceRequest, job.request_id)
        customer = db.get(Customer, job.customer_id)
        payment = db.query(Payment).filter(Payment.job_id == job.id).first()
        if request is None:
            continue
        distance = None
        if request.latitude is not None and request.longitude is not None and worker.latitude is not None and worker.longitude is not None:
            distance = round(sqrt((request.latitude - worker.latitude) ** 2 + (request.longitude - worker.longitude) ** 2) * 111, 1)
        rows.append({
            "job_id": job.id,
            "request_id": request.id,
            "customer_id": customer.id if customer else None,
            "customer_name": customer.name if customer else None,
            "service": request.service_type,
            "description": request.description,
            "area": request.area,
            "urgency": request.urgency,
            "status": job.status,
            "distance_km": distance,
            "job_amount": job.amount,
            "worker_earning": job.worker_earning,
            "estimated_earnings": job.worker_earning,
            "payment_id": payment.id if payment else None,
            "payment_status": payment.status if payment else "not_due",
            "payment_method": payment.payment_method if payment else None,
            "payment_transaction_reference": payment.transaction_reference if payment and payment.status == "paid" else None,
            "paid_at": payment.paid_at.isoformat() if payment and payment.paid_at else None,
            "created_at": request.created_at.isoformat() if request.created_at else None,
            "sos_alert": _get_active_sos(db, job.id),
        })
    return rows


@app.get("/workers/me/workload")
def worker_workload(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can access workload data")
    worker = get_worker_for_user(db, current_user)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    active_jobs = db.query(Job).filter(Job.worker_id == worker.id, Job.status.in_(["assigned", "accepted", "in_progress"])) .count()
    worker.current_workload = active_jobs
    sync_worker_availability(worker)
    db.commit()
    capacity = max(1, worker.max_concurrent_jobs or 3)
    return {
        "worker_id": worker.id,
        "current_workload": active_jobs,
        "max_concurrent_jobs": capacity,
        "utilization_percent": round((active_jobs / capacity) * 100, 1),
        "available": worker.availability_status == "Available" and active_jobs < capacity,
        "availability_status": worker.availability_status,
    }


@app.patch("/workers/me/availability")
def worker_update_availability(payload: WorkerAvailabilityUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can change availability")
    worker = get_worker_for_user(db, current_user)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    worker.availability_status = payload.availability_status
    worker.availability = payload.availability_status == "Available"
    worker.last_status_update = datetime.utcnow()
    if payload.availability_status == "Available":
        worker.available_from = datetime.utcnow()
    else:
        worker.available_from = None
    sync_worker_availability(worker)
    db.commit(); db.refresh(worker)
    return {
        "worker_id": worker.id,
        "id": worker.id,
        "user_id": worker.user_id,
        "name": worker.name,
        "skills": worker.skills,
        "area": worker.area,
        "availability": worker.availability,
        "availability_status": worker.availability_status,
        "current_workload": worker.current_workload,
        "max_concurrent_jobs": worker.max_concurrent_jobs,
        "updated_at": worker.last_status_update.isoformat(),
    }


@app.get("/service-requests/me")
def customer_requests(
    current_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can access their requests")
    customer = get_customer_for_user(db, current_user)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    request_query = db.query(ServiceRequest).filter(ServiceRequest.customer_id == customer.id).order_by(ServiceRequest.created_at.desc())
    if current_only:
        request_query = request_query.limit(1)
    requests = request_query.all()
    rows = []
    for request in requests:
        assigned_worker = db.get(Worker, request.assigned_worker_id) if request.assigned_worker_id else None
        latest_job = db.query(Job).filter(Job.request_id == request.id).order_by(Job.id.desc()).first()
        payment = db.query(Payment).filter(Payment.job_id == latest_job.id).first() if latest_job else None
        rows.append({
            "id": request.id,
            "customer_id": request.customer_id,
            "service": request.service_type,
            "description": request.description,
            "area": request.area,
            "urgency": request.urgency,
            "status": request.status,
            "assigned_worker_id": request.assigned_worker_id,
            "assigned_worker": assigned_worker.name if assigned_worker else None,
            "job_id": latest_job.id if latest_job else None,
            "job_status": latest_job.status if latest_job else None,
            "job_amount": latest_job.amount if latest_job else None,
            "worker_earning": latest_job.worker_earning if latest_job else None,
            "payment_id": payment.id if payment else None,
            "payment_status": payment.status if payment else "not_due",
            "payment_transaction_reference": payment.transaction_reference if payment else None,
            "payment_paid_at": payment.paid_at.isoformat() if payment and payment.paid_at else None,
            "created_at": request.created_at.isoformat() if request.created_at else None,
            "sos_alert": _get_active_sos(db, latest_job.id) if latest_job else None,
        })
    return rows


@app.get("/service-request/{request_id}")
def get_service_request(request_id: int, current_user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    request = db.get(ServiceRequest, request_id)
    if not request:
        raise HTTPException(404, "Service request not found")
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if current_user.role == "customer":
        customer = get_customer_for_user(db, current_user)
        if customer is None or request.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="You do not own this request")
    elif current_user.role == "worker":
        worker = get_worker_for_user(db, current_user)
        job = db.query(Job).filter(Job.request_id == request_id, Job.worker_id == worker.id).first() if worker else None
        if worker is None or job is None:
            raise HTTPException(status_code=403, detail="You do not have access to this request")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    assigned_worker = db.get(Worker, request.assigned_worker_id) if request.assigned_worker_id else None
    return {
        "id": request.id,
        "customer_id": request.customer_id,
        "service_type": request.service_type,
        "description": request.description,
        "area": request.area,
        "latitude": request.latitude,
        "longitude": request.longitude,
        "urgency": request.urgency,
        "status": request.status,
        "assigned_worker_id": request.assigned_worker_id,
        "assigned_worker": assigned_worker.name if assigned_worker else None,
        "created_at": request.created_at.isoformat() if request.created_at else None,
    }


@app.get("/jobs/{job_id}/payment")
def get_job_payment(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only the owning customer can view this payment")
    customer = get_customer_for_user(db, current_user)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if customer is None or job.customer_id != customer.id:
        raise HTTPException(status_code=403, detail="You do not own this payment")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Payment is available after the job is completed")

    payment = ensure_payment_for_job(db, job)
    db.commit()
    db.refresh(payment)
    return payment_response(db, payment, include_qr=True)


@app.get("/payments/me")
def my_payments(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can view payment history")
    customer = get_customer_for_user(db, current_user)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    payments = db.query(Payment).filter(Payment.customer_id == customer.id).order_by(Payment.created_at.desc(), Payment.id.desc()).all()
    return [payment_history_item(db, payment) for payment in payments]


@app.post("/payments/{payment_id}/confirm")
def confirm_payment(
    payment_id: int,
    payload: PaymentConfirm,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only the owning customer can confirm this payment")
    customer = get_customer_for_user(db, current_user)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    job = db.get(Job, payment.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Linked job not found")
    if payment.customer_id != customer.id or job.customer_id != customer.id:
        raise HTTPException(status_code=403, detail="You do not own this payment")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Payment can only be confirmed after job completion")
    if payment.status != "pending":
        raise HTTPException(status_code=409, detail="Payment is not pending")

    reference = payload.transaction_reference.strip()
    if not reference:
        raise HTTPException(status_code=422, detail="Transaction reference is required")
    payment.transaction_reference = reference
    payment.payment_method = "UPI_QR"
    payment.status = "awaiting_worker_confirmation"
    db.commit()
    db.refresh(payment)
    result = payment_response(db, payment, include_qr=True)
    result["message"] = "UPI payment submitted — awaiting worker confirmation"
    return result


@app.post("/payments/{payment_id}/cash-report")
def report_cash_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only the owning customer can report cash payment")
    customer = get_customer_for_user(db, current_user)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    job = db.get(Job, payment.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Linked job not found")
    if payment.customer_id != customer.id or job.customer_id != customer.id:
        raise HTTPException(status_code=403, detail="You do not own this payment")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Payment can only be reported after job completion")
    if payment.status != "pending":
        raise HTTPException(status_code=409, detail="Payment is not pending")

    payment.payment_method = "Cash"
    payment.status = "awaiting_cash_confirmation"
    db.commit()
    db.refresh(payment)
    result = payment_response(db, payment, include_qr=False)
    result["message"] = "Cash payment reported"
    return result


@app.post("/payments/{payment_id}/cash-confirm")
def confirm_cash_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only the assigned worker can confirm cash payment")
    worker = get_worker_for_user(db, current_user)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    job = db.get(Job, payment.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Linked job not found")
    if payment.worker_id != worker.id or job.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="You are not assigned to this job")
    if payment.status not in ("awaiting_cash_confirmation", "awaiting_worker_confirmation"):
        raise HTTPException(status_code=409, detail="Payment is not awaiting worker confirmation")

    payment.status = "paid"
    payment.paid_at = datetime.utcnow()
    db.commit()
    db.refresh(payment)
    result = payment_response(db, payment, include_qr=False)
    result["message"] = "Cash payment confirmed"
    return result


# ─────────────────────── SOS / Safety helpers ───────────────────────

def _get_active_sos(db: Session, job_id: int) -> dict | None:
    """Return the most recent non-cancelled SOS alert for the job, or None."""
    alert = (
        db.query(SOSAlert)
        .filter(SOSAlert.job_id == job_id, SOSAlert.status != "CANCELLED")
        .order_by(SOSAlert.id.desc())
        .first()
    )
    if not alert:
        return None
    return {
        "id": alert.id,
        "job_id": alert.job_id,
        "status": alert.status,
        "activated_by_role": alert.activated_by_role,
        "created_at": alert.created_at.isoformat(),
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
    }


@app.post("/jobs/{job_id}/sos")
def activate_sos(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activate an SOS alert for the given job. Only the customer or assigned worker may call this."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if current_user.role == "customer":
        customer = get_customer_for_user(db, current_user)
        if customer is None or job.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="You do not own this job")
        activated_by_role = "customer"
        customer_id = customer.id
        worker_id = job.worker_id
    elif current_user.role == "worker":
        worker = get_worker_for_user(db, current_user)
        if worker is None or job.worker_id != worker.id:
            raise HTTPException(status_code=403, detail="You are not assigned to this job")
        activated_by_role = "worker"
        customer_id = job.customer_id
        worker_id = worker.id
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Prevent duplicate active alerts
    existing = db.query(SOSAlert).filter(
        SOSAlert.job_id == job_id, SOSAlert.status == "ACTIVE"
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="An active SOS alert already exists for this job")

    alert = SOSAlert(
        job_id=job_id,
        customer_id=customer_id,
        worker_id=worker_id,
        activated_by_user_id=current_user.id,
        activated_by_role=activated_by_role,
        status="ACTIVE",
        created_at=datetime.utcnow(),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return {"message": "SOS alert activated", **_get_active_sos(db, job_id)}


@app.get("/jobs/{job_id}/sos")
def get_job_sos(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current SOS alert for a job."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Verify caller owns or is assigned to the job
    if current_user.role == "customer":
        customer = get_customer_for_user(db, current_user)
        if customer is None or job.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="You do not own this job")
    elif current_user.role == "worker":
        worker = get_worker_for_user(db, current_user)
        if worker is None or job.worker_id != worker.id:
            raise HTTPException(status_code=403, detail="You are not assigned to this job")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    return _get_active_sos(db, job_id) or {"status": "none"}


@app.post("/sos/{sos_id}/acknowledge")
def acknowledge_sos(
    sos_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acknowledge an active SOS alert. Only the OTHER party (not the one who activated it) can acknowledge."""
    alert = db.get(SOSAlert, sos_id)
    if not alert:
        raise HTTPException(status_code=404, detail="SOS alert not found")
    if alert.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="SOS alert is not active")

    # Determine whether caller has access to this job
    job = db.get(Job, alert.job_id)
    if current_user.role == "customer":
        customer = get_customer_for_user(db, current_user)
        if customer is None or job.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif current_user.role == "worker":
        worker = get_worker_for_user(db, current_user)
        if worker is None or job.worker_id != worker.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return {"message": "SOS alert acknowledged", **_get_active_sos(db, alert.job_id)}


@app.post("/sos/{sos_id}/resolve")
def resolve_sos(
    sos_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resolve an active or acknowledged SOS alert."""
    alert = db.get(SOSAlert, sos_id)
    if not alert:
        raise HTTPException(status_code=404, detail="SOS alert not found")
    if alert.status not in ("ACTIVE", "ACKNOWLEDGED"):
        raise HTTPException(status_code=409, detail="SOS alert cannot be resolved in its current state")

    job = db.get(Job, alert.job_id)
    if current_user.role == "customer":
        customer = get_customer_for_user(db, current_user)
        if customer is None or job.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif current_user.role == "worker":
        worker = get_worker_for_user(db, current_user)
        if worker is None or job.worker_id != worker.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    alert.status = "RESOLVED"
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by_user_id = current_user.id
    db.commit()
    db.refresh(alert)
    return {
        "message": "SOS alert resolved",
        "id": alert.id,
        "job_id": alert.job_id,
        "status": alert.status,
        "resolved_at": alert.resolved_at.isoformat(),
    }


@app.post("/sos/{sos_id}/cancel")
def cancel_sos(
    sos_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel an ACTIVE SOS alert (only by the person who triggered it)."""
    alert = db.get(SOSAlert, sos_id)
    if not alert:
        raise HTTPException(status_code=404, detail="SOS alert not found")
    if alert.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Only ACTIVE alerts can be cancelled")
    if alert.activated_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the person who activated the SOS can cancel it")
    alert.status = "CANCELLED"
    db.commit()
    return {"message": "SOS alert cancelled", "id": alert.id, "status": alert.status}


@app.get("/")
def root():
    return {"app": "Handyman", "status": "running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "product": "HANDYMAN"}


@app.get("/workers")
def workers(db: Session = Depends(get_db)):
    return db.query(Worker).filter(Worker.is_demo == True).all()


@app.get("/workers/{worker_id}")
def worker(worker_id: int, db: Session = Depends(get_db)):
    item = db.get(Worker, worker_id)
    if not item:
        raise HTTPException(404, "Worker not found")
    return item


@app.post("/service-request")
def create_request(payload: ServiceRequestCreate, current_user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    try:
        understood = request_understanding.understand(payload.description, payload.area, payload.service_type)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

    service_type = payload.service_type or understood.service_type
    if service_type not in SERVICES:
        raise HTTPException(400, f"Unsupported service. Choose from: {', '.join(sorted(SERVICES))}")
    area = payload.area or understood.area

    if current_user is not None and current_user.role == "customer":
        customer = get_customer_for_user(db, current_user)
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer profile not found")
        payload.customer_id = customer.id
    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    latitude = payload.latitude if payload.latitude is not None else customer.latitude
    longitude = payload.longitude if payload.longitude is not None else customer.longitude
    item = ServiceRequest(
        customer_id=customer.id,
        service_type=service_type,
        description=payload.description,
        required_skill=service_type,
        area=area,
        latitude=latitude,
        longitude=longitude,
        urgency=payload.urgency or understood.urgency,
        estimated_duration=payload.estimated_duration,
        status="matching",
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    result = match_request(db, item)
    if result["best_match"]:
        item.assigned_worker_id = result["best_match"]["worker_id"]
        item.status = "matched"
        db.commit()

    # ---- Phase A: Telemetry ----
    latency = result.get("matching_latency_ms", 0.0)
    total_workers = result.get("total_workers_considered", 0)
    eligible = result.get("eligible_count", 0)
    ranked = result.get("ranked_candidates", [])

    filter_rate = 1.0 - (eligible / total_workers) if total_workers > 0 else 0.0

    eval_record = MatchingEvaluation(
        request_id=item.id,
        created_at=datetime.utcnow(),
        matching_latency_ms=latency,
        total_workers_considered=total_workers,
        eligible_workers_count=eligible,
        ranked_workers_count=len(ranked),
        candidate_filter_rate=filter_rate
    )

    best = result.get("best_match")
    if best:
        eval_record.recommended_worker_id = best.get("worker_id")
        eval_record.recommended_worker_score = best.get("score")

    for i in range(min(5, len(ranked))):
        setattr(eval_record, f"top_{i+1}_score", ranked[i].get("score"))

    db.add(eval_record)
    db.commit()
    # -----------------------------

    result["request_id"] = item.id
    result["request"] = {
        "description": item.description,
        "service_type": item.service_type,
        "required_skills": understood.required_skills,
        "urgency": item.urgency,
        "area": item.area,
        "latitude": item.latitude,
        "longitude": item.longitude,
        "understanding_source": understood.source,
    }
    return result


@app.post("/match-worker")
def match_worker(payload: MatchRequest, db: Session = Depends(get_db)):
    item = db.get(ServiceRequest, payload.request_id)
    if not item:
        raise HTTPException(404, "Service request not found")
    return match_request(db, item)


@app.post("/accept-job/{request_id}", response_model=ActionResponse)
def accept_job(
    request_id: int,
    selected_worker_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request = db.get(ServiceRequest, request_id)
    if not request:
        raise HTTPException(404, "Matched request not found")
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can assign jobs")
    customer = get_customer_for_user(db, current_user)
    if customer is None or request.customer_id != customer.id:
        raise HTTPException(status_code=403, detail="You do not own this request")
    if selected_worker_id is None:
        selected_worker_id = request.assigned_worker_id
    worker = db.get(Worker, selected_worker_id) if selected_worker_id is not None else None
    if not worker:
        raise HTTPException(404, "Selected worker not found")

    existing_job = db.query(Job).filter(Job.request_id == request.id, Job.status != "rejected").order_by(Job.id.desc()).first()
    if existing_job:
        if existing_job.worker_id != worker.id:
            raise HTTPException(status_code=409, detail="This request is already assigned to another worker")
        return {
            "message": "Job already assigned",
            "job_id": existing_job.id,
            "status": existing_job.status,
            "worker_id": worker.id,
            "worker_name": worker.name,
            "request_id": request.id,
            "description": request.description,
            "service_type": request.service_type,
            "area": request.area,
            "urgency": request.urgency,
        }

    ranked = match_request(db, request)["ranked_candidates"]
    candidate_ids = {item["worker_id"] for item in ranked}
    if selected_worker_id not in candidate_ids:
        raise HTTPException(409, "Selected worker is not among the qualified candidates")
    request.assigned_worker_id = selected_worker_id
    request.status = "assigned"
    amount = max(800.0, float(worker.hourly_rate or 800) * max(1.0, request.estimated_duration / 60))
    job = Job(
        request_id=request.id,
        customer_id=request.customer_id,
        worker_id=worker.id,
        status="assigned",
        assigned_at=datetime.utcnow(),
        amount=amount,
        worker_earning=max(680.0, amount * 0.85),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # ---- Phase A: Telemetry ----
    eval_record = db.query(MatchingEvaluation).filter(MatchingEvaluation.request_id == request.id).first()
    if eval_record:
        eval_record.selected_worker_id = worker.id
        rank = None
        for idx, candidate in enumerate(ranked):
            if candidate["worker_id"] == worker.id:
                rank = idx + 1
                break
        eval_record.selected_worker_rank = rank
        eval_record.recommendation_selected = (worker.id == eval_record.recommended_worker_id)
        db.commit()
    # -----------------------------

    return {
        "message": "Job assigned",
        "job_id": job.id,
        "status": job.status,
        "worker_id": worker.id,
        "worker_name": worker.name,
        "request_id": request.id,
        "description": request.description,
        "service_type": request.service_type,
        "area": request.area,
        "urgency": request.urgency,
    }


@app.post("/jobs/{job_id}/accept")
def accept_worker_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can accept jobs")
    worker = get_worker_for_user(db, current_user)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="This job is not assigned to you")
    if job.status in {"accepted", "in_progress", "completed"}:
        raise HTTPException(status_code=409, detail="This job is not available to accept")
    job.status = "accepted"
    job.accepted_at = datetime.utcnow()
    if job.rejected_at is not None:
        job.rejected_at = None
    worker.current_workload = max(0, worker.current_workload + 1)
    request = db.get(ServiceRequest, job.request_id)
    if request:
        request.status = "accepted"
        request.assigned_worker_id = worker.id
    db.commit()
    return {"message": "Job accepted", "job_id": job.id, "status": job.status, "worker_id": worker.id, "request_id": job.request_id}


@app.post("/jobs/{job_id}/reject")
def reject_worker_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can reject jobs")
    worker = get_worker_for_user(db, current_user)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="This job is not assigned to you")
    if job.status in {"completed", "in_progress"}:
        raise HTTPException(status_code=409, detail="This job cannot be rejected once it is in progress or completed")
    request = db.get(ServiceRequest, job.request_id)
    if request:
        request.status = "rejected"
        request.assigned_worker_id = None
    job.status = "rejected"
    job.rejected_at = datetime.utcnow()
    if job.accepted_at is not None:
        worker.current_workload = max(0, worker.current_workload - 1)
    db.commit()
    return {"message": "Job rejected", "job_id": job.id, "status": job.status, "request_id": job.request_id, "customer_notice": "Worker declined the request."}


@app.post("/jobs/{job_id}/start")
def start_worker_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can start jobs")
    worker = get_worker_for_user(db, current_user)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="This job is not assigned to you")
    if job.status != "accepted":
        raise HTTPException(status_code=409, detail="Only accepted jobs can start")
    job.status = "in_progress"
    job.started_at = datetime.utcnow()
    request = db.get(ServiceRequest, job.request_id)
    if request:
        request.status = "in_progress"
    db.commit()
    return {"message": "Service started", "job_id": job.id, "status": job.status}


@app.post("/jobs/{job_id}/complete")
def complete_worker_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can complete jobs")
    worker = get_worker_for_user(db, current_user)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="This job is not assigned to you")
    if job.status != "in_progress":
        raise HTTPException(status_code=409, detail="Only in-progress jobs can be completed")
    job.status = "completed"
    job.completed_at = datetime.utcnow()
    worker.current_workload = max(0, worker.current_workload - 1)
    worker.jobs_completed = (worker.jobs_completed or 0) + 1
    worker.earnings = float(worker.earnings or 0) + float(job.worker_earning or 0)
    request = db.get(ServiceRequest, job.request_id)
    if request:
        request.status = "completed"
    payment = ensure_payment_for_job(db, job)
    db.commit()
    return {
        "message": "Service completed",
        "job_id": job.id,
        "status": job.status,
        "amount": job.amount,
        "worker_earning": job.worker_earning,
        "payment_id": payment.id,
        "payment_status": payment.status,
    }


@app.post("/start-job/{job_id}", response_model=ActionResponse)
def start_job(job_id: int, current_user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if current_user is not None and current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can start jobs")
    if current_user is None:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.status = "in_progress"
        job.started_at = datetime.utcnow()
        db.commit()
        return {"message": "Service started", "job_id": job.id, "status": job.status}
    return start_worker_job(job_id, current_user, db)


@app.post("/complete-job/{job_id}", response_model=ActionResponse)
def complete_job(job_id: int, current_user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if current_user is not None and current_user.role != "worker":
        raise HTTPException(status_code=403, detail="Only workers can complete jobs")
    if current_user is None:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        request = db.get(ServiceRequest, job.request_id)
        if request:
            request.status = "completed"
        payment = ensure_payment_for_job(db, job)
        db.commit()
        return {
            "message": "Service completed",
            "job_id": job.id,
            "status": job.status,
            "amount": job.amount,
            "worker_earning": job.worker_earning,
            "payment_id": payment.id,
            "payment_status": payment.status,
        }
    return complete_worker_job(job_id, current_user, db)


@app.post("/rate-job/{job_id}")
def rate_job(job_id: int, payload: RatingRequest, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.rating = payload.rating
    db.commit()
    return {"message": "Rating saved", "rating": payload.rating}


@app.get("/jobs")
def jobs(db: Session = Depends(get_db)):
    return db.query(Job).all()


@app.get("/cooperative/dashboard")
def dashboard(db: Session = Depends(get_db)):
    all_workers = db.query(Worker).filter(Worker.is_demo == True).all()
    jobs = db.query(Job).all()
    distribution = [{"service": service, "workers": sum(service.lower() in w.skills.lower() for w in all_workers)} for service in SERVICES]
    coverage = [{"area": area, "available_workers": sum(w.area == area and w.availability for w in all_workers), "demand": 24 + index * 6, "shortage": max(0, 24 + index * 6 - sum(w.area == area and w.availability for w in all_workers))} for index, area in enumerate(AREAS)]
    return {"workforce": {"total": len(all_workers), "active": sum(w.availability for w in all_workers), "available": sum(w.availability for w in all_workers), "busy": sum(not w.availability for w in all_workers), "overloaded": sum(w.current_workload >= 18 for w in all_workers), "verified": sum(w.verification_status == "Verified" for w in all_workers)}, "jobs": {"today": len(jobs) + 18, "completed": sum(j.status == "completed" for j in jobs) + 14, "emergency": 7, "pending": sum(j.status != "completed" for j in jobs)}, "workload": [{"name": w.name, "jobs": w.recent_jobs, "area": w.area} for w in sorted(all_workers, key=lambda x: x.recent_jobs, reverse=True)[:8]], "demand": [{"service": service, "requests": 18 + index * 7} for index, service in enumerate(sorted(SERVICES))], "service_distribution": distribution, "area_coverage": coverage, "proposal": {"title": "Reduce cooperative service allocation from 8% to 6%", "yes": 72, "no": 28}}


@app.get("/demand/forecast")
def forecast(db: Session = Depends(get_db)):
    return get_forecast(db)


import statistics

@app.get("/matching/evaluations", response_model=list[MatchingEvaluationResponse])
def get_matching_evaluations(
    limit: int = Query(default=100, le=5000),
    offset: int = 0,
    source: str = Query(default="all"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(MatchingEvaluation)
    if source != "all":
        query = query.filter(MatchingEvaluation.source == source)
    evals = query.order_by(MatchingEvaluation.id.desc()).offset(offset).limit(limit).all()
    return evals

@app.get("/matching/evaluation-summary", response_model=MatchingEvaluationSummary)
def get_matching_evaluation_summary(
    source: str = Query(default="all"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(MatchingEvaluation)
    if source != "all":
        query = query.filter(MatchingEvaluation.source == source)
    evals = query.all()
    total = len(evals)

    if total == 0:
        return {
            "total_evaluations": 0,
            "top_1_selection_rate": None,
            "top_3_selection_rate": None,
            "top_5_selection_rate": None,
            "ai_recommendation_acceptance_rate": None,
            "alternative_selection_rate": None,
            "average_latency_ms": None,
            "p50_latency_ms": None,
            "p95_latency_ms": None,
            "p99_latency_ms": None,
            "average_match_score": None,
            "average_eligible_candidates": None,
            "average_candidate_filter_rate": None,
            "no_match_rate": None,
        }

    latencies = sorted([e.matching_latency_ms for e in evals])
    filter_rates = [e.candidate_filter_rate for e in evals]
    eligible_counts = [e.eligible_workers_count for e in evals]

    def percentile(data, p):
        n = len(data)
        if n == 0: return None
        k = (n - 1) * p
        f = int(k)
        c = int(k) + 1 if f < (n - 1) else f
        if f == c: return data[f]
        d0 = data[f] * (c - k)
        d1 = data[c] * (k - f)
        return d0 + d1

    avg_latency = statistics.mean(latencies)
    p50 = percentile(latencies, 0.5)
    p95 = percentile(latencies, 0.95)
    p99 = percentile(latencies, 0.99)

    avg_filter_rate = statistics.mean(filter_rates)
    avg_eligible = statistics.mean(eligible_counts)

    no_matches = sum(1 for e in evals if e.recommended_worker_id is None)
    no_match_rate = no_matches / total

    scores = [e.recommended_worker_score for e in evals if e.recommended_worker_score is not None]
    avg_score = statistics.mean(scores) if scores else None

    # Selections
    selections = [e for e in evals if e.selected_worker_id is not None]
    total_selections = len(selections)

    if total_selections > 0:
        top1 = sum(1 for e in selections if e.selected_worker_rank == 1) / total_selections
        top3 = sum(1 for e in selections if e.selected_worker_rank is not None and e.selected_worker_rank <= 3) / total_selections
        top5 = sum(1 for e in selections if e.selected_worker_rank is not None and e.selected_worker_rank <= 5) / total_selections
        ai_accept = sum(1 for e in selections if e.recommendation_selected == True) / total_selections
        alt_accept = sum(1 for e in selections if e.recommendation_selected == False) / total_selections
    else:
        top1 = top3 = top5 = ai_accept = alt_accept = None

    return {
        "total_evaluations": total,
        "top_1_selection_rate": top1,
        "top_3_selection_rate": top3,
        "top_5_selection_rate": top5,
        "ai_recommendation_acceptance_rate": ai_accept,
        "alternative_selection_rate": alt_accept,
        "average_latency_ms": avg_latency,
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "p99_latency_ms": p99,
        "average_match_score": avg_score,
        "average_eligible_candidates": avg_eligible,
        "average_candidate_filter_rate": avg_filter_rate,
        "no_match_rate": no_match_rate,
    }


@app.post("/matching/benchmark/run")
def execute_benchmark(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = run_benchmark(db, run_id="benchmark_v1", count=1000)
    return result
