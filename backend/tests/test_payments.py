from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Customer, Job, Payment, ServiceRequest, User, Worker

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


def create_worker_auth(name: str, *, rate: float = 850, skills: str = 'Electrical', area: str = 'Area B'):
    email = f"{name.lower().replace(' ', '.')}.{uuid4().hex[:8]}@example.com"
    response = client.post('/auth/register', json={
        'name': name,
        'email': email,
        'phone': '9876540111',
        'password': 'secret123',
        'role': 'worker',
        'skills': skills,
        'experience': 4,
        'service_areas': [area],
        'area': area,
        'location': {'latitude': 12.9816, 'longitude': 77.5966},
        'availability': True,
        'rate': rate,
    })
    assert response.status_code == 200, response.text
    token = client.post('/auth/login', json={'email': email, 'password': 'secret123'}).json()['access_token']
    auth = {'Authorization': f'Bearer {token}'}
    worker_id = client.get('/workers/me', headers=auth).json()['id']
    return email, auth, worker_id


def complete_assigned_job(customer_auth, worker_auth, worker_id, *, description='Need someone to install a ceiling fan', area='Area B'):
    request = client.post('/service-request', headers=customer_auth, json={
        'description': description,
        'area': area,
        'latitude': 12.9816,
        'longitude': 77.5966,
    })
    assert request.status_code == 200, request.text
    request_id = request.json()['request_id']
    assigned = client.post(f'/accept-job/{request_id}?selected_worker_id={worker_id}', headers=customer_auth)
    assert assigned.status_code == 200, assigned.text
    job_id = assigned.json()['job_id']

    assert client.post(f'/jobs/{job_id}/accept', headers=worker_auth).status_code == 200
    assert client.post(f'/jobs/{job_id}/start', headers=worker_auth).status_code == 200
    completed = client.post(f'/jobs/{job_id}/complete', headers=worker_auth)
    assert completed.status_code == 200, completed.text

    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        amount = job.amount
        customer_id = job.customer_id
        worker_id = job.worker_id
    finally:
        db.close()

    return request_id, job_id, amount, customer_id, worker_id


def test_completed_job_creates_payment_with_job_amount():
    customer_email, customer_auth = create_customer_auth('Payment Customer One')
    worker_email, worker_auth, worker_id = create_worker_auth('Payment Electrician')
    try:
        request_id, job_id, amount, customer_id, assigned_worker_id = complete_assigned_job(
            customer_auth, worker_auth, worker_id
        )
        completion = client.post(f'/jobs/{job_id}/complete', headers=worker_auth)
        assert completion.status_code == 409

        db = SessionLocal()
        try:
            payments = db.query(Payment).filter(Payment.job_id == job_id).all()
            assert len(payments) == 1
            payment = payments[0]
            job = db.get(Job, job_id)
            assert payment.amount == job.amount
            assert payment.job_id == job_id
            assert payment.customer_id == customer_id
            assert payment.worker_id == assigned_worker_id
            assert payment.status == 'pending'
            assert payment.qr_payload.startswith('upi://pay?')
            query = parse_qs(urlparse(payment.qr_payload).query)
            assert query['am'][0] == format_amount(job.amount)
            assert query['pa'][0]
            assert payment.currency == 'INR'
        finally:
            db.close()

        payment_get = client.get(f'/jobs/{job_id}/payment', headers=customer_auth)
        assert payment_get.status_code == 200, payment_get.text
        payload = payment_get.json()
        assert payload['payment_id'] == payment.id
        assert payload['amount'] == amount
        assert payload['status'] == 'pending'
        assert payload['qr_payload']
        assert payload['qr_image'] == '' or payload['qr_image'].startswith('data:image/png;base64,')
        assert payload['request_id'] == request_id
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)


def format_amount(amount: float) -> str:
    return f"{float(amount):.2f}".rstrip('0').rstrip('.')


def test_customer_can_retrieve_own_payment_and_other_customer_cannot():
    customer_a_email, customer_a_auth = create_customer_auth('Payment Owner A')
    customer_b_email, customer_b_auth = create_customer_auth('Payment Owner B')
    worker_email, worker_auth, worker_id = create_worker_auth('Payment Worker A')
    try:
        _, job_id, _, _, _ = complete_assigned_job(customer_a_auth, worker_auth, worker_id)

        own = client.get(f'/jobs/{job_id}/payment', headers=customer_a_auth)
        assert own.status_code == 200

        other = client.get(f'/jobs/{job_id}/payment', headers=customer_b_auth)
        assert other.status_code == 403
    finally:
        cleanup_user(customer_a_email)
        cleanup_user(customer_b_email)
        cleanup_user(worker_email)


def test_worker_cannot_confirm_payment():
    customer_email, customer_auth = create_customer_auth('Payment Customer Two')
    worker_email, worker_auth, worker_id = create_worker_auth('Payment Worker Two')
    try:
        _, job_id, _, _, _ = complete_assigned_job(customer_auth, worker_auth, worker_id)
        payment_id = client.get(f'/jobs/{job_id}/payment', headers=customer_auth).json()['payment_id']

        denied = client.post(
            f'/payments/{payment_id}/confirm',
            headers=worker_auth,
            json={'transaction_reference': 'UPI123456'},
        )
        assert denied.status_code == 403
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)


