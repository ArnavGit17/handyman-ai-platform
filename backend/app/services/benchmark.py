import random
from typing import List, Tuple
from sqlalchemy.orm import Session
from ..models import Worker, ServiceRequest, MatchingEvaluation
from .matching import match_request

SERVICES = [
    "Electrical", "Plumbing", "Carpentry", "Cleaning", 
    "Painting", "Appliance Repair", "HVAC/AC", "Pest Control"
]
AREAS = ["Area A", "Area B", "Area C", "Area D", "Area E"]

def generate_worker(worker_id: int, rng: random.Random) -> Worker:
    w = Worker()
    w.id = worker_id
    w.name = f"Benchmark Worker {worker_id}"
    w.phone = "555-0000"
    
    # 20% chance of multiple skills
    num_skills = 2 if rng.random() < 0.2 else 1
    w.skills = ",".join(rng.sample(SERVICES, num_skills))
    
    w.area = rng.choice(AREAS)
    w.latitude = rng.uniform(12.9, 13.0)
    w.longitude = rng.uniform(77.5, 77.6)
    
    w.availability = rng.random() < 0.9  # 90% chance available
    w.availability_status = "Available" if w.availability else "Unavailable"
    
    w.max_concurrent_jobs = rng.randint(2, 5)
    w.current_workload = rng.randint(0, w.max_concurrent_jobs)
    
    w.rating = round(rng.uniform(3.5, 5.0), 1)
    w.recent_jobs = rng.randint(0, 20)
    w.verification_status = "Verified" if rng.random() < 0.95 else "Pending"
    
    return w

def run_benchmark(db: Session, run_id: str = "benchmark_v1", count: int = 1000):
    # Clear previous benchmark data for this run_id to avoid unbounded growth
    db.query(MatchingEvaluation).filter(MatchingEvaluation.benchmark_run_id == run_id).delete()
    db.commit()

    rng = random.Random(42)  # Fixed seed for reproducibility

    for i in range(count):
        # 1. Construct Request
        req = ServiceRequest()
        req.id = i + 100000 # Pseudo ID
        req.required_skill = rng.choice(SERVICES)
        req.area = rng.choice(AREAS)
        req.latitude = rng.uniform(12.9, 13.0)
        req.longitude = rng.uniform(77.5, 77.6)
        req.urgency = "emergency" if rng.random() < 0.1 else "normal"
        
        # 2. Construct Worker Pool
        # Vary pool size to simulate strong/moderate/low/no-match scenarios
        # 5% No match (very few workers), 15% low, 60% moderate, 20% highly competitive
        pool_type = rng.random()
        if pool_type < 0.05:
            pool_size = rng.randint(1, 3)
        elif pool_type < 0.20:
            pool_size = rng.randint(4, 10)
        elif pool_type < 0.80:
            pool_size = rng.randint(11, 30)
        else:
            pool_size = rng.randint(31, 100)
            
        pool = [generate_worker(w_id, rng) for w_id in range(1, pool_size + 1)]
        
        # 3. Define Ground Truth
        # Ground truth is the 'conceptually best' worker based on hard heuristics.
        # Must be verified, available, matching skill.
        # Then sorted by: distance (ascending), rating (descending).
        eligible = []
        for w in pool:
            if w.verification_status != "Verified": continue
            if w.availability_status != "Available": continue
            if w.current_workload >= w.max_concurrent_jobs: continue
            
            # Skill match
            skills = [s.strip().lower() for s in w.skills.split(",")]
            if req.required_skill.lower() not in skills: continue
            
            # Distance
            dist = ((req.latitude - w.latitude)**2 + (req.longitude - w.longitude)**2)**0.5
            eligible.append((w, dist))
            
        ground_truth_worker_id = None
        if eligible:
            # Sort by distance (asc), then rating (desc)
            eligible.sort(key=lambda x: (x[1], -x[0].rating))
            ground_truth_worker_id = eligible[0][0].id

        # 4. Run Matching Engine
        result = match_request(db, req, override_workers=pool)
        
        # 5. Extract Metrics
        ranked_candidates = result.get("ranked_candidates", [])
        
        top_scores = [None] * 5
        for idx in range(min(5, len(ranked_candidates))):
            top_scores[idx] = ranked_candidates[idx]["score"]
            
        gt_rank = None
        if ground_truth_worker_id is not None:
            for idx, c in enumerate(ranked_candidates):
                if c["worker_id"] == ground_truth_worker_id:
                    gt_rank = idx + 1
                    break
                    
        eval_record = MatchingEvaluation(
            source="benchmark",
            benchmark_run_id=run_id,
            request_id=-1, # Pseudo requests aren't saved, -1 avoids sqlite NOT NULL error
            matching_latency_ms=result.get("matching_latency_ms", 0),
            total_workers_considered=result.get("total_workers_considered", 0),
            eligible_workers_count=result.get("eligible_count", 0),
            ranked_workers_count=len(ranked_candidates),
            
            recommended_worker_id=ranked_candidates[0]["worker_id"] if ranked_candidates else None,
            recommended_worker_score=ranked_candidates[0]["score"] if ranked_candidates else None,
            
            top_1_score=top_scores[0],
            top_2_score=top_scores[1],
            top_3_score=top_scores[2],
            top_4_score=top_scores[3],
            top_5_score=top_scores[4],
            
            selected_worker_id=ground_truth_worker_id,
            selected_worker_rank=gt_rank,
            recommendation_selected=None, # Explicitly None for benchmark
            ground_truth_worker_id=ground_truth_worker_id,
            
            candidate_filter_rate=0.0
        )
        
        if eval_record.total_workers_considered > 0:
            eliminated = eval_record.total_workers_considered - eval_record.eligible_workers_count
            eval_record.candidate_filter_rate = eliminated / eval_record.total_workers_considered
            
        db.add(eval_record)
        
        # Periodically commit to keep memory low
        if (i + 1) % 100 == 0:
            db.commit()

    db.commit()
    return {"message": f"Benchmark {run_id} completed", "scenarios": count}
