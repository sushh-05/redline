const defaultPolicy = { daily_limit: "100.00", approval_above: "5.00", rolling_hour_limit: "25.00" };
let currentPolicy = defaultPolicy;

const $ = (id) => document.getElementById(id);
const money = (value) => value == null ? "—" : `$${Number(value).toFixed(2)}`;

function policyText(policy) {
  return `Set a daily limit of $${policy.daily_limit}, approval above $${policy.approval_above}, and a rolling hour limit of $${policy.rolling_hour_limit ?? "none"}.`;
}

function showAttacks(attacks) {
  $("attack-grid").innerHTML = attacks.map((attack) => {
    const kind = attack.outcome === "escaped" ? "escape" : attack.outcome;
    return `<article class="attack-card ${kind}"><div class="attack-top"><span class="attack-name">${attack.name}</span><span class="badge ${kind}">${attack.outcome}</span></div><p>${attack.explanation}</p><p class="amount">${attack.decisions.length} <span style="font:400 11px 'DM Sans';color:var(--muted)">checks</span></p></article>`;
  }).join("");
}

async function parsePolicy(sentence) {
  const response = await fetch("/pass", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sentence }) });
  if (!response.ok) { const body = await response.json(); throw new Error(body.detail || "Could not understand that policy."); }
  return response.json();
}

async function runPolicy(policy, meta = "") {
  const response = await fetch("/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(policy) });
  if (!response.ok) throw new Error("Attack run failed.");
  const body = await response.json(); showAttacks(body.attacks); $("run-meta").textContent = meta || `${body.attacks.length} attacks · just now`;
}

function renderDiff(diff) {
  const area = $("diff-area");
  const fields = diff.changed_fields || [];
  const outcomes = diff.outcome_changes || [];
  if (!fields.length && !outcomes.length) { area.className = "diff-area"; area.innerHTML = `<span class="diff-icon">✓</span><div><strong>No changes detected</strong><p>The patch produces the same policy and attack outcomes.</p></div>`; return; }
  const fieldMarkup = fields.map(f => `<span class="diff-chip"><b>${f.field.replaceAll("_", " ")}</b> &nbsp;<del>${money(f.old)}</del> → <ins>${money(f.new)}</ins></span>`).join("");
  const outcomeMarkup = outcomes.map(o => `<span class="diff-chip"><b>${o.name}</b> &nbsp;<del>${o.old}</del> → <ins>${o.new}</ins></span>`).join("");
  area.className = "diff-area"; area.innerHTML = `<span class="diff-icon">↗</span><div class="diff-content"><strong>${fields.length} policy field${fields.length === 1 ? "" : "s"} changed · ${outcomes.length} attack${outcomes.length === 1 ? "" : "s"} changed</strong><div class="diff-list">${fieldMarkup}${outcomeMarkup}</div></div>`;
}

$("run-button").addEventListener("click", async () => { $("policy-error").textContent = ""; try { const policy = await parsePolicy($("policy-input").value); currentPolicy = policy; await runPolicy(policy, "3 attacks · just now"); } catch (error) { $("policy-error").textContent = error.message; } });
$("patch-button").addEventListener("click", async () => { $("patch-error").textContent = ""; try { const newPolicy = await parsePolicy($("patch-input").value); const response = await fetch("/patch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ old_policy: currentPolicy, new_policy: newPolicy }) }); if (!response.ok) throw new Error("Could not compare that patch."); renderDiff(await response.json()); currentPolicy = newPolicy; await runPolicy(newPolicy, "3 attacks · patched just now"); } catch (error) { $("patch-error").textContent = error.message; } });

runPolicy(currentPolicy, "3 attacks · ready").catch(() => { $("run-meta").textContent = "Run unavailable"; });
