import { useEffect, useMemo, useState } from "react";

const blank = { daily_limit: "", approval_above: "", rolling_hour_limit: "" };
const presets = {
  Balanced: { daily_limit: "100", approval_above: "5", rolling_hour_limit: "25" },
  Strict: { daily_limit: "50", approval_above: "10", rolling_hour_limit: "10" },
  "No rolling limit": { daily_limit: "100", approval_above: "5", rolling_hour_limit: "" },
};

function policyFromForm(values) {
  if (!values.daily_limit || !values.approval_above) throw new Error("Enter both a daily limit and an approval threshold.");
  const numbers = Object.values(values).filter(Boolean).map(Number);
  if (numbers.some((value) => value < 0 || Number.isNaN(value))) throw new Error("Limits must be zero or greater.");
  return { daily_limit: Number(values.daily_limit).toFixed(2), approval_above: Number(values.approval_above).toFixed(2), rolling_hour_limit: values.rolling_hour_limit ? Number(values.rolling_hour_limit).toFixed(2) : null };
}
function money(value) { return value == null ? "—" : `$${Number(value).toFixed(2)}`; }
async function post(path, body) { const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || `Request failed (HTTP ${response.status}).`); return data; }

function NumericPolicyForm({ values, onChange, prefix, disabled }) {
  const update = (field) => (event) => onChange({ ...values, [field]: event.target.value });
  return <div className="limit-form">
    <label htmlFor={`${prefix}-daily`}>Daily spend limit<input id={`${prefix}-daily`} type="number" min="0" step="0.01" placeholder="$100" value={values.daily_limit} onChange={update("daily_limit")} disabled={disabled} /></label>
    <label htmlFor={`${prefix}-approval`}>Approval required above<input id={`${prefix}-approval`} type="number" min="0" step="0.01" placeholder="$5" value={values.approval_above} onChange={update("approval_above")} disabled={disabled} /></label>
    <label htmlFor={`${prefix}-rolling`}>Rolling hour limit <small>optional</small><input id={`${prefix}-rolling`} type="number" min="0" step="0.01" placeholder="$25" value={values.rolling_hour_limit} onChange={update("rolling_hour_limit")} disabled={disabled} /></label>
  </div>;
}

function AttackCard({ attack, expanded, onToggle }) {
  const kind = attack.outcome === "escaped" ? "escape" : attack.outcome;
  return <article className={`attack-card ${kind}`}>
    <button className="attack-toggle" onClick={onToggle} aria-expanded={expanded}><span className="attack-top"><span className="attack-name">{attack.name}</span><span className={`badge ${kind}`}>{attack.outcome}</span></span><p>{attack.explanation}</p><p className="amount">{attack.decisions.length} <span>checks</span></p></button>
    {expanded && <div className="decision-timeline">{attack.decisions.map((decision, index) => <div className="decision-row" key={`${attack.name}-${index}`}><span className={`decision-dot ${decision.status}`} /> <span>Payment {index + 1}</span><b>{decision.status}</b>{decision.reasons.length > 0 && <small>{decision.reasons.join(", ")}</small>}</div>)}</div>}
  </article>;
}

function riskFor(attacks) {
  const escaped = attacks.filter((item) => item.outcome === "escaped").length;
  const escalated = attacks.filter((item) => item.outcome === "escalated").length;
  const blocked = attacks.filter((item) => item.outcome === "blocked").length;
  return { escaped, escalated, blocked, score: Math.max(0, Math.min(100, escaped * 35 + escalated * 15 - blocked * 5)) };
}

function recommendationsFor(attacks, policy) {
  const recommendations = [];
  if (attacks.some((item) => item.outcome === "escaped")) recommendations.push("Lower the approval threshold or add a tighter rolling-hour limit to stop small payments from bypassing review.");
  if (attacks.some((item) => item.name === "velocity" && item.outcome !== "blocked") && !policy.rolling_hour_limit) recommendations.push("Add a rolling-hour limit to control rapid repeated payments.");
  if (attacks.some((item) => item.name === "split-second" && item.outcome === "escaped")) recommendations.push("Consider cumulative approval rules so several small payments cannot avoid review together.");
  return recommendations;
}

