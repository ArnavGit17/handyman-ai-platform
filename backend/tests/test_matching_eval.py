import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import MatchingEvaluation
import random
import string

client = TestClient(app)

def register_and_login(email, password, role, name="Test User", skills=None):
    payload = {
        "name": name, "email": email, "phone": "9876543210",
        "password": password, "role": role, "area": "Area A",
        "skills": skills if role == "worker" else None,
        "certifications": f"{skills} Cert" if role == "worker" else None,
        "service_areas": ["Area A"], "experience": 3, "rate": 700, "availability": True,
    }
    client.post("/auth/register", json=payload)
    resp = client.post("/auth/login", json={"email": email, "password": password})
    data = resp.json()
    return data.get("access_token"), data.get("user", {})

@pytest.fixture
def test_users():
    uid = "".join(random.choices(string.ascii_lowercase, k=6))
    c_token, c_user = register_and_login(f"eval_c_{uid}@test.com", "pass1234", "customer", f"Eval C {uid}")
    w_token_1, w_user_1 = register_and_login(f"eval_w1_{uid}@test.com", "pass1234", "worker", f"Eval W1 {uid}", skills="Electrical")
    w_token_2, w_user_2 = register_and_login(f"eval_w2_{uid}@test.com", "pass1234", "worker", f"Eval W2 {uid}", skills="Electrical")
    w_token_3, w_user_3 = register_and_login(f"eval_w3_{uid}@test.com", "pass1234", "worker", f"Eval W3 {uid}", skills="Plumbing")
    
    p = client.get("/customers/me", headers={"Authorization": f"Bearer {c_token}"}).json()
    customer_id = p["id"]

    return {
        "c_token": c_token,
        "customer_id": customer_id,
        "workers": [w_user_1, w_user_2, w_user_3]
    }

def test_matching_evaluation_creation(test_users):
    c_token = test_users["c_token"]
    
    # 1. Matching creates evaluation record.
    resp = client.post(
        "/service-request",
        json={
            "description": "Fix electrical wiring",
            "service_type": "Electrical",
            "area": "Area A",
            "latitude": 12.97,
            "longitude": 77.59,
            "urgency": "normal",
            "estimated_duration": 60,
        },
        headers={"Authorization": f"Bearer {c_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    request_id = data["request_id"]
    best_match_id = data["best_match"]["worker_id"]

    # 2. Evaluation stores matching latency, candidate counts, recommended worker, top-5 scores.
    evals_resp = client.get("/matching/evaluations", headers={"Authorization": f"Bearer {c_token}"})
    assert evals_resp.status_code == 200
    evals = evals_resp.json()
    
    # Find the evaluation for this request
    my_eval = next((e for e in evals if e["request_id"] == request_id), None)
    assert my_eval is not None
    
    # Asserting stored fields
    assert my_eval["matching_latency_ms"] >= 0
    assert my_eval["total_workers_considered"] > 0
    assert my_eval["eligible_workers_count"] >= 2  # Two electrical workers
    assert my_eval["ranked_workers_count"] >= 2
    assert my_eval["recommended_worker_id"] == best_match_id
    assert my_eval["top_1_score"] is not None
    assert my_eval["top_2_score"] is not None
    assert my_eval["candidate_filter_rate"] >= 0.0

def test_no_match_evaluation(test_users):
    c_token = test_users["c_token"]
    
    # 9. No-match request creates evaluation.
    resp = client.post(
        "/service-request",
        json={
            "description": "Need a very obscure skill",
            "service_type": "Appliance Repair",
            "area": "Nowhere",
            "latitude": 89.0,
            "longitude": 179.0,
            "urgency": "normal",
            "estimated_duration": 60,
        },
        headers={"Authorization": f"Bearer {c_token}"},
    )
    data = resp.json()
    request_id = data.get("request_id")
    assert request_id is not None
    
    evals_resp = client.get("/matching/evaluations", headers={"Authorization": f"Bearer {c_token}"})
    my_eval = next((e for e in evals_resp.json() if e["request_id"] == request_id), None)
    assert my_eval is not None
    assert my_eval["matching_latency_ms"] >= 0
    assert my_eval["total_workers_considered"] > 0
    assert my_eval["eligible_workers_count"] >= 0
    assert my_eval["candidate_filter_rate"] >= 0.0
    
def test_customer_selection_updates_evaluation(test_users):
    c_token = test_users["c_token"]
    
    resp = client.post(
        "/service-request",
        json={
            "description": "Electrical issue again",
            "service_type": "Electrical",
            "area": "Area A",
            "latitude": 12.97,
            "longitude": 77.59,
        },
        headers={"Authorization": f"Bearer {c_token}"},
    )
    data = resp.json()
    request_id = data["request_id"]
    best_match_id = data["best_match"]["worker_id"]
    
    # 10. Customer selecting recommended worker sets: recommendation_selected = true
    client.post(
        f"/accept-job/{request_id}",
        params={"selected_worker_id": best_match_id},
        headers={"Authorization": f"Bearer {c_token}"},
    )
    
    evals_resp = client.get("/matching/evaluations", headers={"Authorization": f"Bearer {c_token}"})
    my_eval = next((e for e in evals_resp.json() if e["request_id"] == request_id), None)
    assert my_eval["selected_worker_id"] == best_match_id
    assert my_eval["selected_worker_rank"] == 1
    assert my_eval["recommendation_selected"] == True

def test_alternative_selection(test_users):
    c_token = test_users["c_token"]
    
    resp = client.post(
        "/service-request",
        json={
            "description": "Another electrical issue",
            "service_type": "Electrical",
            "area": "Area A",
            "latitude": 12.97,
            "longitude": 77.59,
        },
        headers={"Authorization": f"Bearer {c_token}"},
    )
    data = resp.json()
    request_id = data["request_id"]
    ranked = data["ranked_candidates"]
    
    if len(ranked) > 1:
        alt_worker_id = ranked[1]["worker_id"]
        
        # 11. Customer selecting second-ranked worker sets: recommendation_selected = false
        client.post(
            f"/accept-job/{request_id}",
            params={"selected_worker_id": alt_worker_id},
            headers={"Authorization": f"Bearer {c_token}"},
        )
        
        evals_resp = client.get("/matching/evaluations", headers={"Authorization": f"Bearer {c_token}"})
        my_eval = next((e for e in evals_resp.json() if e["request_id"] == request_id), None)
        assert my_eval["selected_worker_id"] == alt_worker_id
        assert my_eval["selected_worker_rank"] == 2
        assert my_eval["recommendation_selected"] == False

def test_aggregate_metrics_endpoint(test_users):
    c_token = test_users["c_token"]
    resp = client.get("/matching/evaluation-summary", headers={"Authorization": f"Bearer {c_token}"})
    assert resp.status_code == 200
    summary = resp.json()
    
    # Metrics should be populated
    assert summary["total_evaluations"] > 0
    assert summary["average_latency_ms"] is not None
    assert summary["p50_latency_ms"] is not None
    assert summary["p95_latency_ms"] is not None
    assert summary["p99_latency_ms"] is not None
    assert summary["average_match_score"] is not None
    assert summary["average_eligible_candidates"] is not None
    assert summary["average_candidate_filter_rate"] is not None
    assert summary["no_match_rate"] is not None

def test_unauthorized_access():
    resp = client.get("/matching/evaluations")
    assert resp.status_code == 401
    
    resp = client.get("/matching/evaluation-summary")
    assert resp.status_code == 401
