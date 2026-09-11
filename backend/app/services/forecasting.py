from sqlalchemy import func
from sqlalchemy.orm import Session
from ..models import Demand, Worker


def get_forecast(db: Session):
    rows = db.query(Demand.area, Demand.service_type, func.avg(Demand.request_count).label("average")).group_by(Demand.area, Demand.service_type).all()
    result = []
    for area, service, average in rows:
        available = db.query(Worker).filter(Worker.area == area, Worker.availability == True).count()
        expected = round(average * 1.12)
        shortage = max(0, expected - available)
        result.append({"area": area, "service": service, "expected_demand": expected, "available_workers": available, "predicted_shortage": shortage, "level": "HIGH" if shortage > 8 else "MEDIUM" if shortage else "HEALTHY"})
    return result
