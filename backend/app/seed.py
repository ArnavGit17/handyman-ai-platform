from random import Random
from sqlalchemy.orm import Session
from .models import Customer, Demand, Proposal, Worker

NAMES = ["Rajesh Kumar", "Amit Sharma", "Suresh Kumar", "Vijay Singh", "Priya Menon", "Meena Devi", "Arjun Patel", "Nisha Verma", "Mohan Das", "Kavita Rao"]
SERVICES = ["Plumbing", "Electrical", "Carpentry", "Cleaning", "Painting", "Appliance Repair"]
AREAS = ["Area A", "Area B", "Area C", "Area D"]


def seed_database(db: Session):
    if db.query(Worker).count(): return
    rng = Random(26089)
    for index in range(40):
        service = SERVICES[index % len(SERVICES)]
        name = NAMES[index % len(NAMES)] if index < 10 else f"{NAMES[index % len(NAMES)].split()[0]} {['Khan', 'Joshi', 'Iyer', 'Bose'][index % 4]}"
        skills = service
        if index % 5 == 0: skills += ", Plumbing"
        db.add(Worker(name=name, phone=f"987650{index:04d}", skills=skills, certifications=f"{service} Level {1 + index % 3}", experience_years=2 + index % 9, latitude=12.9716 if index == 0 else 12.9716 + rng.uniform(-.035, .035), longitude=77.5946 if index == 0 else 77.5946 + rng.uniform(-.035, .035), area=AREAS[index % 4], availability=index == 0 or index % 7 != 0, current_workload=3 if index == 0 else 6 + index % 15, rating=round(4.2 + (index % 8) / 10, 1), jobs_completed=40 + index * 7, earnings=32000 + index * 1800, recent_jobs=3 if index == 0 else 7 + index % 16))
    db.add(Customer(name="Ananya Rao", phone="9876543210", area="Area A", latitude=12.9716, longitude=77.5946))
    for index in range(120):
        db.add(Demand(date=f"2026-09-{(index % 9) + 1:02d}", area=AREAS[index % 4], service_type=SERVICES[index % 6], request_count=12 + index % 35, emergency_requests=index % 8, average_duration=45 + index % 50))
    db.add(Proposal(title="Reduce cooperative service allocation from 8% to 6%", description="Prototype worker proposal for cooperative discussion.", yes_votes=72, no_votes=28))
    db.commit()
