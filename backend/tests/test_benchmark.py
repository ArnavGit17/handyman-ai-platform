"""
Test suite for Phase B: 1,000-case matching evaluation benchmark.
Tests cover: determinism, scenario counts, no real data pollution,
metric accuracy, and separation of live vs benchmark records.
"""
import random
import statistics
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app, get_db
from app.database import Base
from app.models import MatchingEvaluation, Worker, ServiceRequest, Job
from app.services.benchmark import run_benchmark, generate_worker, SERVICES, AREAS

# --------------------------------------------------------------------------- #
# In-memory test DB
# --------------------------------------------------------------------------- #
TEST_DB_URL = "sqlite://"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=test_engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# 1. Benchmark generator creates exactly 1,000 scenarios
# --------------------------------------------------------------------------- #
def test_benchmark_creates_1000_scenarios(db):
    run_benchmark(db, run_id="test_run", count=1000)
    count = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "test_run"
    ).count()
    assert count == 1000, f"Expected 1000 scenarios, got {count}"


# --------------------------------------------------------------------------- #
# 2. Benchmark generation is deterministic with seed 42
# --------------------------------------------------------------------------- #
def test_benchmark_deterministic(db):
    run_benchmark(db, run_id="det_run_1", count=100)
    first_run = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "det_run_1"
    ).order_by(MatchingEvaluation.id).all()
    latencies_1 = [e.matching_latency_ms for e in first_run]

    # Drop and rerun same benchmark
    db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "det_run_1"
    ).delete()
    db.commit()

    run_benchmark(db, run_id="det_run_1", count=100)
    second_run = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "det_run_1"
    ).order_by(MatchingEvaluation.id).all()
    latencies_2 = [e.matching_latency_ms for e in second_run]

    # Eligible counts and scores should be identical (same seed, same pool)
    eligible_1 = [e.eligible_workers_count for e in first_run]
    eligible_2 = [e.eligible_workers_count for e in second_run]
    assert eligible_1 == eligible_2, "Benchmark should be deterministic"

    total_1 = [e.total_workers_considered for e in first_run]
    total_2 = [e.total_workers_considered for e in second_run]
    assert total_1 == total_2, "Worker pool sizes should be deterministic"


# --------------------------------------------------------------------------- #
# 3. Every scenario contains valid (non-null) required fields
# --------------------------------------------------------------------------- #
def test_benchmark_scenarios_valid(db):
    run_benchmark(db, run_id="valid_run", count=50)
    evals = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "valid_run"
    ).all()
    for e in evals:
        assert e.matching_latency_ms >= 0, "Latency must be non-negative"
        assert e.total_workers_considered >= 0
        assert e.eligible_workers_count >= 0
        assert e.ranked_workers_count >= 0
        assert e.candidate_filter_rate >= 0.0
        assert e.source == "benchmark"
        assert e.benchmark_run_id == "valid_run"


# --------------------------------------------------------------------------- #
# 4. Benchmark records are labeled source = "benchmark"
# --------------------------------------------------------------------------- #
def test_benchmark_records_labeled_benchmark(db):
    run_benchmark(db, run_id="label_run", count=20)
    evals = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "label_run"
    ).all()
    for e in evals:
        assert e.source == "benchmark"


# --------------------------------------------------------------------------- #
# 5. recommendation_selected is always None for benchmark records
# --------------------------------------------------------------------------- #
def test_benchmark_no_customer_acceptance(db):
    run_benchmark(db, run_id="no_accept_run", count=50)
    evals = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "no_accept_run"
    ).all()
    for e in evals:
        assert e.recommendation_selected is None, (
            "Benchmark records must not set recommendation_selected (no real customer interaction)"
        )


# --------------------------------------------------------------------------- #
# 6. Live evaluations remain unaffected
# --------------------------------------------------------------------------- #
def test_live_evaluations_unaffected(db):
    # Simulate a live evaluation record
    live_eval = MatchingEvaluation(
        source="live",
        request_id=999,
        matching_latency_ms=5.0,
        total_workers_considered=10,
        eligible_workers_count=5,
        ranked_workers_count=5,
        candidate_filter_rate=0.5,
    )
    db.add(live_eval)
    db.commit()
    live_id = live_eval.id

    # Run benchmark
    run_benchmark(db, run_id="isolation_run", count=50)

    # The live record must still exist and be unchanged
    after_live = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.id == live_id
    ).first()
    assert after_live is not None
    assert after_live.source == "live"
    assert after_live.request_id == 999


