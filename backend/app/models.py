from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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
    current_workload: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=4.5)
    jobs_completed: Mapped[int] = mapped_column(Integer, default=0)
    earnings: Mapped[float] = mapped_column(Float, default=0)
    verification_status: Mapped[str] = mapped_column(String(30), default="Verified")
    recent_jobs: Mapped[int] = mapped_column(Integer, default=0)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    area: Mapped[str] = mapped_column(String(40))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


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
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)


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
