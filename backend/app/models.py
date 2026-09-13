from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="customer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    cooperative_id: Mapped[str] = mapped_column(String(40), default="COOP-A")
    skills: Mapped[str] = mapped_column(String(300))
    certifications: Mapped[str] = mapped_column(String(300), default="")
    experience_years: Mapped[int] = mapped_column(Integer, default=1)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    area: Mapped[str] = mapped_column(String(40))
    availability: Mapped[bool] = mapped_column(Boolean, default=True)
    availability_status: Mapped[str] = mapped_column(String(20), default="Available")
    current_workload: Mapped[int] = mapped_column(Integer, default=0)
    max_concurrent_jobs: Mapped[int] = mapped_column(Integer, default=3)
    available_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status_update: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)
    rating: Mapped[float] = mapped_column(Float, default=4.5)
    jobs_completed: Mapped[int] = mapped_column(Integer, default=0)
    earnings: Mapped[float] = mapped_column(Float, default=0)
    verification_status: Mapped[str] = mapped_column(String(30), default="Verified")
    recent_jobs: Mapped[int] = mapped_column(Integer, default=0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    service_areas: Mapped[str] = mapped_column(String(200), default="")
    hourly_rate: Mapped[float] = mapped_column(Float, default=0)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str] = mapped_column(String(20))
    area: Mapped[str] = mapped_column(String(40))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    service_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    required_skill: Mapped[str] = mapped_column(String(60))
    area: Mapped[str] = mapped_column(String(40))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    urgency: Mapped[str] = mapped_column(String(20), default="normal")
    estimated_duration: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(30), default="matching")
    assigned_worker_id: Mapped[int | None] = mapped_column(ForeignKey("workers.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("service_requests.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id"))
    status: Mapped[str] = mapped_column(String(30), default="assigned")
    amount: Mapped[float] = mapped_column(Float, default=800)
    worker_earning: Mapped[float] = mapped_column(Float, default=680)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id"))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(40), default="pending")
    payment_method: Mapped[str] = mapped_column(String(30), default="UPI_QR")
    upi_id: Mapped[str] = mapped_column(String(100))
    transaction_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    qr_payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Demand(Base):
    __tablename__ = "demand"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(20))
    area: Mapped[str] = mapped_column(String(40))
    service_type: Mapped[str] = mapped_column(String(40))
    request_count: Mapped[int] = mapped_column(Integer)
    emergency_requests: Mapped[int] = mapped_column(Integer)
    average_duration: Mapped[int] = mapped_column(Integer)


class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    yes_votes: Mapped[int] = mapped_column(Integer)
    no_votes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="Open")


class SOSAlert(Base):
    __tablename__ = "sos_alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id"))
    activated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    activated_by_role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

class MatchingEvaluation(Base):
    __tablename__ = "matching_evaluations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source: Mapped[str] = mapped_column(String(20), default="live")
    benchmark_run_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    request_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    matching_latency_ms: Mapped[float] = mapped_column(Float)
    total_workers_considered: Mapped[int] = mapped_column(Integer)
    eligible_workers_count: Mapped[int] = mapped_column(Integer)
    ranked_workers_count: Mapped[int] = mapped_column(Integer)

    recommended_worker_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended_worker_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    top_1_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_2_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_3_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_4_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_5_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    selected_worker_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_worker_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation_selected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    ground_truth_worker_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_filter_rate: Mapped[float] = mapped_column(Float)
