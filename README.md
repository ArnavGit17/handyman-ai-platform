# HANDYMAN

**Smart work. Fair opportunities. Stronger communities.**

HANDYMAN is a presentation-ready prototype of a cooperative-owned household services platform. Its core feature is an explainable Cooperative Intelligence Engine that allocates work using verified skill, availability, distance, urgency, workload balance, and fair opportunity.

## What is implemented

- FastAPI + SQLAlchemy + SQLite backend
- Deterministic synthetic network of 40 workers and historical demand data
- Emergency and normal service requests
- Explainable worker ranking with configurable weights
- Worker acceptance, start, completion, and rating lifecycle
- Worker skill passport and transparent earnings view
- Cooperative workforce, demand, fairness, and governance dashboard
- Simple moving-average-style demand baseline

## Run it

Backend:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Frontend in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo flow

1. Open Customer and submit the prefilled emergency plumbing request.
2. Inspect the calculated match score and explanation for Rajesh Kumar.
3. Confirm the worker, open Worker desk, and accept/start the job.
4. Complete the service and open Cooperative to see network intelligence.

The prototype uses synthetic data. It does not claim production verification, payments, GPS, or trained deep learning. The matching engine is transparent, deterministic, and easy to audit.
