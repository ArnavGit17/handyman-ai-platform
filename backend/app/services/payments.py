import base64
import os
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from ..models import Customer, Job, Payment, ServiceRequest, Worker

DEFAULT_UPI_ID = "handyman@upi"
MERCHANT_NAME = "HANDYMAN Demo"


def merchant_upi_id() -> str:
    configured = os.getenv("HANDYMAN_UPI_ID", "").strip()
    return configured or DEFAULT_UPI_ID


def upi_demo_mode() -> bool:
    return not os.getenv("HANDYMAN_UPI_ID", "").strip()


def format_amount(amount: float) -> str:
    return f"{float(amount):.2f}".rstrip("0").rstrip(".")


def build_upi_payload(payment: Payment, job: Job) -> str:
    reference = f"HANDYMAN-JOB-{job.id}-PAY-{payment.id}"
    params = {
        "pa": payment.upi_id,
        "pn": MERCHANT_NAME,
        "am": format_amount(payment.amount),
        "cu": payment.currency,
        "tn": f"Handyman job {job.id} payment {payment.id}",
        "tr": reference,
    }
    return f"upi://pay?{urlencode(params)}"


def qr_image_data_url(qr_payload: str) -> str:
    try:
        import qrcode
        image = qrcode.make(qr_payload)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except ImportError:
        return ""


def ensure_payment_for_job(db: Session, job: Job) -> Payment:
    payment = db.query(Payment).filter(Payment.job_id == job.id).first()
    if payment:
        return payment

    payment = Payment(
        job_id=job.id,
        customer_id=job.customer_id,
        worker_id=job.worker_id,
        amount=float(job.amount or 0),
        currency="INR",
        status="pending",
        payment_method="UPI_QR",
        upi_id=merchant_upi_id(),
        transaction_reference=None,
        qr_payload="",
        created_at=datetime.utcnow(),
        paid_at=None,
    )
    db.add(payment)
    db.flush()
    payment.qr_payload = build_upi_payload(payment, job)
    return payment


def payment_response(db: Session, payment: Payment, include_qr: bool = True) -> dict:
    job = db.get(Job, payment.job_id)
    worker = db.get(Worker, payment.worker_id)
    request = db.get(ServiceRequest, job.request_id) if job else None
    return {
        "job_id": payment.job_id,
        "payment_id": payment.id,
        "customer_id": payment.customer_id,
        "worker_id": payment.worker_id,
        "worker_name": worker.name if worker else None,
        "request_id": job.request_id if job else None,
        "service_type": request.service_type if request else None,
        "amount": payment.amount,
        "currency": payment.currency,
        "status": payment.status,
        "payment_method": payment.payment_method,
        "upi_id": payment.upi_id,
        "qr_payload": payment.qr_payload,
        "qr_image": qr_image_data_url(payment.qr_payload) if include_qr else None,
        "transaction_reference": payment.transaction_reference,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "demo_mode": upi_demo_mode() or payment.upi_id == DEFAULT_UPI_ID,
        "demo_notice": "Demo Payment: this records a customer-submitted UPI reference and does not verify with a bank.",
    }


def payment_history_item(db: Session, payment: Payment) -> dict:
    job = db.get(Job, payment.job_id)
    request = db.get(ServiceRequest, job.request_id) if job else None
    worker = db.get(Worker, payment.worker_id)
    customer = db.get(Customer, payment.customer_id)
    return {
        "payment_id": payment.id,
        "job_id": payment.job_id,
        "request_id": job.request_id if job else None,
        "service": request.service_type if request else None,
        "worker": worker.name if worker else None,
        "customer": customer.name if customer else None,
        "date": (payment.paid_at or payment.created_at).isoformat() if (payment.paid_at or payment.created_at) else None,
        "amount": payment.amount,
        "currency": payment.currency,
        "status": payment.status,
        "payment_method": payment.payment_method,
        "transaction_reference": payment.transaction_reference,
    }
