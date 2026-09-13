from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Customer, Job, Payment, ServiceRequest, User, Worker
from app.seed import seed_database
from app.services.matching import worker_eligible

client = TestClient(app)


def cleanup_user(email: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return
        customer = db.query(Customer).filter(Customer.user_id == user.id).first()
        if customer:
            job_ids = [job.id for job in db.query(Job).filter(Job.customer_id == customer.id).all()]
            if job_ids:
                db.query(Payment).filter(Payment.job_id.in_(job_ids)).delete(synchronize_session=False)
            db.query(Job).filter(Job.customer_id == customer.id).delete(synchronize_session=False)
            db.query(ServiceRequest).filter(ServiceRequest.customer_id == customer.id).delete()
            db.delete(customer)
        worker = db.query(Worker).filter(Worker.user_id == user.id).first()
        if worker:
            job_ids = [job.id for job in db.query(Job).filter(Job.worker_id == worker.id).all()]
            if job_ids:
                db.query(Payment).filter(Payment.job_id.in_(job_ids)).delete(synchronize_session=False)
            db.query(Job).filter(Job.worker_id == worker.id).delete()
            db.delete(worker)
        db.delete(user)
        db.commit()
    finally:
        db.close()


def create_customer_auth(name: str):
    email = f"{name.lower().replace(' ', '.')}.{uuid4().hex[:8]}@example.com"
    response = client.post('/auth/register', json={
        'name': name,
        'email': email,
        'phone': '9876540000',
        'password': 'secret123',
        'role': 'customer',
    })
    assert response.status_code == 200, response.text
    token = client.post('/auth/login', json={'email': email, 'password': 'secret123'}).json()['access_token']
    return email, {'Authorization': f'Bearer {token}'}


def test_customer_registration_and_login():
    email = f'customer.{uuid4().hex[:8]}@example.com'
    response = client.post('/auth/register', json={
        'name': 'Aisha Khan',
        'email': email,
        'phone': '9876540101',
        'password': 'secret123',
        'role': 'customer',
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['user']['email'] == email
    assert body['user']['role'] == 'customer'
    token = client.post('/auth/login', json={'email': email, 'password': 'secret123'})
    assert token.status_code == 200, token.text
    token_body = token.json()
    assert 'access_token' in token_body

    me = client.get('/auth/me', headers={'Authorization': f"Bearer {token_body['access_token']}"})
    assert me.status_code == 200
    assert me.json()['email'] == email
    cleanup_user(email)


def test_worker_registration_creates_real_profile_for_matching():
    email = f'worker.{uuid4().hex[:8]}@example.com'
    response = client.post('/auth/register', json={
        'name': 'Arnav Singh',
        'email': email,
        'phone': '9876540111',
        'password': 'secret123',
        'role': 'worker',
        'skills': 'Plumbing',
        'experience': 6,
        'service_areas': ['Area A'],
        'location': {'latitude': 12.9716, 'longitude': 77.5946},
        'availability': True,
        'rate': 680,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['user']['role'] == 'worker'

    login = client.post('/auth/login', json={'email': email, 'password': 'secret123'})
    assert login.status_code == 200, login.text
    auth = {'Authorization': f"Bearer {login.json()['access_token']}"}

    me = client.get('/workers/me', headers=auth)
    assert me.status_code == 200, me.text
    assert me.json()['name'] == 'Arnav Singh'
    assert me.json()['skills'] == 'Plumbing'

    match = client.post('/service-request', json={'description': 'My bathroom pipe is leaking urgently.', 'area': 'Area A'})
    assert match.status_code == 200, match.text
    names = {item['name'] for item in match.json()['ranked_candidates']}
    assert 'Arnav Singh' in names
    cleanup_user(email)


def test_registered_worker_profile_returns_real_skill_and_certifications():
    email = f'worker.profile.{uuid4().hex[:8]}@example.com'
    response = client.post('/auth/register', json={
        'name': 'Test Electrician',
        'email': email,
        'phone': '9876540222',
        'password': 'secret123',
        'role': 'worker',
        'skills': 'Electrical',
        'certifications': 'Electrical Safety',
        'experience': 3,
        'service_areas': ['Area B'],
        'area': 'Area B',
        'location': {'latitude': 12.9816, 'longitude': 77.5966},
        'availability': True,
        'rate': 850,
    })
    assert response.status_code == 200, response.text

    login = client.post('/auth/login', json={'email': email, 'password': 'secret123'})
    assert login.status_code == 200, login.text
    auth = {'Authorization': f"Bearer {login.json()['access_token']}"}

    me = client.get('/workers/me', headers=auth)
    assert me.status_code == 200, me.text
    body = me.json()
    assert body['name'] == 'Test Electrician'
    assert body['skills'] == 'Electrical'
    assert body['certifications'] == 'Electrical Safety'
    assert body['experience_years'] == 3
    assert body['area'] == 'Area B'

    cleanup_user(email)


def test_fresh_registered_electrician_reaches_matching_and_job_lifecycle():
    customer_email, customer_auth = create_customer_auth('Fresh Match Customer')
    worker_email = f'test.electrician.{uuid4().hex[:8]}@example.com'
    try:
        registered = client.post('/auth/register', json={
            'name': 'Test Electrician',
            'email': worker_email,
            'phone': '9876540333',
            'password': 'secret123',
            'role': 'worker',
            'skill': 'Electrician',
            'certifications': 'Relevant electrical certificate',
            'experience': 2,
            'service_areas': ['Area C'],
            'area': 'Area C',
            'location': {'latitude': 13.2, 'longitude': 77.8},
            'availability': True,
            'rate': 850,
        })
        assert registered.status_code == 200, registered.text

        worker_token = client.post('/auth/login', json={'email': worker_email, 'password': 'secret123'}).json()['access_token']
        worker_auth = {'Authorization': f'Bearer {worker_token}'}
        auth_me = client.get('/auth/me', headers=worker_auth)
        assert auth_me.status_code == 200
        assert auth_me.json()['name'] == 'Test Electrician'

        worker_profile = client.get('/workers/me', headers=worker_auth)
        assert worker_profile.status_code == 200, worker_profile.text
        profile = worker_profile.json()
        assert profile['name'] == 'Test Electrician'
        assert profile['skills'] == 'Electrician'
        assert profile['area'] == 'Area C'
        assert profile['certifications'] == 'Relevant electrical certificate'
        assert profile['availability_status'] == 'Available'
        worker_id = profile['id']

        db = SessionLocal()
        try:
            saved_worker = db.get(Worker, worker_id)
            assert saved_worker is not None
            assert saved_worker.is_demo is False
            saved_worker.rating = 5.0
            saved_worker.recent_jobs = 0
            db.commit()
        finally:
            db.close()

        request = client.post('/service-request', headers=customer_auth, json={
            'description': 'My ceiling fan is not working and I need an electrician.',
            'area': 'Area C',
            'latitude': 13.2,
            'longitude': 77.8,
        })
        assert request.status_code == 200, request.text
        body = request.json()
        request_id = body['request_id']
        assert body['request']['service_type'] == 'Electrical'
        assert body['best_match']['worker_id'] == worker_id
        assert worker_id in {candidate['worker_id'] for candidate in body['ranked_candidates']}
        ranked = next(candidate for candidate in body['ranked_candidates'] if candidate['worker_id'] == worker_id)
        assert ranked['score'] > 0
        rematch = client.post('/match-worker', json={'request_id': request_id})
        assert rematch.status_code == 200, rematch.text
        assert rematch.json()['best_match']['worker_id'] == worker_id

        db = SessionLocal()
        try:
            saved_request = db.get(ServiceRequest, request_id)
            saved_worker = db.get(Worker, worker_id)
            eligible, reason = worker_eligible(saved_request, saved_worker)
            assert eligible, reason
        finally:
            db.close()

        assigned = client.post(f'/accept-job/{request_id}?selected_worker_id={worker_id}', headers=customer_auth)
        assert assigned.status_code == 200, assigned.text
        job_payload = assigned.json()
        assert job_payload['worker_id'] == worker_id
        assert job_payload['worker_name'] == 'Test Electrician'
        job_id = job_payload['job_id']

        db = SessionLocal()
        try:
            saved_job = db.get(Job, job_id)
            assert saved_job is not None
            assert saved_job.worker_id == worker_id
            assert saved_job.request_id == request_id
        finally:
            db.close()

        inbox = client.get('/workers/me/requests', headers=worker_auth)
        assert inbox.status_code == 200
        assert any(item['job_id'] == job_id for item in inbox.json())

        accepted = client.post(f'/jobs/{job_id}/accept', headers=worker_auth)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()['status'] == 'accepted'

        started = client.post(f'/jobs/{job_id}/start', headers=worker_auth)
        assert started.status_code == 200, started.text
        assert started.json()['status'] == 'in_progress'

        completed = client.post(f'/jobs/{job_id}/complete', headers=worker_auth)
        assert completed.status_code == 200, completed.text
        assert completed.json()['status'] == 'completed'

        customer_view = client.get('/service-requests/me', headers=customer_auth)
        assert customer_view.status_code == 200
        completed_request = next(item for item in customer_view.json() if item['id'] == request_id)
        assert completed_request['status'] == 'completed'
        assert completed_request['assigned_worker_id'] == worker_id
        assert completed_request['assigned_worker'] == 'Test Electrician'
        assert completed_request['job_status'] == 'completed'
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)


def test_registered_real_worker_skill_aliases_match_only_their_services():
    customer_email, customer_auth = create_customer_auth('Skill Matrix Customer')
    specs = [
        ('Matrix Electrician', 'Electrician', 'Need someone to install a ceiling fan in Area C', 'Electrical'),
        ('Matrix Plumber', 'Plumber', 'My sink pipe is leaking in Area C', 'Plumbing'),
        ('Matrix Carpenter', 'Carpenter', 'Repair my wooden cupboard door in Area C', 'Carpentry'),
        ('Matrix Cleaner', 'Cleaner', 'Please clean my house in Area C', 'Cleaning'),
        ('Matrix Appliance Tech', 'Appliance Technician', 'My washing machine appliance needs repair in Area C', 'Appliance Repair'),
    ]
    worker_emails = []
    worker_ids = {}
    try:
        for name, skill, _, _ in specs:
            email = f'{name.lower().replace(" ", ".")}.{uuid4().hex[:8]}@example.com'
            worker_emails.append(email)
            registered = client.post('/auth/register', json={
                'name': name,
                'email': email,
                'phone': '9876540444',
                'password': 'secret123',
                'role': 'worker',
                'skills': skill,
                'certifications': f'{skill} certificate',
                'experience': 4,
                'service_areas': ['Area C'],
                'area': 'Area C',
                'location': {'latitude': 12.9716, 'longitude': 77.5946},
                'availability_status': 'Available',
                'rate': 800,
            })
            assert registered.status_code == 200, registered.text
            token = client.post('/auth/login', json={'email': email, 'password': 'secret123'}).json()['access_token']
            profile = client.get('/workers/me', headers={'Authorization': f'Bearer {token}'}).json()
            worker_ids[name] = profile['id']

        for name, _, description, expected_service in specs:
            response = client.post('/service-request', headers=customer_auth, json={
                'description': description,
                'area': 'Area C',
                'latitude': 12.9716,
                'longitude': 77.5946,
            })
            assert response.status_code == 200, response.text
            body = response.json()
            assert body['request']['service_type'] == expected_service
            candidate_ids = {candidate['worker_id'] for candidate in body['ranked_candidates']}
            assert worker_ids[name] in candidate_ids
            for other_name in worker_ids:
                if other_name != name:
                    assert worker_ids[other_name] not in candidate_ids
    finally:
        cleanup_user(customer_email)
        for email in worker_emails:
            cleanup_user(email)


def test_emergency_plumbing_matches_verified_worker():
    response = client.post('/service-request', json={'service_type':'Plumbing','description':'Bathroom pipe is leaking','area':'Area A','latitude':12.9716,'longitude':77.5946,'urgency':'emergency'})
    assert response.status_code == 200
    body = response.json()
    assert body['best_match']['name'] in {candidate['name'] for candidate in body['ranked_candidates']}
    assert body['best_match']['components']['skill_match'] == 100
    assert body['best_match']['reasons']
    assert body['eligible_count'] >= 5
    assert len(body['ranked_candidates']) == body['eligible_count']

def test_database_has_exactly_50_workers_and_service_mix():
    workers = client.get('/workers').json()
    assert len(workers) == 50
    counts = {service: sum(service.lower() in worker['skills'].lower() for worker in workers) for service in ['Plumbing', 'Electrical', 'Carpentry', 'Cleaning', 'Painting', 'Appliance Repair']}
    assert counts['Plumbing'] >= 5
    assert all(count >= 7 for count in counts.values())

def test_unavailable_showcase_worker_is_replaced():
    db = SessionLocal()
    rajesh = db.query(Worker).filter(Worker.name == 'Rajesh Kumar').first()
    original = rajesh.availability
    rajesh.availability = False
    db.commit()
    try:
        response = client.post('/service-request', json={'service_type':'Plumbing','description':'Bathroom pipe is leaking','area':'Area A','latitude':12.9716,'longitude':77.5946,'urgency':'emergency'})
        assert response.json()['best_match']['name'] != 'Rajesh Kumar'
    finally:
        rajesh.availability = original
        db.commit()
        db.close()

def test_different_services_change_winner():
    payload = {'description':'Need a qualified professional','area':'Area A','latitude':12.9716,'longitude':77.5946,'urgency':'normal'}
    electrical = client.post('/service-request', json={**payload, 'service_type':'Electrical'}).json()['best_match']['name']
    carpentry = client.post('/service-request', json={**payload, 'service_type':'Carpentry'}).json()['best_match']['name']
    assert electrical != carpentry

def test_workload_can_change_ranking():
    db = SessionLocal()
    rajesh = db.query(Worker).filter(Worker.name == 'Rajesh Kumar').first()
    original = rajesh.current_workload
    original_recent_jobs = rajesh.recent_jobs
    rajesh.current_workload = 100
    rajesh.recent_jobs = 100
    db.commit()
    try:
        response = client.post('/service-request', json={'service_type':'Plumbing','description':'Bathroom pipe is leaking','area':'Area A','latitude':12.9716,'longitude':77.5946,'urgency':'emergency'})
        assert response.json()['best_match']['name'] != 'Rajesh Kumar'
    finally:
        rajesh.current_workload = original
        rajesh.recent_jobs = original_recent_jobs
        db.commit()
        db.close()

def test_location_changes_ranking_and_unqualified_worker_is_excluded():
    payload = {'service_type':'Plumbing','description':'Need a qualified professional','area':'Area A','urgency':'normal'}
    db = SessionLocal()
    candidate = db.query(Worker).filter(Worker.skills.ilike('%Plumbing%')).first()
    original_skills = candidate.skills
    candidate.skills = 'Electrical'
    db.commit()
    first = client.post('/service-request', json={**payload, 'latitude':12.94, 'longitude':77.56}).json()
    second = client.post('/service-request', json={**payload, 'latitude':13.00, 'longitude':77.63}).json()
    try:
        assert first['best_match']['name'] != second['best_match']['name']
        assert candidate.name not in {item['name'] for item in second['ranked_candidates']}
    finally:
        candidate.skills = original_skills
        db.commit()
        db.close()

def test_job_lifecycle_and_dashboard_contract():
    customer_email, customer_auth = create_customer_auth('Lifecycle Customer')
    response = client.post('/service-request', headers=customer_auth, json={'service_type':'Electrical','description':'Ceiling fan is not working','area':'Area B','latitude':12.9716,'longitude':77.5946})
    request_id = response.json()['request_id']
    job = client.post(f'/accept-job/{request_id}', headers=customer_auth)
    assert job.status_code == 200
    job_id = job.json()['job_id']
    assert client.post(f'/start-job/{job_id}').json()['status'] == 'in_progress'
    assert client.post(f'/complete-job/{job_id}').json()['status'] == 'completed'
    dashboard = client.get('/cooperative/dashboard').json()
    assert dashboard['workforce']['total'] == 50
    assert len(dashboard['area_coverage']) == 5
    cleanup_user(customer_email)

def test_natural_language_understanding_routes_each_service():
    examples = [
        ('My bathroom pipe is leaking urgently', 'Plumbing'),
        ('Need someone to install a ceiling fan', 'Electrical'),
        ('Repair my wooden cupboard door', 'Carpentry'),
        ('Please clean my house today', 'Cleaning'),
        ('My washing machine is not working', 'Appliance Repair'),
    ]
    winners = []
    for description, service in examples:
        response = client.post('/service-request', json={'description': description, 'area': 'Area A'})
        assert response.status_code == 200
        body = response.json()
        assert body['request']['service_type'] == service
        assert body['best_match']['name'] in {candidate['name'] for candidate in body['ranked_candidates']}
        winners.append(body['best_match']['name'])
    assert len(set(winners)) > 1

def test_selected_worker_and_exact_request_reach_job():
    customer_email, customer_auth = create_customer_auth('Selection Customer')
    response = client.post('/service-request', headers=customer_auth, json={'description':'Need someone to install a ceiling fan','area':'Area B'})
    body = response.json()
    selected_id = body['best_match']['worker_id']
    job = client.post(f"/accept-job/{body['request_id']}?selected_worker_id={selected_id}", headers=customer_auth)
    result = job.json()
    assert result['worker_id'] == selected_id
    assert result['worker_name'] == body['best_match']['name']
    assert result['description'] == 'Need someone to install a ceiling fan'
    assert result['service_type'] == 'Electrical'
    assert result['area'] == 'Area B'
    cleanup_user(customer_email)


def test_customer_can_select_another_qualified_worker():
    customer_email, customer_auth = create_customer_auth('Alternative Customer')
    worker_email = f"alternative.worker.{uuid4().hex[:8]}@example.com"
    try:
        registered = client.post('/auth/register', json={
            'name': 'Qualified Alternative',
            'email': worker_email,
            'phone': '9876540123',
            'password': 'secret123',
            'role': 'worker',
            'skills': 'Electrical',
            'experience': 6,
            'service_areas': ['Area B'],
            'area': 'Area B',
            'location': {'latitude': 12.9816, 'longitude': 77.5966},
            'availability_status': 'Available',
            'rate': 900,
        })
        assert registered.status_code == 200, registered.text
        worker_token = client.post('/auth/login', json={'email': worker_email, 'password': 'secret123'}).json()['access_token']
        worker_id = client.get('/workers/me', headers={'Authorization': f'Bearer {worker_token}'}).json()['id']
        response = client.post('/service-request', headers=customer_auth, json={'description':'Need someone to install a ceiling fan','area':'Area B'})
        body = response.json()
        db = SessionLocal()
        try:
            assert db.query(Job).filter(Job.request_id == body['request_id']).count() == 0
        finally:
            db.close()
        assert worker_id in {candidate['worker_id'] for candidate in body['ranked_candidates']}
        job = client.post(f"/accept-job/{body['request_id']}?selected_worker_id={worker_id}", headers=customer_auth)
        assert job.status_code == 200, job.text
        result = job.json()
        assert result['worker_id'] == worker_id
        assert result['worker_name'] == 'Qualified Alternative'
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)

def test_customer_request_ownership_and_worker_inbox():
    customer_email = f'customer.owner.{uuid4().hex[:8]}@example.com'
    customer = client.post('/auth/register', json={
        'name': 'Naina Shah',
        'email': customer_email,
        'phone': '9876540999',
        'password': 'secret123',
        'role': 'customer',
    }).json()['user']
    cust_token = client.post('/auth/login', json={'email': customer_email, 'password': 'secret123'}).json()['access_token']

    worker_email = f'worker.owner.{uuid4().hex[:8]}@example.com'
    worker = client.post('/auth/register', json={
        'name': 'Ishaan Verma',
        'email': worker_email,
        'phone': '9876540888',
        'password': 'secret123',
        'role': 'worker',
        'skills': 'Plumbing',
        'experience': 5,
        'service_areas': ['Area A'],
        'location': {'latitude': 12.9716, 'longitude': 77.5946},
        'availability': True,
        'rate': 700,
    }).json()['user']
    worker_token = client.post('/auth/login', json={'email': worker_email, 'password': 'secret123'}).json()['access_token']

    create = client.post('/service-request', headers={'Authorization': f'Bearer {cust_token}'}, json={'description': 'My bathroom pipe is leaking urgently.', 'area': 'Area A'})
    assert create.status_code == 200, create.text
    request_id = create.json()['request_id']

    my_requests = client.get('/service-requests/me', headers={'Authorization': f'Bearer {cust_token}'})
    assert my_requests.status_code == 200
    assert any(item['id'] == request_id for item in my_requests.json())

    my_request = client.get(f'/service-request/{request_id}', headers={'Authorization': f'Bearer {cust_token}'})
    assert my_request.status_code == 200
    assert my_request.json()['description'] == 'My bathroom pipe is leaking urgently.'

    worker_requests = client.get('/workers/me/requests', headers={'Authorization': f'Bearer {worker_token}'})
    assert worker_requests.status_code == 200
    assert isinstance(worker_requests.json(), list)

    unauthorized = client.get(f'/service-request/{request_id}', headers={'Authorization': f"Bearer {worker_token}"})
    assert unauthorized.status_code == 403, unauthorized.text

    cleanup_user(customer_email)
    cleanup_user(worker_email)


def test_worker_accept_reject_and_complete_lifecycle():
    customer_email = f'customer.lifecycle.{uuid4().hex[:8]}@example.com'
    customer_token = client.post('/auth/login', json={'email': customer_email, 'password': 'secret123'}).json()['access_token'] if False else None
    customer_response = client.post('/auth/register', json={
        'name': 'Pooja Menon',
        'email': customer_email,
        'phone': '9876540777',
        'password': 'secret123',
        'role': 'customer',
    })
    customer_token = client.post('/auth/login', json={'email': customer_email, 'password': 'secret123'}).json()['access_token']

    worker_email = f'worker.lifecycle.{uuid4().hex[:8]}@example.com'
    worker_response = client.post('/auth/register', json={
        'name': 'Kabir Shah',
        'email': worker_email,
        'phone': '9876540666',
        'password': 'secret123',
        'role': 'worker',
        'skills': 'Plumbing',
        'experience': 12,
        'service_areas': ['Area A'],
        'location': {'latitude': 12.9716, 'longitude': 77.5946},
        'availability': True,
        'rate': 720,
    })
    worker_token = client.post('/auth/login', json={'email': worker_email, 'password': 'secret123'}).json()['access_token']

    request_resp = client.post('/service-request', headers={'Authorization': f'Bearer {customer_token}'}, json={'description': 'My bathroom sink is leaking urgently.', 'area': 'Area A'})
    assert request_resp.status_code == 200, request_resp.text
    request_id = request_resp.json()['request_id']
    ranked_ids = {candidate['worker_id'] for candidate in request_resp.json()['ranked_candidates']}
    worker_profile = client.get('/workers/me', headers={'Authorization': f'Bearer {worker_token}'})
    assert worker_profile.status_code == 200, worker_profile.text
    worker_id = worker_profile.json()['id']
    assert worker_id in ranked_ids, f'Worker {worker_id} must be a ranked candidate for this request'
    assign = client.post(f'/accept-job/{request_id}?selected_worker_id={worker_id}', headers={'Authorization': f'Bearer {customer_token}'})
    assert assign.status_code == 200, assign.text
    job_id = assign.json()['job_id']
    duplicate_assign = client.post(f'/accept-job/{request_id}?selected_worker_id={worker_id}', headers={'Authorization': f'Bearer {customer_token}'})
    assert duplicate_assign.status_code == 200
    assert duplicate_assign.json()['job_id'] == job_id
    db = SessionLocal()
    try:
        assert db.query(Job).filter(Job.request_id == request_id).count() == 1
    finally:
        db.close()

    customer_identity = client.get('/auth/me', headers={'Authorization': f'Bearer {customer_token}'})
    assert customer_identity.status_code == 200
    assert customer_identity.json()['role'] == 'customer'
    customer_request = client.get('/service-requests/me', headers={'Authorization': f'Bearer {customer_token}'})
    assigned_request = next(item for item in customer_request.json() if item['id'] == request_id)
    assert assigned_request['status'] == 'assigned'
    assert assigned_request['assigned_worker_id'] == worker_id
    customer_accept = client.post(f'/jobs/{job_id}/accept', headers={'Authorization': f'Bearer {customer_token}'})
    assert customer_accept.status_code == 403

    worker_inbox = client.get('/workers/me/requests', headers={'Authorization': f'Bearer {worker_token}'})
    assert worker_inbox.status_code == 200
    assert any(item['job_id'] == job_id for item in worker_inbox.json())

    reject = client.post(f'/jobs/{job_id}/reject', headers={'Authorization': f'Bearer {worker_token}'})
    assert reject.status_code == 200, reject.text

    accept = client.post(f'/jobs/{job_id}/accept', headers={'Authorization': f'Bearer {worker_token}'})
    assert accept.status_code == 200, accept.text
    assert accept.json()['status'] == 'accepted'

    start = client.post(f'/jobs/{job_id}/start', headers={'Authorization': f'Bearer {worker_token}'})
    assert start.status_code == 200, start.text
    assert start.json()['status'] == 'in_progress'

    complete = client.post(f'/jobs/{job_id}/complete', headers={'Authorization': f'Bearer {worker_token}'})
    assert complete.status_code == 200, complete.text
    assert complete.json()['status'] == 'completed'

    cleanup_user(customer_email)
    cleanup_user(worker_email)


def test_customer_request_persists_and_status_moves_through_lifecycle():
    customer_email = f'customer.lifecycle.real.{uuid4().hex[:8]}@example.com'
    customer = client.post('/auth/register', json={
        'name': 'Real Customer',
        'email': customer_email,
        'phone': '9876540118',
        'password': 'secret123',
        'role': 'customer',
    })
    customer_token = client.post('/auth/login', json={'email': customer_email, 'password': 'secret123'}).json()['access_token']

    worker_email = f'worker.lifecycle.real.{uuid4().hex[:8]}@example.com'
    worker = client.post('/auth/register', json={
        'name': 'Real Electrician',
        'email': worker_email,
        'phone': '9876540119',
        'password': 'secret123',
        'role': 'worker',
        'skills': 'Electrical',
        'experience': 4,
        'service_areas': ['Area B'],
        'area': 'Area B',
        'location': {'latitude': 12.9816, 'longitude': 77.5966},
        'availability': True,
        'rate': 850,
    })
    worker_token = client.post('/auth/login', json={'email': worker_email, 'password': 'secret123'}).json()['access_token']

    create = client.post('/service-request', headers={'Authorization': f'Bearer {customer_token}'}, json={'description': 'Need someone to install a ceiling fan in Area B', 'area': 'Area B'})
    assert create.status_code == 200, create.text
    request_id = create.json()['request_id']
    assert create.json()['request']['service_type'] == 'Electrical'

    saved = client.get('/service-requests/me', headers={'Authorization': f'Bearer {customer_token}'})
    assert saved.status_code == 200
    assert any(item['id'] == request_id for item in saved.json())
    assert any(item['id'] == request_id and item['status'] == 'matched' for item in saved.json())
    current = client.get('/service-requests/me?current_only=true', headers={'Authorization': f'Bearer {customer_token}'})
    assert current.status_code == 200
    assert len(current.json()) == 1
    assert current.json()[0]['id'] == request_id

    worker_profile = client.get('/workers/me', headers={'Authorization': f'Bearer {worker_token}'}).json()
    selected_worker_id = worker_profile['id']
    assert selected_worker_id in {candidate['worker_id'] for candidate in create.json()['ranked_candidates']}
    assign = client.post(f'/accept-job/{request_id}?selected_worker_id={selected_worker_id}', headers={'Authorization': f'Bearer {customer_token}'})
    assert assign.status_code == 200, assign.text
    job_id = assign.json()['job_id']

    worker_inbox = client.get('/workers/me/requests', headers={'Authorization': f'Bearer {worker_token}'})
    assert worker_inbox.status_code == 200
    assert any(item['job_id'] == job_id for item in worker_inbox.json())

    worker_accept = client.post(f'/jobs/{job_id}/accept', headers={'Authorization': f'Bearer {worker_token}'})
    assert worker_accept.status_code == 200, worker_accept.text
    assert worker_accept.json()['status'] == 'accepted'

    worker_start = client.post(f'/jobs/{job_id}/start', headers={'Authorization': f'Bearer {worker_token}'})
    assert worker_start.status_code == 200, worker_start.text
    assert worker_start.json()['status'] == 'in_progress'

    worker_complete = client.post(f'/jobs/{job_id}/complete', headers={'Authorization': f'Bearer {worker_token}'})
    assert worker_complete.status_code == 200, worker_complete.text
    assert worker_complete.json()['status'] == 'completed'

    customer_view = client.get('/service-requests/me', headers={'Authorization': f'Bearer {customer_token}'})
    assert customer_view.status_code == 200
    completed_request = next(item for item in customer_view.json() if item['id'] == request_id)
    assert completed_request['status'] == 'completed'
    assert completed_request['assigned_worker_id'] == selected_worker_id
    assert completed_request['assigned_worker'] == worker_profile['name']
    assert completed_request['job_status'] == 'completed'
    for _ in range(3):
        refreshed = client.get('/service-requests/me?current_only=true', headers={'Authorization': f'Bearer {customer_token}'})
        assert refreshed.status_code == 200
        current_request = refreshed.json()[0]
        assert current_request['id'] == request_id
        assert current_request['assigned_worker_id'] == selected_worker_id
        assert current_request['assigned_worker'] == worker_profile['name']
        assert current_request['job_status'] == 'completed'

    cleanup_user(customer_email)
    cleanup_user(worker_email)


def test_unrelated_worker_cannot_see_or_accept_other_workers_request():
    customer_email = f'customer.private.{uuid4().hex[:8]}@example.com'
    customer_token = client.post('/auth/login', json={'email': customer_email, 'password': 'secret123'}).json()['access_token'] if False else None
    client.post('/auth/register', json={
        'name': 'Private Customer',
        'email': customer_email,
        'phone': '9876540151',
        'password': 'secret123',
        'role': 'customer',
    })
    customer_token = client.post('/auth/login', json={'email': customer_email, 'password': 'secret123'}).json()['access_token']

    worker1_email = f'worker.private1.{uuid4().hex[:8]}@example.com'
    worker1_token = client.post('/auth/login', json={'email': worker1_email, 'password': 'secret123'}).json()['access_token'] if False else None
    client.post('/auth/register', json={
        'name': 'Worker One',
        'email': worker1_email,
        'phone': '9876540152',
        'password': 'secret123',
        'role': 'worker',
        'skills': 'Electrical',
        'experience': 4,
        'service_areas': ['Area B'],
        'area': 'Area B',
        'location': {'latitude': 12.9816, 'longitude': 77.5966},
        'availability': True,
        'rate': 850,
    })
    worker1_token = client.post('/auth/login', json={'email': worker1_email, 'password': 'secret123'}).json()['access_token']

    worker2_email = f'worker.private2.{uuid4().hex[:8]}@example.com'
    worker2_token = client.post('/auth/login', json={'email': worker2_email, 'password': 'secret123'}).json()['access_token'] if False else None
    client.post('/auth/register', json={
        'name': 'Worker Two',
        'email': worker2_email,
        'phone': '9876540153',
        'password': 'secret123',
        'role': 'worker',
        'skills': 'Electrical',
        'experience': 5,
        'service_areas': ['Area B'],
        'area': 'Area B',
        'location': {'latitude': 12.9826, 'longitude': 77.5976},
        'availability': True,
        'rate': 900,
    })
    worker2_token = client.post('/auth/login', json={'email': worker2_email, 'password': 'secret123'}).json()['access_token']

    request = client.post('/service-request', headers={'Authorization': f'Bearer {customer_token}'}, json={'description': 'Need someone to install a ceiling fan in Area B', 'area': 'Area B'})
    request_id = request.json()['request_id']
    worker1_profile = client.get('/workers/me', headers={'Authorization': f'Bearer {worker1_token}'}).json()
    selected_worker_id = worker1_profile['id']
    assign = client.post(f'/accept-job/{request_id}?selected_worker_id={selected_worker_id}', headers={'Authorization': f'Bearer {customer_token}'})
    job_id = assign.json()['job_id']

    worker1_inbox = client.get('/workers/me/requests', headers={'Authorization': f'Bearer {worker1_token}'})
    worker2_inbox = client.get('/workers/me/requests', headers={'Authorization': f'Bearer {worker2_token}'})
    assert any(item['job_id'] == job_id for item in worker1_inbox.json())
    assert all(item['job_id'] != job_id for item in worker2_inbox.json())

    deny = client.post(f'/jobs/{job_id}/accept', headers={'Authorization': f'Bearer {worker2_token}'})
    assert deny.status_code == 403, deny.text

    cleanup_user(customer_email)
    cleanup_user(worker1_email)
    cleanup_user(worker2_email)


def test_seed_database_is_idempotent_for_requests_and_jobs():
    db = SessionLocal()
    try:
        before_requests = db.query(ServiceRequest).count()
        before_jobs = db.query(Job).count()
        seed_database(db)
        seed_database(db)
        assert db.query(ServiceRequest).count() == before_requests
        assert db.query(Job).count() == before_jobs
    finally:
        db.close()


def test_worker_availability_persists_and_controls_matching():
    worker_email = f'worker.availability.{uuid4().hex[:8]}@example.com'
    customer_email = f'customer.availability.{uuid4().hex[:8]}@example.com'
    try:
        registered = client.post('/auth/register', json={
            'name': 'Availability Electrician',
            'email': worker_email,
            'phone': '9876540171',
            'password': 'secret123',
            'role': 'worker',
            'skills': 'Electrician',
            'experience': 5,
            'service_areas': ['Area B'],
            'area': 'Area B',
            'location': {'latitude': 12.9816, 'longitude': 77.5966},
            'availability': True,
            'availability_status': 'Available',
            'rate': 900,
        })
        assert registered.status_code == 200, registered.text
        worker_token = client.post('/auth/login', json={'email': worker_email, 'password': 'secret123'}).json()['access_token']
        worker_auth = {'Authorization': f'Bearer {worker_token}'}

        initial = client.get('/workers/me', headers=worker_auth)
        assert initial.status_code == 200
        assert initial.json()['availability_status'] == 'Available'

        customer = client.post('/auth/register', json={
            'name': 'Availability Customer',
            'email': customer_email,
            'phone': '9876540172',
            'password': 'secret123',
            'role': 'customer',
            'area': 'Area B',
            'location': {'latitude': 12.9816, 'longitude': 77.5966},
        })
        assert customer.status_code == 200, customer.text
        customer_token = client.post('/auth/login', json={'email': customer_email, 'password': 'secret123'}).json()['access_token']
        customer_auth = {'Authorization': f'Bearer {customer_token}'}

        unavailable = client.patch('/workers/me/availability', headers=worker_auth, json={'availability_status': 'Unavailable'})
        assert unavailable.status_code == 200, unavailable.text
        assert unavailable.json()['worker_id'] == initial.json()['id']
        assert unavailable.json()['availability_status'] == 'Unavailable'

        persisted = client.get('/workers/me', headers=worker_auth)
        assert persisted.status_code == 200
        assert persisted.json()['availability_status'] == 'Unavailable'

        relogin_token = client.post('/auth/login', json={'email': worker_email, 'password': 'secret123'}).json()['access_token']
        relogged = client.get('/workers/me', headers={'Authorization': f'Bearer {relogin_token}'})
        assert relogged.status_code == 200
        assert relogged.json()['availability_status'] == 'Unavailable'

        request = client.post('/service-request', headers=customer_auth, json={'description': 'Need an electrician urgently to fix the ceiling fan', 'area': 'Area B'})
        assert request.status_code == 200
        assert initial.json()['id'] not in {candidate['worker_id'] for candidate in request.json()['ranked_candidates']}

        available = client.patch('/workers/me/availability', headers=worker_auth, json={'availability_status': 'Available'})
        assert available.status_code == 200, available.text
        assert available.json()['availability_status'] == 'Available'
        assert client.get('/workers/me', headers=worker_auth).json()['availability_status'] == 'Available'

        request_again = client.post('/service-request', headers=customer_auth, json={'description': 'Need an electrician urgently to fix the ceiling fan', 'area': 'Area B'})
        assert request_again.status_code == 200
        assert initial.json()['id'] in {candidate['worker_id'] for candidate in request_again.json()['ranked_candidates']}

        customer_cannot_update = client.patch('/workers/me/availability', headers=customer_auth, json={'availability_status': 'Unavailable'})
        assert customer_cannot_update.status_code == 403
        invalid = client.patch('/workers/me/availability', headers=worker_auth, json={'availability_status': 'Busy'})
        assert invalid.status_code in {400, 422}
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)


def test_forecast_exists():
    response = client.get('/demand/forecast')
    assert response.status_code == 200
    assert len(response.json()) > 0
