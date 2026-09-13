from math import sqrt
from time import perf_counter
from sqlalchemy.orm import Session
from ..models import ServiceRequest, Worker

WEIGHTS = {"skill_match": .35, "availability": .20, "distance": .15, "urgency": .10, "workload_balance": .10, "fair_opportunity": .10, "rating": .10}
SKILL_ALIASES = {
    "electrician": "electrical",
    "electricians": "electrical",
    "plumber": "plumbing",
    "plumbers": "plumbing",
    "carpenter": "carpentry",
    "carpenters": "carpentry",
    "painter": "painting",
    "painters": "painting",
    "cleaner": "cleaning",
    "cleaners": "cleaning",
    "appliance technician": "appliance repair",
    "appliance technicians": "appliance repair",
}


def canonical_skill(value: str) -> str:
    normalized = value.strip().lower()
    return SKILL_ALIASES.get(normalized, normalized)


def distance_km(request: ServiceRequest, worker: Worker):
    if request.latitude is None or request.longitude is None or worker.latitude is None or worker.longitude is None:
        return None
    return round(sqrt((request.latitude - worker.latitude) ** 2 + (request.longitude - worker.longitude) ** 2) * 111, 1)


def worker_eligible(request: ServiceRequest, worker: Worker):
    skills = {canonical_skill(item) for item in worker.skills.split(",") if item.strip()}
    required = canonical_skill(request.required_skill)
    if required not in skills:
        return False, "Skill mismatch"
    if worker.verification_status != "Verified":
        return False, "Verification pending"

    status = getattr(worker, "availability_status", None)
    if status not in {"Available", "Unavailable"}:
        status = "Available" if getattr(worker, "availability", True) else "Unavailable"
    if not getattr(worker, "availability", True) and status == "Available":
        status = "Unavailable"
    if status != "Available":
        return False, f"Availability is {status}"

    capacity = max(1, worker.max_concurrent_jobs or 3)
    if worker.current_workload >= capacity:
        return False, f"Workload at capacity ({worker.current_workload}/{capacity})"
    return True, "Eligible"


def score_worker(request: ServiceRequest, worker: Worker):
    eligible, reason = worker_eligible(request, worker)
    if not eligible:
        return None

    distance = distance_km(request, worker)
    skills = {canonical_skill(item) for item in worker.skills.split(",") if item.strip()}
    required = canonical_skill(request.required_skill)
    certifications = (worker.certifications or "").lower()
    skill = 100 if required in skills else 0
    availability = 100 if worker.availability_status == "Available" else 0
    distance_score = 100 if distance is None else max(15, round(100 - distance * 12))
    urgency = 100 if request.urgency == "emergency" else 80
    capacity = max(1, worker.max_concurrent_jobs or 3)
    workload = max(0, min(100, 100 - (worker.current_workload / capacity) * 100))
    rating_score = max(0, min(100, round((worker.rating / 5) * 100)))
    fairness = max(15, 100 - worker.recent_jobs * 3)
    components = {
        "skill_match": skill,
        "availability": availability,
        "distance": distance_score,
        "urgency": urgency,
        "workload_balance": workload,
        "fair_opportunity": fairness,
        "rating": rating_score,
    }
    total = max(0, min(100, round(sum(components[key] * weight for key, weight in WEIGHTS.items()))))
    reasons = [
        f"Required {request.required_skill.lower()} skill verified" if required in certifications else f"Required {request.required_skill.lower()} skill matched",
        "Available immediately" if worker.availability_status == "Available" else "Not available",
    ]
    if distance is not None:
        reasons.append(f"{distance} km away")
    else:
        reasons.append("Distance unavailable")
    reasons.append(f"Current workload: {worker.current_workload}/{capacity}")
    reasons.append(f"{worker.rating}★ rating")
    if fairness >= 60:
        reasons.append("Strong fairness opportunity score")
    eta_minutes = max(7, round((distance or 15) * 4 + 3)) if distance is not None else None
    return {
        "worker_id": worker.id,
        "name": worker.name,
        "score": total,
        "final_score": total,
        "eta_minutes": eta_minutes,
        "distance_km": distance,
        "rating": worker.rating,
        "components": components,
        **{f"{key}_score": value for key, value in components.items()},
        "reasons": reasons,
        "eligibility": reason,
    }


def match_request(db: Session, request: ServiceRequest, override_workers=None):
    started = perf_counter()
    workers = override_workers if override_workers is not None else db.query(Worker).all()
    candidate_time = perf_counter()
    ranked = [result for worker in workers if (result := score_worker(request, worker))]
    scoring_time = perf_counter()
    ranked.sort(key=lambda item: item["score"], reverse=True)
    elapsed_ms = (perf_counter() - started) * 1000
    candidate_ms = (candidate_time - started) * 1000
    scoring_ms = (scoring_time - candidate_time) * 1000
    if not ranked:
        return {
            "best_match": None,
            "alternatives": [],
            "ranked_candidates": [],
            "eligible_count": 0,
            "total_workers_considered": len(workers),
            "message": "No qualified available worker found.",
            "weights": WEIGHTS,
            "matching_latency_ms": round(elapsed_ms, 2),
            "candidate_retrieval_ms": round(candidate_ms, 2),
            "candidate_scoring_ms": round(scoring_ms, 2),
        }
    return {
        "best_match": ranked[0],
        "alternatives": ranked[1:4],
        "ranked_candidates": ranked,
        "eligible_count": len(ranked),
        "total_workers_considered": len(workers),
        "message": "Explainable AI-based Cooperative Worker Matching Engine",
        "weights": WEIGHTS,
        "matching_latency_ms": round(elapsed_ms, 2),
        "candidate_retrieval_ms": round(candidate_ms, 2),
        "candidate_scoring_ms": round(scoring_ms, 2),
    }
