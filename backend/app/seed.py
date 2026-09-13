from random import Random
from sqlalchemy.orm import Session
from .models import Customer, Demand, Job, Proposal, ServiceRequest, Worker

NAMES = ["Rajesh Kumar", "Amit Sharma", "Suresh Kumar", "Vijay Singh", "Priya Menon", "Meena Devi", "Arjun Patel", "Nisha Verma", "Mohan Das", "Kavita Rao", "Rohan Gupta", "Lakshmi Iyer", "Imran Khan", "Deepak Joshi", "Anjali Nair"]
SERVICES = ["Plumbing", "Electrical", "Carpentry", "Cleaning", "Painting", "Appliance Repair"]
AREAS = ["Area A", "Area B", "Area C", "Area D", "Area E"]
SERVICE_COUNTS = {"Plumbing": 10, "Electrical": 9, "Carpentry": 8, "Cleaning": 8, "Painting": 8, "Appliance Repair": 7}


def seed_database(db: Session):
    demo_workers = db.query(Worker).filter(Worker.is_demo == True).all()
    if len(demo_workers) > 50:
        for worker in demo_workers[50:]:
            db.delete(worker)

    demo_workers = db.query(Worker).filter(Worker.is_demo == True).all()
    if len(demo_workers) < 50:
        rng = Random(26089)
        existing_demo_names = {worker.name for worker in demo_workers}
        service_list = [service for service, count in SERVICE_COUNTS.items() for _ in range(count)]
        for index, service in enumerate(service_list[:50 - len(demo_workers)]):
            name = NAMES[index % len(NAMES)] if index < len(NAMES) else f"{NAMES[index % len(NAMES)].split()[0]} {['Bose', 'Patil', 'Reddy', 'Das'][index % 4]}"
            if name in existing_demo_names:
                continue
            skills = [service]
            if index in (1, 11, 21, 31, 41):
                skills.append("Plumbing")
            certification = f"{service} Level {1 + index % 3}" if index % 6 != 4 else ""
            is_showcase = index == 0
            db.add(Worker(name=name, phone=f"987650{index:04d}", skills=", ".join(skills), certifications=certification, experience_years=8 if is_showcase else 2 + index % 9, latitude=12.9716 if is_showcase else 12.9716 + rng.uniform(-.035, .035), longitude=77.5946 if is_showcase else 77.5946 + rng.uniform(-.035, .035), area=AREAS[index % len(AREAS)], availability=True, availability_status="Available", current_workload=0, max_concurrent_jobs=3, rating=4.8 if is_showcase else round(4.2 + (index % 8) / 10, 1), jobs_completed=327 if is_showcase else 40 + index * 7, earnings=68000 if is_showcase else 32000 + index * 1800, verification_status="Verified", recent_jobs=3 if is_showcase else 1 + index % 6, is_demo=True, service_areas=AREAS[index % len(AREAS)], hourly_rate=700))

    for worker in db.query(Worker).filter(Worker.is_demo == True).all():
        worker.availability = True
        worker.availability_status = "Available"
        worker.current_workload = 0
        worker.max_concurrent_jobs = 3
        worker.verification_status = "Verified"
        if not worker.service_areas:
            worker.service_areas = worker.area
        if not worker.skills:
            worker.skills = "General"

    if not db.query(Customer).filter(Customer.is_demo == True).first():
        db.add(Customer(name="Ananya Rao", phone="9876543210", area="Area A", latitude=12.9716, longitude=77.5946, is_demo=True))
    if db.query(Demand).count() == 0:
        for index in range(120):
            db.add(Demand(date=f"2026-09-{(index % 9) + 1:02d}", area=AREAS[index % 4], service_type=SERVICES[index % 6], request_count=12 + index % 35, emergency_requests=index % 8, average_duration=45 + index % 50))
    if db.query(Proposal).count() == 0:
        db.add(Proposal(title="Reduce cooperative service allocation from 8% to 6%", description="Prototype worker proposal for cooperative discussion.", yes_votes=72, no_votes=28))
    db.commit()