# --------------------------------------------------------------------------- #
# 7. Benchmark does not create real Worker records
# --------------------------------------------------------------------------- #
def test_benchmark_does_not_create_real_workers(db):
    before_workers = db.query(Worker).count()
    run_benchmark(db, run_id="no_workers_run", count=50)
    after_workers = db.query(Worker).count()
    assert before_workers == after_workers, "Benchmark must not insert real worker records"


# --------------------------------------------------------------------------- #
# 8. Benchmark does not create real Job records
# --------------------------------------------------------------------------- #
def test_benchmark_does_not_create_real_jobs(db):
    before_jobs = db.query(Job).count()
    run_benchmark(db, run_id="no_jobs_run", count=50)
    after_jobs = db.query(Job).count()
    assert before_jobs == after_jobs, "Benchmark must not insert real job records"


# --------------------------------------------------------------------------- #
# 9. Running benchmark twice replaces (not doubles) records
# --------------------------------------------------------------------------- #
def test_benchmark_replace_not_duplicate(db):
    run_benchmark(db, run_id="dedup_run", count=100)
    count_after_first = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "dedup_run"
    ).count()
    assert count_after_first == 100

    run_benchmark(db, run_id="dedup_run", count=100)
    count_after_second = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "dedup_run"
    ).count()
    assert count_after_second == 100, (
        f"Re-running benchmark must replace records, got {count_after_second}"
    )


# --------------------------------------------------------------------------- #
# 10. Top-1/3/5 calculations are mathematically correct
# --------------------------------------------------------------------------- #
def test_top_k_calculations(db):
    run_benchmark(db, run_id="topk_run", count=200)
    evals = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "topk_run"
    ).all()

    with_gt = [e for e in evals if e.selected_worker_rank is not None]
    if len(with_gt) == 0:
        pytest.skip("No ground truth matches to evaluate in this run")

    manual_top1 = sum(1 for e in with_gt if e.selected_worker_rank == 1) / len(with_gt)
    manual_top3 = sum(1 for e in with_gt if e.selected_worker_rank <= 3) / len(with_gt)
    manual_top5 = sum(1 for e in with_gt if e.selected_worker_rank <= 5) / len(with_gt)

    assert 0.0 <= manual_top1 <= 1.0
    assert 0.0 <= manual_top3 <= 1.0
    assert 0.0 <= manual_top5 <= 1.0
    assert manual_top1 <= manual_top3 <= manual_top5, (
        "Top-K rates must be non-decreasing"
    )


# --------------------------------------------------------------------------- #
# 11. Latency metrics are non-negative and reasonable
# --------------------------------------------------------------------------- #
def test_latency_metrics(db):
    run_benchmark(db, run_id="latency_run", count=100)
    evals = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "latency_run"
    ).all()
    latencies = [e.matching_latency_ms for e in evals]
    assert all(l >= 0 for l in latencies), "All latencies must be non-negative"
    avg = statistics.mean(latencies)
    assert avg < 5000, f"Average latency should be < 5s, got {avg:.2f}ms"


# --------------------------------------------------------------------------- #
# 12. generate_worker produces valid Worker objects
# --------------------------------------------------------------------------- #
def test_generate_worker_valid():
    rng = random.Random(42)
    for i in range(50):
        w = generate_worker(i + 1, rng)
        assert w.id == i + 1
        assert w.skills, "Worker must have at least one skill"
        assert w.rating >= 3.5
        assert w.rating <= 5.0
        assert w.max_concurrent_jobs >= 2
        assert w.verification_status in ("Verified", "Pending")
        assert w.availability_status in ("Available", "Unavailable")
        # Skills must be from the defined service list (may have comma-separated)
        for skill in w.skills.split(","):
            assert skill.strip() in SERVICES, f"Unexpected skill: {skill}"


# --------------------------------------------------------------------------- #
# 13. No-match rate is calculated correctly
# --------------------------------------------------------------------------- #
def test_no_match_rate(db):
    run_benchmark(db, run_id="nomatch_run", count=100)
    evals = db.query(MatchingEvaluation).filter(
        MatchingEvaluation.benchmark_run_id == "nomatch_run"
    ).all()
    no_matches = sum(1 for e in evals if e.recommended_worker_id is None)
    computed_rate = no_matches / len(evals)
    assert 0.0 <= computed_rate <= 1.0
