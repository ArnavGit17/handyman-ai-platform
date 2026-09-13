import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, AlertTriangle, BarChart3, CheckCircle2, ChevronLeft, ChevronRight, Clock, Filter, FlaskConical, RefreshCw, Sparkles, Target, TrendingUp, Users, XCircle, Zap } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const PAGE_SIZE = 20;
const pct = (v) => (v == null ? "\u2014" : (v * 100).toFixed(1) + "%");
const fms = (v) => (v == null ? "\u2014" : Number(v).toFixed(1) + " ms");
const num = (v, d = 1) => (v == null ? "\u2014" : Number(v).toFixed(d));

function filterByRange(records, range) {
  if (range === "all") return records;
  const cut = { today: 86400000, "7d": 604800000, "30d": 2592000000 }[range];
  return records.filter((r) => new Date(r.created_at).getTime() >= Date.now() - cut);
}

function buildScoreBuckets(records) {
  const b = { "90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "<60": 0 };
  let total = 0;
  records.forEach((r) => {
    const s = r.recommended_worker_score;
    if (s == null) return;
    total++;
    if (s >= 90) b["90-100"]++;
    else if (s >= 80) b["80-89"]++;
    else if (s >= 70) b["70-79"]++;
    else if (s >= 60) b["60-69"]++;
    else b["<60"]++;
  });
  if (total === 0) return null;
  return Object.entries(b).map(([label, count]) => ({ label, count, pct: ((count / total) * 100).toFixed(1) }));
}

function buildTopKScores(records) {
  const sums = [0, 0, 0, 0, 0];
  const counts = [0, 0, 0, 0, 0];
  records.forEach((r) => {
    [r.top_1_score, r.top_2_score, r.top_3_score, r.top_4_score, r.top_5_score].forEach((s, i) => {
      if (s != null) { sums[i] += s; counts[i]++; }
    });
  });
  return [1, 2, 3, 4, 5].map((rank, i) => ({
    rank: "Rank #" + rank,
    score: counts[i] > 0 ? +(sums[i] / counts[i]).toFixed(1) : null,
  }));
}

function pctile(arr, p) {
  if (!arr.length) return null;
  const sorted = [...arr].sort((a, b) => a - b);
  const k = (sorted.length - 1) * p;
  const f = Math.floor(k);
  const c = Math.ceil(k);
  return f === c ? sorted[f] : sorted[f] * (c - k) + sorted[c] * (k - f);
}

function deriveMetrics(rs, isBenchmark = false) {
  if (!rs.length) return null;
  const lat = rs.map((r) => r.matching_latency_ms);
  const nm = rs.filter((r) => r.recommended_worker_id == null).length;
  const sc = rs.filter((r) => r.recommended_worker_score != null).map((r) => r.recommended_worker_score);
  const el = rs.map((r) => r.eligible_workers_count);
  const cfr = rs.map((r) => r.candidate_filter_rate);
  const avg = (a) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;

  let top1 = null, top3 = null, top5 = null;
  let aiAccept = null, altSel = null;

  if (isBenchmark) {
    // Benchmark: Top-K Hit Rate = fraction where GT worker appears in top-K of ranked results.
    // Benchmark records have selected_worker_rank = GT rank, recommendation_selected = null.
    const withGtRank = rs.filter((r) => r.selected_worker_rank != null);
    top1 = withGtRank.length ? withGtRank.filter((r) => r.selected_worker_rank === 1).length / withGtRank.length : null;
    top3 = withGtRank.length ? withGtRank.filter((r) => r.selected_worker_rank <= 3).length / withGtRank.length : null;
    top5 = withGtRank.length ? withGtRank.filter((r) => r.selected_worker_rank <= 5).length / withGtRank.length : null;
    // AI Acceptance / Alternative are NOT applicable for benchmark (no real customer choice).
    aiAccept = null;
    altSel = null;
  } else {
    // Live: Top-K Selection Rate uses ONLY source="live" (or legacy untagged) records.
    // This ensures benchmark GT ranks do NOT pollute customer selection metrics.
    const liveOnly = rs.filter((r) => r.source === "live" || !r.source);
    const withRank = liveOnly.filter((r) => r.selected_worker_rank != null);
    top1 = withRank.length ? withRank.filter((r) => r.selected_worker_rank === 1).length / withRank.length : null;
    top3 = withRank.length ? withRank.filter((r) => r.selected_worker_rank <= 3).length / withRank.length : null;
    top5 = withRank.length ? withRank.filter((r) => r.selected_worker_rank <= 5).length / withRank.length : null;
    // AI Acceptance Rate = of confirmed selections, how many chose the AI rank-1 recommendation.
    // Only count records where customer explicitly selected (recommendation_selected is not null).
    const confirmedSels = liveOnly.filter((r) => r.recommendation_selected != null);
    aiAccept = confirmedSels.length ? confirmedSels.filter((r) => r.recommendation_selected === true).length / confirmedSels.length : null;
    altSel = confirmedSels.length ? confirmedSels.filter((r) => r.recommendation_selected === false).length / confirmedSels.length : null;
  }

  return {
    total_evaluations: rs.length,
    live_count: isBenchmark ? 0 : rs.filter((r) => r.source === "live" || !r.source).length,
    average_latency_ms: avg(lat),
    p50_latency_ms: pctile(lat, 0.5),
    p95_latency_ms: pctile(lat, 0.95),
    p99_latency_ms: pctile(lat, 0.99),
    average_match_score: avg(sc),
    average_eligible_candidates: avg(el),
    average_candidate_filter_rate: avg(cfr),
    no_match_rate: rs.length ? nm / rs.length : null,
    top_1_selection_rate: top1,
    top_3_selection_rate: top3,
    top_5_selection_rate: top5,
    ai_recommendation_acceptance_rate: aiAccept,
    alternative_selection_rate: altSel,
  };
}

function KpiCard({ label, value, sub, icon: Icon, color = "orange", info, muted }) {
  const [show, setShow] = useState(false);
  const colors = {
    orange: ["#fff1ea", "#c75439"], green: ["#edf8f2", "#234f3e"],
    blue: ["#eff6ff", "#1d4ed8"], amber: ["#fffbeb", "#92400e"],
    purple: ["#f5f3ff", "#4c1d95"],
  };
  const [bg, text] = colors[color] || colors.orange;
  return (
    <div className={"eval-kpi-card" + (muted ? " eval-kpi-muted" : "")}>
      <div className="eval-kpi-icon" style={{ background: bg, color: text }}><Icon size={17} /></div>
      <span className="eval-kpi-label">
        {label}
        {info && <button type="button" className="eval-info-btn" onClick={() => setShow((s) => !s)}>?</button>}
      </span>
      <strong className="eval-kpi-value">{value}</strong>
      {sub && <small className="eval-kpi-sub">{sub}</small>}
      {show && <div className="eval-info-tooltip">{info}</div>}
    </div>
  );
}

function SecHead({ eyebrow, title, subtitle }) {
  return (
    <div className="eval-section-head">
      <span className="eyebrow">{eyebrow}</span>
      <h3>{title}</h3>
      {subtitle && <p className="eval-section-sub">{subtitle}</p>}
    </div>
  );
}

function LatBar({ label, value, max }) {
  const w = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="eval-lat-row">
      <span className="eval-lat-label">{label}</span>
      <div className="eval-lat-track"><div className="eval-lat-fill" style={{ width: w + "%" }} /></div>
      <span className="eval-lat-val">{fms(value)}</span>
    </div>
  );
}

