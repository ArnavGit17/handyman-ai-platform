"""
Tests for SOS / Safety alert system.
"""
import random
import string

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def register_and_login(email, password, role, name="Test User"):
    payload = {
        "name": name, "email": email, "phone": "9876543210",
        "password": password, "role": role, "area": "Area A",
        "skills": "Plumbing" if role == "worker" else None,
        "certifications": "Safety" if role == "worker" else None,
        "service_areas": ["Area A"], "experience": 3, "rate": 700, "availability": True,
    }
    client.post("/auth/register", json=payload)
    resp = client.post("/auth/login", json={"email": email, "password": password})
    data = resp.json()
    return data.get("access_token"), data.get("user", {})


def create_active_job(c_token, w_token, customer_id):
    """
    Create a Plumbing job in Area A, explicitly assigning it to the test worker.
    The test worker is registered with Plumbing / Area A so they will appear
    in ranked_candidates.  We look up their worker ID first to force-select them.
    """
    # Resolve the registered test-worker's DB id
    w_profile = client.get("/workers/me", headers={"Authorization": f"Bearer {w_token}"}).json()
    w_id = w_profile["id"]

    # Create service request
    resp = client.post(
        "/service-request",
        json={
            "description": "Pipe leaking urgently",
            "service_type": "Plumbing",
            "area": "Area A",
            "latitude": 12.97,
            "longitude": 77.59,
            "urgency": "normal",
            "estimated_duration": 60,
            "customer_id": customer_id,
        },
        headers={"Authorization": f"Bearer {c_token}"},
    )
    data = resp.json()
    request_id = data["request_id"]

    # Assign to our test worker (they should be in ranked_candidates)
    resp2 = client.post(
        f"/accept-job/{request_id}",
        params={"selected_worker_id": w_id},
        headers={"Authorization": f"Bearer {c_token}"},
    )
    job_id = resp2.json().get("job_id")
    assert job_id, f"Job creation failed: {resp2.json()}"

    # Worker accepts then starts
    client.post(f"/jobs/{job_id}/accept", headers={"Authorization": f"Bearer {w_token}"})
    client.post(f"/jobs/{job_id}/start",  headers={"Authorization": f"Bearer {w_token}"})
    return job_id


@pytest.fixture
def setup():
    uid = "".join(random.choices(string.ascii_lowercase, k=6))
    c_token, c_user = register_and_login(
        f"sos_c_{uid}@test.com", "pass1234", "customer", f"SOS C {uid}"
    )
    w_token, w_user = register_and_login(
        f"sos_w_{uid}@test.com", "pass1234", "worker", f"SOS W {uid}"
    )
    customer_id = c_user.get("customer_id") or c_user.get("id")
    if not customer_id:
        p = client.get("/customers/me", headers={"Authorization": f"Bearer {c_token}"}).json()
        customer_id = p["id"]
    return {"c_token": c_token, "w_token": w_token, "customer_id": customer_id}


# -- activation ----------------------------------------------------------------

def test_customer_can_activate_sos(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    resp = client.post(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ACTIVE"
    assert resp.json()["activated_by_role"] == "customer"


def test_worker_can_activate_sos(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    resp = client.post(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['w_token']}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["activated_by_role"] == "worker"


def test_duplicate_active_sos_rejected(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    client.post(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"})
    resp = client.post(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"})
    assert resp.status_code == 409


def test_unauthenticated_sos_rejected(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    resp = client.post(f"/jobs/{job_id}/sos")
    assert resp.status_code == 401


def test_unrelated_customer_cannot_activate(setup):
    uid = "".join(random.choices(string.ascii_lowercase, k=6))
    other_token, _ = register_and_login(
        f"other_{uid}@test.com", "pass1234", "customer", f"Other {uid}"
    )
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    resp = client.post(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code in (403, 404)


# -- lifecycle ----------------------------------------------------------------

def test_worker_can_acknowledge_customer_sos(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    sos = client.post(
        f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"}
    ).json()
    resp = client.post(
        f"/sos/{sos['id']}/acknowledge", headers={"Authorization": f"Bearer {setup['w_token']}"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ACKNOWLEDGED"


def test_customer_can_acknowledge_worker_sos(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    sos = client.post(
        f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['w_token']}"}
    ).json()
    resp = client.post(
        f"/sos/{sos['id']}/acknowledge", headers={"Authorization": f"Bearer {setup['c_token']}"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ACKNOWLEDGED"


def test_resolve_sos(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    sos = client.post(
        f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"}
    ).json()
    resp = client.post(
        f"/sos/{sos['id']}/resolve", headers={"Authorization": f"Bearer {setup['c_token']}"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "RESOLVED"


def test_cancel_sos_by_activator(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    sos = client.post(
        f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"}
    ).json()
    resp = client.post(
        f"/sos/{sos['id']}/cancel", headers={"Authorization": f"Bearer {setup['c_token']}"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_non_activator_cannot_cancel(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    sos = client.post(
        f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"}
    ).json()
    resp = client.post(
        f"/sos/{sos['id']}/cancel", headers={"Authorization": f"Bearer {setup['w_token']}"}
    )
    assert resp.status_code == 403


def test_resolve_already_resolved_fails(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    sos = client.post(
        f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"}
    ).json()
    client.post(f"/sos/{sos['id']}/resolve", headers={"Authorization": f"Bearer {setup['c_token']}"})
    resp = client.post(
        f"/sos/{sos['id']}/resolve", headers={"Authorization": f"Bearer {setup['c_token']}"}
    )
    assert resp.status_code == 409


def test_get_sos_none(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    resp = client.get(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "none"


def test_get_sos_active(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    client.post(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"})
    resp = client.get(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"})
    assert resp.json()["status"] == "ACTIVE"


# -- polling endpoints include sos_alert ---------------------------------------

def test_sos_in_customer_requests_polling(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    client.post(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"})
    items = client.get(
        "/service-requests/me", headers={"Authorization": f"Bearer {setup['c_token']}"}
    ).json()
    matching = [i for i in items if i.get("job_id") == job_id]
    assert matching, "Job not found in customer requests"
    assert matching[0]["sos_alert"] is not None
    assert matching[0]["sos_alert"]["status"] == "ACTIVE"


def test_sos_in_worker_requests_polling(setup):
    job_id = create_active_job(setup["c_token"], setup["w_token"], setup["customer_id"])
    client.post(f"/jobs/{job_id}/sos", headers={"Authorization": f"Bearer {setup['c_token']}"})
    items = client.get(
        "/workers/me/requests", headers={"Authorization": f"Bearer {setup['w_token']}"}
    ).json()
    matching = [i for i in items if i.get("job_id") == job_id]
    assert matching, f"Job {job_id} not found in worker requests; got job_ids={[i.get('job_id') for i in items]}"
    assert matching[0]["sos_alert"] is not None
    assert matching[0]["sos_alert"]["status"] == "ACTIVE"
