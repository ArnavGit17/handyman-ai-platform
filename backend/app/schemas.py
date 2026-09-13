from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

SERVICES = {"Plumbing", "Electrical", "Carpentry", "Cleaning", "Painting", "Appliance Repair"}

class AuthRegister(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=4, max_length=120)
    phone: str | None = None
    password: str = Field(min_length=6, max_length=80)
    role: Literal["customer", "worker"] = "customer"
    skill: str | None = None
    skills: str | None = None
    certifications: str | None = None
    experience: int | None = None
    service_areas: list[str] = []
    area: str | None = None
    location: dict | None = None
    availability: bool | None = None
    availability_status: Literal["Available", "Unavailable"] | None = None
    max_concurrent_jobs: int | None = None
    rate: float | None = None

class AuthLogin(BaseModel):
    email: str
    password: str

class CustomerProfileUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    area: str | None = None
    latitude: float | None = None
    longitude: float | None = None

class WorkerProfileUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    skills: str | None = None
    certifications: str | None = None
    experience_years: int | None = None
    service_areas: list[str] | None = None
    area: str | None = None
    availability: bool | None = None
    availability_status: Literal["Available", "Unavailable"] | None = None
    max_concurrent_jobs: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    hourly_rate: float | None = None

class WorkerAvailabilityUpdate(BaseModel):
    availability_status: Literal["Available", "Unavailable"]

class ServiceRequestCreate(BaseModel):
    customer_id: int = 1
    description: str = Field(min_length=8, max_length=500)
    service_type: str | None = None
    area: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    urgency: Literal["normal", "emergency"] | None = None
    estimated_duration: int = Field(default=60, ge=15, le=480)

class MatchRequest(BaseModel):
    request_id: int

class ActionResponse(BaseModel):
    message: str
    job_id: int
    status: str
    amount: float | None = None
    worker_earning: float | None = None
    payment_id: int | None = None
    payment_status: str | None = None
    worker_id: int | None = None
    worker_name: str | None = None
    request_id: int | None = None
    description: str | None = None
    service_type: str | None = None
    area: str | None = None
    urgency: str | None = None

class RatingRequest(BaseModel):
    rating: float = Field(ge=1, le=5)


class PaymentConfirm(BaseModel):
    transaction_reference: str = Field(min_length=1, max_length=100)


class SOSAlertResponse(BaseModel):
    id: int
    job_id: int
    customer_id: int
    worker_id: int
    activated_by_user_id: int
    activated_by_role: str
    status: str
    created_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by_user_id: int | None = None

class MatchingEvaluationResponse(BaseModel):
    id: int
    source: str = "live"
    benchmark_run_id: str | None = None
    request_id: int | None = None
    created_at: datetime
    matching_latency_ms: float
    total_workers_considered: int
    eligible_workers_count: int
    ranked_workers_count: int
    recommended_worker_id: int | None = None
    recommended_worker_score: int | None = None
    top_1_score: int | None = None
    top_2_score: int | None = None
    top_3_score: int | None = None
    top_4_score: int | None = None
    top_5_score: int | None = None
    selected_worker_id: int | None = None
    selected_worker_rank: int | None = None
    recommendation_selected: bool | None = None
    ground_truth_worker_id: int | None = None
    candidate_filter_rate: float

class MatchingEvaluationSummary(BaseModel):
    total_evaluations: int
    top_1_selection_rate: float | None
    top_3_selection_rate: float | None
    top_5_selection_rate: float | None
    ai_recommendation_acceptance_rate: float | None
    alternative_selection_rate: float | None
    average_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    p99_latency_ms: float | None
    average_match_score: float | None
    average_eligible_candidates: float | None
    average_candidate_filter_rate: float | None
    no_match_rate: float | None