def test_payment_cannot_be_confirmed_before_completion():
    customer_email, customer_auth = create_customer_auth('Payment Customer Three')
    worker_email, worker_auth, worker_id = create_worker_auth('Payment Worker Three')
    try:
        request = client.post('/service-request', headers=customer_auth, json={
            'description': 'Need someone to install a ceiling fan',
            'area': 'Area B',
        })
        request_id = request.json()['request_id']
        assigned = client.post(f'/accept-job/{request_id}?selected_worker_id={worker_id}', headers=customer_auth)
        job_id = assigned.json()['job_id']

        before_complete = client.get(f'/jobs/{job_id}/payment', headers=customer_auth)
        assert before_complete.status_code == 409

        db = SessionLocal()
        try:
            assert db.query(Payment).filter(Payment.job_id == job_id).count() == 0
        finally:
            db.close()
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)


def test_empty_transaction_reference_rejected_and_pending_to_paid_flow():
    customer_email, customer_auth = create_customer_auth('Payment Customer Four')
    worker_email, worker_auth, worker_id = create_worker_auth('Payment Worker Four')
    try:
        _, job_id, amount, _, _ = complete_assigned_job(customer_auth, worker_auth, worker_id)
        payment = client.get(f'/jobs/{job_id}/payment', headers=customer_auth).json()
        payment_id = payment['payment_id']

        empty = client.post(
            f'/payments/{payment_id}/confirm',
            headers=customer_auth,
            json={'transaction_reference': '   '},
        )
        assert empty.status_code == 422

        # Step 1: customer submits UPI reference
        submitted = client.post(
            f'/payments/{payment_id}/confirm',
            headers=customer_auth,
            json={'transaction_reference': 'UPI-DEMO-7788'},
        )
        assert submitted.status_code == 200, submitted.text
        body = submitted.json()
        # UPI now requires worker confirmation
        assert body['status'] == 'awaiting_worker_confirmation'
        assert body['transaction_reference'] == 'UPI-DEMO-7788'
        assert body['amount'] == amount

        # Duplicate submit must be rejected
        duplicate = client.post(
            f'/payments/{payment_id}/confirm',
            headers=customer_auth,
            json={'transaction_reference': 'UPI-DEMO-9999'},
        )
        assert duplicate.status_code == 409

        # Step 2: worker confirms receipt
        confirmed = client.post(f'/payments/{payment_id}/cash-confirm', headers=worker_auth)
        assert confirmed.status_code == 200, confirmed.text
        final = confirmed.json()
        assert final['status'] == 'paid'
        assert final['paid_at']
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)


def test_payment_survives_database_persistence():
    customer_email, customer_auth = create_customer_auth('Payment Customer Five')
    worker_email, worker_auth, worker_id = create_worker_auth('Payment Worker Five')
    try:
        request_id, job_id, amount, _, _ = complete_assigned_job(customer_auth, worker_auth, worker_id)
        payment_id = client.get(f'/jobs/{job_id}/payment', headers=customer_auth).json()['payment_id']
        client.post(
            f'/payments/{payment_id}/confirm',
            headers=customer_auth,
            json={'transaction_reference': 'UPI-PERSIST-001'},
        )
        # Worker confirms receipt to complete the flow
        client.post(f'/payments/{payment_id}/cash-confirm', headers=worker_auth)

        db = SessionLocal()
        try:
            saved = db.get(Payment, payment_id)
            assert saved is not None
            assert saved.status == 'paid'
            assert saved.transaction_reference == 'UPI-PERSIST-001'
            assert saved.amount == amount
        finally:
            db.close()

        history = client.get('/payments/me', headers=customer_auth)
        assert history.status_code == 200
        items = history.json()
        assert any(item['payment_id'] == payment_id and item['status'] == 'paid' for item in items)

        current = client.get('/service-requests/me?current_only=true', headers=customer_auth)
        assert current.status_code == 200
        row = current.json()[0]
        assert row['id'] == request_id
        assert row['payment_status'] == 'paid'
        assert row['payment_transaction_reference'] == 'UPI-PERSIST-001'
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)


