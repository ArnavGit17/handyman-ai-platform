from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_emergency_plumbing_matches_verified_worker():
    response = client.post('/service-request', json={'service_type':'Plumbing','description':'Bathroom pipe is leaking','area':'Area A','latitude':12.9716,'longitude':77.5946,'urgency':'emergency'})
    assert response.status_code == 200
    body = response.json()
    assert body['best_match']['name'] == 'Rajesh Kumar'
    assert body['best_match']['components']['skill_match'] == 100
    assert body['best_match']['reasons']

def test_forecast_exists():
    response = client.get('/demand/forecast')
    assert response.status_code == 200
    assert len(response.json()) > 0