export default function App() {
  const [policy, setPolicy] = useState(blank); const [patch, setPatch] = useState(blank); const [currentPolicy, setCurrentPolicy] = useState(null);
  const [attacks, setAttacks] = useState([]); const [diff, setDiff] = useState(null); const [busy, setBusy] = useState(""); const [error, setError] = useState({ policy: "", patch: "" });
  const [dark, setDark] = useState(() => localStorage.getItem("redline-theme") === "dark"); const [filter, setFilter] = useState("all"); const [expanded, setExpanded] = useState(null);
  const [history, setHistory] = useState(() => JSON.parse(localStorage.getItem("redline-history") || "[]"));
  useEffect(() => { document.body.classList.toggle("dark", dark); localStorage.setItem("redline-theme", dark ? "dark" : "light"); }, [dark]);
  useEffect(() => { localStorage.setItem("redline-history", JSON.stringify(history.slice(0, 10))); }, [history]);
  const risk = useMemo(() => riskFor(attacks), [attacks]); const filteredAttacks = attacks.filter((item) => filter === "all" || item.outcome === filter || (filter === "escape" && item.outcome === "escaped"));
  const recommendations = useMemo(() => currentPolicy ? recommendationsFor(attacks, currentPolicy) : [], [attacks, currentPolicy]);

  function applyPreset(name) { setPolicy(presets[name]); setError({ ...error, policy: "" }); }
  function exportReport() { const report = { exported_at: new Date().toISOString(), policy: currentPolicy, risk, attacks, diff }; const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "redline-report.json"; link.click(); URL.revokeObjectURL(link.href); }
  async function runAttacks() { setError({ ...error, policy: "" }); setBusy("run"); try { const next = policyFromForm(policy); const result = await post("/run", next); setCurrentPolicy(next); setAttacks(result.attacks); setExpanded(null); setHistory((items) => [{ at: new Date().toISOString(), policy: next, risk: riskFor(result.attacks) }, ...items].slice(0, 10)); } catch (err) { setError({ ...error, policy: err.message }); } finally { setBusy(""); } }
  async function applyPatch() { setError({ ...error, patch: "" }); setBusy("patch"); try { if (!currentPolicy) throw new Error("Run the current policy first, then enter a patch."); const next = policyFromForm(patch); const result = await post("/patch", { old_policy: currentPolicy, new_policy: next }); setDiff(result); setCurrentPolicy(next); const rerun = await post("/run", next); setAttacks(rerun.attacks); } catch (err) { setError({ ...error, patch: err.message }); } finally { setBusy(""); } }

  return <div className="app-shell"><header className="topbar"><a className="brand" href="/" aria-label="Redline home"><span className="brand-mark">R</span><span>REDLINE</span></a><div className="header-actions"><span className="header-note"><span className="status-dot" /> deterministic policy testing</span><button className="theme-toggle" onClick={() => setDark(!dark)}>{dark ? "☀ Light mode" : "☾ Dark mode"}</button></div></header>
    <main className="shell"><section className="intro"><div><p className="eyebrow">Policy attack simulator</p><h1>Find the line<br /><em>before</em> the spend.</h1></div><p className="intro-copy">Pressure-test an agent’s spending policy with repeatable attacks. See exactly what escapes, escalates, or gets stopped.</p></section>
      <section className="workspace"><div className="panel"><div className="panel-heading"><div><span className="step">01</span><h2>Set Your Policy</h2></div><span className="live-label">POLICY INPUT</span></div><p className="helper">Enter limits as numbers. The rolling-hour limit is optional.</p><div className="preset-row"><span>Preset</span>{Object.keys(presets).map((name) => <button key={name} onClick={() => applyPreset(name)}>{name}</button>)}</div><NumericPolicyForm values={policy} onChange={setPolicy} prefix="policy" disabled={busy === "run"} /><div className="panel-footer"><span className="hint">No policy words required</span><button className="button primary" onClick={runAttacks} disabled={busy === "run"}>{busy === "run" ? "Running…" : "Run attacks ↗"}</button></div><p className="error">{error.policy}</p></div>
        <div className="results-column"><div className="results-heading"><div><p className="eyebrow">Attack surface</p><h2>What got through?</h2></div><span>{attacks.length ? `${attacks.length} attacks · just now` : "Run attacks to see results"}</span></div>{attacks.length > 0 && <div className="result-toolbar"><div className="filter-row">{["all", "escape", "escalated", "blocked", "safe"].map((item) => <button className={filter === item ? "active" : ""} key={item} onClick={() => setFilter(item)}>{item}</button>)}</div><button className="export-button" onClick={exportReport}>Export JSON ↓</button></div>}<div className="attack-grid">{filteredAttacks.map((attack) => <AttackCard key={attack.name} attack={attack} expanded={expanded === attack.name} onToggle={() => setExpanded(expanded === attack.name ? null : attack.name)} />)}</div></div></section>
      {attacks.length > 0 && <section className="insight-grid"><div className="insight-card"><p className="eyebrow">Policy health</p><div className="risk-score"><strong>{risk.score}</strong><span>/ 100 risk</span></div><div className="risk-breakdown"><span className="red-text">{risk.escaped} escaped</span><span className="amber-text">{risk.escalated} escalated</span><span className="green-text">{risk.blocked} blocked</span></div></div><div className="insight-card"><p className="eyebrow">Recommendations</p>{recommendations.length ? <ul>{recommendations.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted-copy">No immediate recommendations. All tested attacks are contained.</p>}</div></section>}
      <section className="panel patch-panel"><div className="panel-heading"><div><span className="step">02</span><h2>Set Your Patch</h2></div><span className="live-label">COMPARE CHANGES</span></div><p className="helper">Enter new numbers to compare a revised policy with the last run.</p><div className="patch-row"><NumericPolicyForm values={patch} onChange={setPatch} prefix="patch" disabled={busy === "patch"} /><button className="button secondary" onClick={applyPatch} disabled={busy === "patch"}>{busy === "patch" ? "Applying…" : "Apply patch ↗"}</button></div><p className="error">{error.patch}</p>{diff ? <div className="diff-area"><span className="diff-icon">+</span><div className="diff-content"><strong>{diff.changed_fields.length} policy fields changed · {diff.outcome_changes.length} attacks changed</strong><div className="diff-list">{diff.changed_fields.map((field) => <span className="diff-chip" key={field.field}><b>{field.field.replaceAll("_", " ")}</b> <del>{money(field.old)}</del> → <ins>{money(field.new)}</ins></span>)}{diff.outcome_changes.map((change) => <span className="diff-chip" key={change.name}><b>{change.name}</b> <del>{change.old}</del> → <ins>{change.new}</ins></span>)}</div></div></div> : <div className="diff-area empty"><span className="diff-icon">+</span><div><strong>No patch applied yet</strong><p>Your policy difference and changed attacks will appear here.</p></div></div>}</section>
      {history.length > 0 && <section className="panel history-panel"><div className="panel-heading"><div><span className="step">03</span><h2>Run History</h2></div><button className="export-button" onClick={() => setHistory([])}>Clear history</button></div><div className="history-list">{history.map((run) => <div className="history-row" key={run.at}><span>{new Date(run.at).toLocaleString()}</span><span>{money(run.policy.daily_limit)} daily · {money(run.policy.approval_above)} approval</span><b>{run.risk.score} risk</b></div>)}</div></section>}
    </main><footer><span>REDLINE / POLICY LAB</span><span>Built for safer autonomous spending</span></footer></div>;
}
