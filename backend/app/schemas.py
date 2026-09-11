from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

SERVICES = {"Plumbing", "Electrical", "Carpentry", "Cleaning", "Painting", "Appliance Repair"}

class ServiceRequestCreate(BaseModel):
    customer_id: int = 1
    service_type: str
    description: str = Field(min_length=8, max_length=500)
    area: str
    latitude: float
    longitude: float
    urgency: Literal["normal", "emergency"] = "normal"
    estimated_duration: int = Field(default=60, ge=15, le=480)

class MatchRequest(BaseModel):
    request_id: int

class ActionResponse(BaseModel):
    message: str
    job_id: int
    status: str

class RatingRequest(BaseModel):
    rating: float = Field(ge=1, le=5)