const BUCKET_COLORS = ["#3c8b6c", "#65bf91", "#e76f51", "#f4a261", "#94a3b8"];

export default function EvaluationDashboard({ apiFetch }) {
  const [allRecords, setAllRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [sourceFilter, setSourceFilter] = useState("all"); // "all" | "live" | "benchmark"
  const [dateRange, setDateRange] = useState("all");
  const [page, setPage] = useState(0);
  const [benchmarkRunning, setBenchmarkRunning] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState(null);
  const lastFetch = useRef(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError(null);
    try {
      // Fetch all records (up to 2000 to cover benchmark + live)
      const rr = await apiFetch("/matching/evaluations?limit=2000");
      if (!rr.ok) {
        const b = await rr.json().catch(() => ({}));
        let errMsg = "Unable to load evaluation data.";
        if (b.detail) {
          errMsg = Array.isArray(b.detail) ? b.detail.map((e) => e.msg).join(", ") : b.detail;
        }
        throw new Error(errMsg);
      }
      const rd = await rr.json();
      setAllRecords(rd);
      lastFetch.current = Date.now();
    } catch (err) {
      setError(err.message || "Unable to load evaluation data.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [apiFetch]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(0); }, [dateRange, sourceFilter]);

  const runBenchmark = async () => {
    setBenchmarkRunning(true);
    setBenchmarkResult(null);
    try {
      const resp = await apiFetch("/matching/benchmark/run", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const errMsg = data.detail
          ? Array.isArray(data.detail)
            ? data.detail.map((e) => e.msg).join(", ")
            : String(data.detail)
          : `Server error ${resp.status}`;
        setBenchmarkResult({ error: `Benchmark failed: ${errMsg}` });
        return;
      }
      setBenchmarkResult(data);
      await load(true); // Refresh records after successful run
    } catch (e) {
      setBenchmarkResult({ error: `Benchmark failed: ${e.message}` });
    } finally {
      setBenchmarkRunning(false);
    }
  };

  // Split records by source
  const liveRecords = allRecords.filter((r) => r.source === "live" || !r.source);
  const benchmarkRecords = allRecords.filter((r) => r.source === "benchmark");

  // Active records based on source filter
  const isBenchmarkView = sourceFilter === "benchmark";
  const isAllView = sourceFilter === "all";

  // For "all" view, keep live and benchmark strictly separate for metrics
  const sourceRecords = sourceFilter === "live" ? liveRecords
    : sourceFilter === "benchmark" ? benchmarkRecords
    : allRecords;

  // Apply date filter only to live records (benchmark has synthetic timestamps)
  const fr = isBenchmarkView ? sourceRecords : filterByRange(
    isAllView ? liveRecords : sourceRecords, dateRange
  );
  // For "all" view, benchmark records displayed separately (not date-filtered)
  const frBench = isAllView ? benchmarkRecords : null;

  // Derive metrics — always source-specific
  // For "all" view: s = live metrics, sBench = benchmark metrics (both computed independently)
  const s = fr.length > 0 ? deriveMetrics(fr, isBenchmarkView) : null;
  const sBench = isAllView && frBench && frBench.length > 0 ? deriveMetrics(frBench, true) : null;

  const topKSel = s
    ? [
        { name: isBenchmarkView ? "Top-1 Hit" : "Top-1 Sel.", rate: s.top_1_selection_rate != null ? +(s.top_1_selection_rate * 100).toFixed(1) : null },
        { name: isBenchmarkView ? "Top-3 Hit" : "Top-3 Sel.", rate: s.top_3_selection_rate != null ? +(s.top_3_selection_rate * 100).toFixed(1) : null },
        { name: isBenchmarkView ? "Top-5 Hit" : "Top-5 Sel.", rate: s.top_5_selection_rate != null ? +(s.top_5_selection_rate * 100).toFixed(1) : null },
      ].filter((d) => d.rate != null)
    : [];
  const topKBench = sBench
    ? [
        { name: "Top-1 Hit", rate: sBench.top_1_selection_rate != null ? +(sBench.top_1_selection_rate * 100).toFixed(1) : null },
        { name: "Top-3 Hit", rate: sBench.top_3_selection_rate != null ? +(sBench.top_3_selection_rate * 100).toFixed(1) : null },
        { name: "Top-5 Hit", rate: sBench.top_5_selection_rate != null ? +(sBench.top_5_selection_rate * 100).toFixed(1) : null },
      ].filter((d) => d.rate != null)
    : [];

  const latMax = s ? Math.max(s.average_latency_ms || 0, s.p50_latency_ms || 0, s.p95_latency_ms || 0, s.p99_latency_ms || 0) : 0;
  // Score/topK charts: live-only in All view, or active filter records otherwise
  const displayRecords = isAllView ? fr : fr; // fr is always live-or-active filtered
  const buckets = buildScoreBuckets(isAllView ? [...fr, ...(frBench || [])] : fr);
  const topKSc = buildTopKScores(isAllView ? [...fr, ...(frBench || [])] : fr).filter((d) => d.score != null);
  // Worker allocation: always live-only (benchmark has synthetic selected_worker_id)
  const liveForAlloc = isAllView ? fr : (isBenchmarkView ? [] : fr);
  const uniqW = new Set(liveForAlloc.filter((r) => r.selected_worker_id && (r.source === "live" || !r.source)).map((r) => r.selected_worker_id)).size;
  const totalSel = liveForAlloc.filter((r) => (r.source === "live" || !r.source) && r.selected_worker_id != null).length;
  // Table shows active-source records
  const tableRecords = isAllView ? [...fr, ...(frBench || [])] : fr;
  const sorted = [...tableRecords].sort((a, b) => b.id - a.id);
  const tPages = Math.ceil(sorted.length / PAGE_SIZE);
  const pageRecs = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const rlabel = { today: "Today", "7d": "Last 7 days", "30d": "Last 30 days", all: "All time" }[dateRange];

  const latestBenchRun = benchmarkRecords.length > 0
    ? benchmarkRecords[0]?.created_at
    : null;

  if (loading) return (
    <div className="eval-shell">
      <div className="eval-loading"><div className="eval-spinner" /><p>Loading evaluation data\u2026</p></div>
    </div>
  );

  if (error) return (
    <div className="eval-shell">
      <div className="eval-error">
        <AlertTriangle size={32} />
        <strong>Unable to load evaluation data</strong>
        <p>{error}</p>
        <button className="primary" onClick={() => load()}><RefreshCw size={15} /> Try again</button>
      </div>
    </div>
  );

  return (
    <div className="eval-shell">
      {/* Header */}
      <div className="eval-header">
        <div>
          <span className="eyebrow">AI SYSTEM TELEMETRY</span>
          <h2 className="eval-title">AI Matching Evaluation</h2>
          <p className="eval-subtitle">
            {allRecords.length} total records &mdash; <strong>{liveRecords.length}</strong> live &middot; <strong>{benchmarkRecords.length}</strong> benchmark.
            {lastFetch.current && <> Last refreshed {new Date(lastFetch.current).toLocaleTimeString("en-IN")}.</>}
          </p>
        </div>
        <div className="eval-header-actions">
          {/* Source filter toggle */}
          <div className="eval-source-toggle">
            {[["all", "All"], ["live", "Live"], ["benchmark", "Benchmark"]].map(([v, l]) => (
              <button key={v} type="button" className={"eval-source-btn" + (sourceFilter === v ? " active" : "")} onClick={() => setSourceFilter(v)}>{l}</button>
            ))}
          </div>
          {/* Date range (only for live/all) */}
          {!isBenchmarkView && (
            <div className="eval-filter-row">
              <Filter size={14} />
              {[["today", "Today"], ["7d", "7 days"], ["30d", "30 days"], ["all", "All time"]].map(([v, l]) => (
                <button key={v} type="button" className={"eval-range-btn" + (dateRange === v ? " active" : "")} onClick={() => setDateRange(v)}>{l}</button>
              ))}
            </div>
          )}
          <button type="button" className="ghost-button eval-refresh-btn" onClick={() => { setRefreshing(true); load(true); }} disabled={refreshing}>
            <RefreshCw size={15} className={refreshing ? "eval-spin" : ""} />
            {refreshing ? "Refreshing\u2026" : "Refresh"}
          </button>
        </div>
      </div>

      {/* Benchmark panel */}
      <section className="eval-section eval-benchmark-panel">
        <div className="eval-benchmark-header">
          <div>
            <span className="eyebrow">REPRODUCIBLE BENCHMARK</span>
            <h3>1,000-Case Matching Benchmark</h3>
            <p className="eval-section-sub">
              Exercises the live matching engine against {benchmarkRecords.length > 0 ? "1,000" : "0"} deterministic synthetic scenarios (seed 42).
              Ground truth labels are based on explicit scenario design — not real customer decisions.
              {latestBenchRun && <> Latest run: {new Date(latestBenchRun).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}.</>}
            </p>
          </div>
          <div className="eval-benchmark-actions">
            <button
              type="button"
              className={"primary eval-run-btn" + (benchmarkRunning ? " loading" : "")}
              onClick={runBenchmark}
              disabled={benchmarkRunning}
              id="run-benchmark-btn"
            >
              <FlaskConical size={16} />
              {benchmarkRunning ? "Running 1,000 scenarios\u2026" : "Run 1,000-Case Benchmark"}
            </button>
          </div>
        </div>
        {benchmarkResult && (
          <div className={"eval-benchmark-result" + (benchmarkResult.error ? " error" : " success")}>
            {benchmarkResult.error
              ? <><AlertTriangle size={16} /> Error: {benchmarkResult.error}</>
              : <><CheckCircle2 size={16} /> {benchmarkResult.message} &mdash; {benchmarkResult.scenarios} scenarios evaluated.</>}
          </div>
        )}
        {benchmarkRecords.length > 0 && (() => {
          const bm = deriveMetrics(benchmarkRecords, true);
          return bm ? (
            <div className="eval-benchmark-kpis">
              <div className="eval-bench-kpi"><span>Total Scenarios</span><strong>{bm.total_evaluations}</strong></div>
              <div className="eval-bench-kpi"><span>Top-1 Hit Rate</span><strong>{pct(bm.top_1_selection_rate)}</strong></div>
              <div className="eval-bench-kpi"><span>Top-3 Hit Rate</span><strong>{pct(bm.top_3_selection_rate)}</strong></div>
              <div className="eval-bench-kpi"><span>Top-5 Hit Rate</span><strong>{pct(bm.top_5_selection_rate)}</strong></div>
              <div className="eval-bench-kpi"><span>Avg Match Score</span><strong>{num(bm.average_match_score)} / 100</strong></div>
              <div className="eval-bench-kpi"><span>Avg Latency</span><strong>{fms(bm.average_latency_ms)}</strong></div>
              <div className="eval-bench-kpi"><span>No-Match Rate</span><strong>{pct(bm.no_match_rate)}</strong></div>
            </div>
          ) : null;
        })()}
      </section>

      {fr.length === 0 && (
        <div className="eval-empty">
          {sourceFilter === "benchmark" ? (
            <><FlaskConical size={36} /><strong>No benchmark data yet</strong><p>Click &ldquo;Run 1,000-Case Benchmark&rdquo; above to populate the benchmark dataset.</p></>
          ) : (
            <><Sparkles size={36} /><strong>No evaluations in this view</strong><p>Create a service request or run the benchmark to collect data.</p></>
          )}
        </div>
      )}

      {fr.length > 0 && (<>
        {isAllView && sBench && sBench.total_evaluations > 0 && (
          <section className="eval-section" style={{ marginBottom: "2rem" }}>
            <SecHead
              eyebrow="BENCHMARK PERFORMANCE INDICATORS"
              title="Benchmark Ground Truth Metrics"
              subtitle={`Synthetic test cases \u00b7 ${sBench.total_evaluations} evaluations`}
            />
            <div className="eval-kpi-grid">
              <KpiCard label="Total Evaluations" value={sBench.total_evaluations} sub="Benchmark scenarios" icon={BarChart3} color="orange" />
              <KpiCard label="Top-1 Benchmark Hit Rate" value={pct(sBench.top_1_selection_rate)} sub="GT worker ranked #1" icon={Target} color="green" info="Fraction of scenarios where the ground-truth suitable worker was ranked #1 by the matching engine." />
              <KpiCard label="Top-3 Benchmark Hit Rate" value={pct(sBench.top_3_selection_rate)} sub="GT worker in top 3" icon={TrendingUp} color="green" info="Fraction of scenarios where the ground-truth worker appeared in the top 3 ranked results." />
              <KpiCard label="Top-5 Benchmark Hit Rate" value={pct(sBench.top_5_selection_rate)} sub="GT worker in top 5" icon={TrendingUp} color="green" info="Fraction of scenarios where the ground-truth worker appeared in the top 5 ranked results." />
              <KpiCard label="Avg Latency" value={fms(sBench.average_latency_ms)} sub="Mean scoring time" icon={Clock} color="blue" info="Average time to filter and score all candidate workers." />
              <KpiCard label="P50 Latency" value={fms(sBench.p50_latency_ms)} sub="Median" icon={Zap} color="blue" info="Median matching latency." />
              <KpiCard label="P95 Latency" value={fms(sBench.p95_latency_ms)} sub="95th percentile" icon={Zap} color="blue" info="95th percentile latency." />
              <KpiCard label="P99 Latency" value={fms(sBench.p99_latency_ms)} sub="99th percentile" icon={Zap} color="blue" info="99th percentile latency." />
              <KpiCard label="Avg Match Score" value={num(sBench.average_match_score)} sub="Top candidate / 100" icon={Sparkles} color="orange" info="Average match score assigned to the AI top-ranked candidate." />
              <KpiCard label="No-Match Rate" value={pct(sBench.no_match_rate)} sub="Zero eligible workers" icon={AlertTriangle} color="amber" info="Fraction of requests where no eligible worker was found." />
            </div>
          </section>
        )}

        <section className="eval-section">
          <SecHead
            eyebrow={isAllView ? "LIVE PERFORMANCE INDICATORS" : "KEY PERFORMANCE INDICATORS"}
            title={isBenchmarkView ? "Benchmark Summary Metrics" : isAllView ? "Live Customer Metrics" : "Summary Metrics"}
            subtitle={(isBenchmarkView ? "Benchmark ground truth \u00b7 " : rlabel + " \u00b7 ") + (isAllView ? s?.live_count : fr.length) + " evaluations"}
          />
          <div className="eval-kpi-grid">
            <KpiCard label="Total Evaluations" value={isAllView ? (s?.live_count ?? 0) : (s?.total_evaluations ?? fr.length)} sub={isBenchmarkView ? "Benchmark scenarios" : rlabel} icon={BarChart3} color="orange" />
            <KpiCard label={isBenchmarkView ? "Top-1 Benchmark Hit Rate" : "Top-1 Selection Rate"} value={pct(s?.top_1_selection_rate)} sub={isBenchmarkView ? "GT worker ranked #1" : "Chose AI top pick"} icon={Target} color="green" info={isBenchmarkView ? "Fraction of scenarios where the ground-truth suitable worker was ranked #1 by the matching engine." : "Customer chose the AI rank-1 recommended worker."} />
            <KpiCard label={isBenchmarkView ? "Top-3 Benchmark Hit Rate" : "Top-3 Selection Rate"} value={pct(s?.top_3_selection_rate)} sub={isBenchmarkView ? "GT worker in top 3" : "Chose from top 3"} icon={TrendingUp} color="green" info={isBenchmarkView ? "Fraction of scenarios where the ground-truth worker appeared in the top 3 ranked results." : "Customer chose a worker ranked 1, 2, or 3."} />
            <KpiCard label={isBenchmarkView ? "Top-5 Benchmark Hit Rate" : "Top-5 Selection Rate"} value={pct(s?.top_5_selection_rate)} sub={isBenchmarkView ? "GT worker in top 5" : "Chose from top 5"} icon={TrendingUp} color="green" info={isBenchmarkView ? "Fraction of scenarios where the ground-truth worker appeared in the top 5 ranked results." : "Customer chose any of the top 5 candidates."} />
            {!isBenchmarkView && <KpiCard label="AI Acceptance Rate" value={pct(s?.ai_recommendation_acceptance_rate)} sub="Accepted recommendation" icon={CheckCircle2} color="green" info="How often the customer confirmed the AI rank-1 worker exactly." />}
            {!isBenchmarkView && <KpiCard label="Alternative Selection" value={pct(s?.alternative_selection_rate)} sub="Bypassed recommendation" icon={XCircle} color="amber" info="Customer selected a worker other than the AI rank-1 recommendation." />}
            <KpiCard label="Avg Latency" value={fms(s?.average_latency_ms)} sub="Mean scoring time" icon={Clock} color="blue" info="Average time to filter and score all candidate workers." />
            <KpiCard label="P50 Latency" value={fms(s?.p50_latency_ms)} sub="Median" icon={Zap} color="blue" info="Median matching latency." />
            <KpiCard label="P95 Latency" value={fms(s?.p95_latency_ms)} sub="95th percentile" icon={Zap} color="blue" info="95th percentile latency." />
            <KpiCard label="P99 Latency" value={fms(s?.p99_latency_ms)} sub="99th percentile" icon={Zap} color="blue" info="99th percentile latency." />
            <KpiCard label="Avg Match Score" value={num(s?.average_match_score)} sub="Top candidate / 100" icon={Sparkles} color="orange" info="Average match score assigned to the AI top-ranked candidate." />
            <KpiCard label="No-Match Rate" value={pct(s?.no_match_rate)} sub="Zero eligible workers" icon={AlertTriangle} color="amber" info="Fraction of requests where no eligible worker was found." />
          </div>
        </section>

        <div className="eval-two-col">
          <section className="eval-section eval-panel">
            <SecHead eyebrow="SELECTION QUALITY" title={isBenchmarkView ? "Top-K Benchmark Hit Rates" : "Top-K Selection Rates"} subtitle={isBenchmarkView ? "Ground-truth worker position in ranked results." : "How often customers chose within top K results."} />
            {topKSel.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={topKSel} layout="vertical" margin={{ left: 8, right: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e6e2da" />
                  <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => v + "%"} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 13, fontWeight: 600 }} axisLine={false} tickLine={false} width={60} />
                  <Tooltip formatter={(v) => v + "%"} />
                  <Bar dataKey="rate" radius={[0, 6, 6, 0]} fill="#3c8b6c" label={{ position: "right", formatter: (v) => v + "%", fontSize: 12, fontWeight: 700, fill: "#234f3e" }} />
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="eval-no-data"><p>{isBenchmarkView ? "Run the benchmark to see hit rate data." : "No selection data yet."}</p></div>}
          </section>
          <section className="eval-section eval-panel">
            <SecHead eyebrow="PERFORMANCE" title="Matching Latency" subtitle="Lower latency indicates faster candidate scoring and ranking." />
            <div className="eval-lat-grid">
              <LatBar label="Average" value={s?.average_latency_ms} max={latMax} />
              <LatBar label="P50" value={s?.p50_latency_ms} max={latMax} />
              <LatBar label="P95" value={s?.p95_latency_ms} max={latMax} />
              <LatBar label="P99" value={s?.p99_latency_ms} max={latMax} />
            </div>
            <p className="eval-lat-note">Measured using <code>time.perf_counter()</code> inside the scoring loop &mdash; excludes database I/O and network overhead.</p>
          </section>
        </div>

        <div className="eval-two-col">
          <section className="eval-section eval-panel">
            <SecHead eyebrow="CANDIDATE PIPELINE" title="Candidate Filtering" subtitle="Worker pool statistics per matching operation." />
            <div className="eval-stat-rows">
              {[
                ["Average eligible candidates", num(s?.average_eligible_candidates)],
                ["Average filter rate", pct(s?.average_candidate_filter_rate)],
                ["No-match rate", pct(s?.no_match_rate)],
              ].map(([l, v]) => (
                <div className="eval-stat-row" key={l}><span>{l}</span><strong>{v ?? "\u2014"}</strong></div>
              ))}
            </div>
            <p className="eval-lat-note">Filter rate = fraction of workers eliminated before scoring (skill, availability constraints).</p>
          </section>
          <section className="eval-section eval-panel">
            <SecHead
              eyebrow={isBenchmarkView ? "BENCHMARK GROUND TRUTH" : "RECOMMENDATION QUALITY"}
              title={isBenchmarkView ? "Ground Truth Hit Analysis" : "How Customers Decide"}
              subtitle={isBenchmarkView ? "How often the matching engine ranks the expected suitable worker highly." : "Customer selection behavior relative to AI rankings."}
            />
            <div className="eval-stat-rows">
              {isBenchmarkView ? [
                ["Top-1 Benchmark Hit Rate", pct(s?.top_1_selection_rate)],
                ["Top-3 Benchmark Hit Rate", pct(s?.top_3_selection_rate)],
                ["Top-5 Benchmark Hit Rate", pct(s?.top_5_selection_rate)],
                ["No-Match Rate", pct(s?.no_match_rate)],
              ].map(([l, v]) => (
                <div className="eval-stat-row" key={l}><span>{l}</span><strong>{v}</strong></div>
              )) : [
                ["AI Recommendation Accepted (#1)", pct(s?.ai_recommendation_acceptance_rate)],
                ["Top-3 Selection Rate", pct(s?.top_3_selection_rate)],
                ["Top-5 Selection Rate", pct(s?.top_5_selection_rate)],
                ["Alternative Selection Rate", pct(s?.alternative_selection_rate)],
              ].map(([l, v]) => (
                <div className="eval-stat-row" key={l}><span>{l}</span><strong>{v}</strong></div>
              ))}
            </div>
            <p className="eval-lat-note">
              {isBenchmarkView
                ? "Benchmark ground truth is defined by explicit scenario design — not real customer choices."
                : "High AI acceptance rate indicates the ranking engine aligns with real customer preferences."}
            </p>
          </section>
        </div>

        <div className="eval-two-col">
          <section className="eval-section eval-panel">
            <SecHead eyebrow="SCORE ANALYSIS" title="Match Score Distribution" subtitle="Distribution of AI scores for top-recommended candidates." />
            {buckets ? (
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={buckets} margin={{ left: 0, right: 12 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e6e2da" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v, _n, p) => [v + " eval (" + p.payload.pct + "%)", "Count"]} />
                  <Bar dataKey="count" radius={[5, 5, 0, 0]}>
                    {buckets.map((_, i) => <Cell key={i} fill={BUCKET_COLORS[i] || "#94a3b8"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="eval-no-data"><p>Not enough data yet.</p></div>}
          </section>
          <section className="eval-section eval-panel">
            <SecHead eyebrow="RANKING ENGINE" title="Top-K Average Scores" subtitle={"Average score by rank position \u2014 demonstrates differentiation between candidates."} />
            {topKSc.length > 0 ? (
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={topKSc} margin={{ left: 0, right: 12 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e6e2da" />
                  <XAxis dataKey="rank" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => [v + " / 100", "Avg Score"]} />
                  <Bar dataKey="score" radius={[5, 5, 0, 0]} fill="#e76f51" label={{ position: "top", fontSize: 11, fontWeight: 700, fill: "#c75439" }} />
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="eval-no-data"><p>Submit service requests or run the benchmark to populate this chart.</p></div>}
          </section>
        </div>

        {!isBenchmarkView && (
          <section className="eval-section eval-panel">
            <SecHead eyebrow="WORKER ALLOCATION" title="Selection Distribution" subtitle="Assignment statistics from confirmed customer selections." />
            <div className="eval-alloc-grid">
              <div className="eval-alloc-card"><Users size={22} /><strong>{uniqW}</strong><span>Unique workers selected</span></div>
              <div className="eval-alloc-card"><Activity size={22} /><strong>{totalSel}</strong><span>Total confirmed selections</span></div>
              <div className="eval-alloc-card"><TrendingUp size={22} /><strong>{uniqW > 0 ? (totalSel / uniqW).toFixed(1) : "\u2014"}</strong><span>Avg assignments per worker</span></div>
            </div>
            <div className="eval-fairness-note"><AlertTriangle size={14} />Fairness analysis requires completed-job allocation data across a larger sample.</div>
          </section>
        )}

        <section className="eval-section eval-panel">
          <SecHead eyebrow="RAW TELEMETRY" title="Evaluation Records" subtitle={pageRecs.length + " of " + sorted.length + " records \u2014 " + (isAllView ? "live & benchmark" : isBenchmarkView ? "benchmark" : "live")} />
          <div className="eval-table-wrap">
            <table className="eval-table">
              <thead><tr>
                <th>Source</th><th>ID</th><th>Timestamp</th><th>Latency</th><th>Workers</th>
                <th>Eligible</th><th>Ranked</th><th>Rec. Score</th>
                <th>{isAllView ? "Rank" : isBenchmarkView ? "GT Rank" : "Sel. Rank"}</th>
                <th>{isAllView ? "Result" : isBenchmarkView ? "GT Match" : "AI Pick"}</th><th>Filter %</th>
              </tr></thead>
              <tbody>
                {pageRecs.map((r) => (
                  <tr key={r.id}>
                    <td><span className={"eval-source-badge " + (r.source === "benchmark" ? "bench" : "live")}>{r.source === "benchmark" ? "BM" : "Live"}</span></td>
                    <td><span className="eval-td-id">#{r.request_id ?? r.id}</span></td>
                    <td className="eval-td-ts">{new Date(r.created_at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
                    <td><span className={"eval-latency-badge " + (r.matching_latency_ms > 100 ? "slow" : r.matching_latency_ms > 50 ? "med" : "fast")}>{fms(r.matching_latency_ms)}</span></td>
                    <td>{r.total_workers_considered}</td>
                    <td>{r.eligible_workers_count}</td>
                    <td>{r.ranked_workers_count}</td>
                    <td>{r.recommended_worker_score ?? "\u2014"}</td>
                    <td>{r.selected_worker_rank != null ? <span className={"eval-rank-badge " + (r.selected_worker_rank <= 3 ? "rank-top" : "rank-other")}>#{r.selected_worker_rank}</span> : "\u2014"}</td>
                    <td>{r.source === "benchmark"
                      ? (r.selected_worker_rank === 1 ? <span className="eval-rec-yes">\u2713 Top-1</span> : r.selected_worker_rank != null ? <span className="eval-rec-no">\u2713 Top-{r.selected_worker_rank}</span> : "\u2014")
                      : (r.recommendation_selected === true ? <span className="eval-rec-yes">\u2713 Yes</span> : r.recommendation_selected === false ? <span className="eval-rec-no">\u2717 No</span> : "\u2014")}</td>
                    <td>{r.candidate_filter_rate != null ? (r.candidate_filter_rate * 100).toFixed(1) + "%" : "\u2014"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {tPages > 1 && (
            <div className="eval-pagination">
              <button type="button" className="ghost-button eval-page-btn" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}><ChevronLeft size={16} />Prev</button>
              <span className="eval-page-info">Page {page + 1} of {tPages}</span>
              <button type="button" className="ghost-button eval-page-btn" onClick={() => setPage((p) => Math.min(tPages - 1, p + 1))} disabled={page === tPages - 1}>Next<ChevronRight size={16} /></button>
            </div>
          )}
        </section>
      </>)}
    </div>
  );
}
