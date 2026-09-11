from math import sqrt
from sqlalchemy.orm import Session
from ..models import ServiceRequest, Worker

WEIGHTS = {"skill_match": .35, "availability": .20, "distance": .15, "urgency": .10, "workload_balance": .10, "fair_opportunity": .10}


def distance_km(request: ServiceRequest, worker: Worker) -> float:
    return round(sqrt((request.latitude - worker.latitude) ** 2 + (request.longitude - worker.longitude) ** 2) * 111, 1)


def score_worker(request: ServiceRequest, worker: Worker):
    skills = {item.strip().lower() for item in worker.skills.split(",")}
    required = request.required_skill.lower()
    if required not in skills or not worker.availability or worker.verification_status != "Verified":
        return None
    distance = distance_km(request, worker)
    skill = 100 if required in skills and required in worker.certifications.lower() else 88
    availability = 100
    distance_score = max(15, round(100 - distance * 12))
    urgency = max(50, round(100 - distance * 8)) if request.urgency == "emergency" else 75
    workload = max(10, 100 - worker.current_workload * 4)
    fairness = max(15, 100 - worker.recent_jobs * 3)
    components = {"skill_match": skill, "availability": availability, "distance": distance_score, "urgency": urgency, "workload_balance": workload, "fair_opportunity": fairness}
    total = round(sum(components[key] * weight for key, weight in WEIGHTS.items()))
    reasons = [f"Required {request.required_skill.lower()} skill verified", "Available immediately", f"{distance} km away"]
    if workload >= 70: reasons.append("Low current workload")
    if fairness >= 60: reasons.append("Good fair-opportunity score")
    return {"worker_id": worker.id, "name": worker.name, "score": total, "eta_minutes": max(7, round(distance * 4 + 3)), "distance_km": distance, "rating": worker.rating, "components": components, "reasons": reasons}


def match_request(db: Session, request: ServiceRequest):
    workers = db.query(Worker).all()
    ranked = [result for worker in workers if (result := score_worker(request, worker))]
    ranked.sort(key=lambda item: item["score"], reverse=True)
    if not ranked:
        return {"best_match": None, "alternatives": [], "message": "No qualified available worker found.", "weights": WEIGHTS}
    return {"best_match": ranked[0], "alternatives": ranked[1:4], "message": "Explainable AI-based Cooperative Worker Matching Engine", "weights": WEIGHTS}