def test_multiple_jobs_have_independent_payments():
    customer_email, customer_auth = create_customer_auth('Payment Customer Six')
    worker_one_email, worker_one_auth, worker_one_id = create_worker_auth('Payment Worker Six A', skills='Electrical')
    worker_two_email, worker_two_auth, worker_two_id = create_worker_auth('Payment Worker Six B', skills='Plumbing', rate=720)
    try:
        request_one = client.post('/service-request', headers=customer_auth, json={
            'description': 'Need someone to install a ceiling fan',
            'area': 'Area B',
        })
        request_one_id = request_one.json()['request_id']
        job_one_id = client.post(
            f'/accept-job/{request_one_id}?selected_worker_id={worker_one_id}',
            headers=customer_auth,
        ).json()['job_id']
        for endpoint in ('accept', 'start', 'complete'):
            assert client.post(f'/jobs/{job_one_id}/{endpoint}', headers=worker_one_auth).status_code == 200

        request_two = client.post('/service-request', headers=customer_auth, json={
            'description': 'My bathroom pipe is leaking urgently',
            'area': 'Area B',
        })
        request_two_id = request_two.json()['request_id']
        job_two_id = client.post(
            f'/accept-job/{request_two_id}?selected_worker_id={worker_two_id}',
            headers=customer_auth,
        ).json()['job_id']
        for endpoint in ('accept', 'start', 'complete'):
            assert client.post(f'/jobs/{job_two_id}/{endpoint}', headers=worker_two_auth).status_code == 200

        payment_one = client.get(f'/jobs/{job_one_id}/payment', headers=customer_auth).json()
        payment_two = client.get(f'/jobs/{job_two_id}/payment', headers=customer_auth).json()
        assert payment_one['payment_id'] != payment_two['payment_id']
        assert payment_one['amount'] != payment_two['amount']

        client.post(
            f"/payments/{payment_one['payment_id']}/confirm",
            headers=customer_auth,
            json={'transaction_reference': 'UPI-JOB-ONE'},
        )
        # Worker one confirms receipt
        client.post(f"/payments/{payment_one['payment_id']}/cash-confirm", headers=worker_one_auth)

        refreshed_two = client.get(f'/jobs/{job_two_id}/payment', headers=customer_auth).json()
        assert refreshed_two['status'] == 'pending'
        refreshed_one = client.get(f'/jobs/{job_one_id}/payment', headers=customer_auth).json()
        assert refreshed_one['status'] == 'paid'

        worker_view = client.get('/workers/me/requests', headers=worker_two_auth).json()
        job_two_row = next(item for item in worker_view if item['job_id'] == job_two_id)
        assert job_two_row['payment_status'] == 'pending'
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_one_email)
        cleanup_user(worker_two_email)


def test_customer_stays_on_same_active_request_after_payment_refresh():
    customer_email, customer_auth = create_customer_auth('Payment Customer Seven')
    worker_email, worker_auth, worker_id = create_worker_auth('Payment Worker Seven')
    try:
        request_id, job_id, _, _, _ = complete_assigned_job(customer_auth, worker_auth, worker_id)
        payment_id = client.get(f'/jobs/{job_id}/payment', headers=customer_auth).json()['payment_id']
        client.post(
            f'/payments/{payment_id}/confirm',
            headers=customer_auth,
            json={'transaction_reference': 'UPI-STABLE-REQUEST'},
        )
        # Worker confirms to complete the payment
        client.post(f'/payments/{payment_id}/cash-confirm', headers=worker_auth)

        for _ in range(3):
            refreshed = client.get('/service-requests/me?current_only=true', headers=customer_auth)
            assert refreshed.status_code == 200
            current = refreshed.json()[0]
            assert current['id'] == request_id
            assert current['job_id'] == job_id
            assert current['payment_status'] == 'paid'
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)


def test_cash_payment_flow():
    customer_email, customer_auth = create_customer_auth('Cash Flow Customer')
    worker_email, worker_auth, worker_id = create_worker_auth('Cash Flow Worker')
    try:
        _, job_id, _, _, _ = complete_assigned_job(customer_auth, worker_auth, worker_id)
        payment_id = client.get(f'/jobs/{job_id}/payment', headers=customer_auth).json()['payment_id']

        report_fail = client.post(f'/payments/{payment_id}/cash-report', headers=worker_auth)
        assert report_fail.status_code == 403

        report = client.post(f'/payments/{payment_id}/cash-report', headers=customer_auth)
        assert report.status_code == 200
        assert report.json()['status'] == 'awaiting_cash_confirmation'

        confirm_fail = client.post(f'/payments/{payment_id}/cash-confirm', headers=customer_auth)
        assert confirm_fail.status_code == 403

        confirm = client.post(f'/payments/{payment_id}/cash-confirm', headers=worker_auth)
        assert confirm.status_code == 200
        assert confirm.json()['status'] == 'paid'

        history = client.get('/payments/me', headers=customer_auth).json()
        assert len(history) == 1
        assert history[0]['status'] == 'paid'
        assert history[0]['payment_method'] == 'Cash'
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)


def test_qr_payment_uri_generation():
    customer_email, customer_auth = create_customer_auth('QR Flow Customer')
    worker_email, worker_auth, worker_id = create_worker_auth('QR Flow Worker')
    try:
        _, job_id, amount, _, _ = complete_assigned_job(customer_auth, worker_auth, worker_id)
        payment = client.get(f'/jobs/{job_id}/payment', headers=customer_auth).json()
        assert payment['status'] == 'pending'
        
        # QR payload should be present and valid
        qr_payload = payment['qr_payload']
        assert qr_payload.startswith("upi://pay?")
        
        # Format the amount same as backend (strip .0 if any)
        expected_amount_str = f"{float(amount):.2f}".rstrip("0").rstrip(".")
        assert f"am={expected_amount_str}" in qr_payload
        
        assert "pa=" in qr_payload
        assert "pn=HANDYMAN+Demo" in qr_payload
    finally:
        cleanup_user(customer_email)
        cleanup_user(worker_email)
