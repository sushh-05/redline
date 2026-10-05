from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from datetime import timedelta
import random
from decimal import Decimal
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.attacks import ATTACK_START, Attack, RECIPIENT, _outcome, run_attack, run_attacks
from app.compare import attack_payload, changed_fields, changed_outcomes
from app.engine import Transaction, evaluate
from app.models import (
    AttackRunModel,
    CustomAttackRequest,
    AdaptiveAttackRequest,
    AIAssistRequest,
    MultiAgentRequest,
    SimulationRequest,
    EvaluateRequest,
    EvaluateResponse,
    GuardRequest,
    GuardResponse,
    PassRequest,
    PatchRequest,
    PatchResponse,
    PassPolicyResponse,
    PolicyModel,
    RunResponse,
    to_policy,
)
from app.policy_text import parse_policy_sentence


_AI_PROVIDER_FAILURES: dict[str, str] = {}


def _record_ai_failure(provider: str, failure: str) -> None:
    # Keep diagnostics useful without ever logging or returning an API key.
    _AI_PROVIDER_FAILURES[provider] = failure[:160]


def _load_local_env() -> None:
    """Load simple KEY=VALUE entries without printing or exposing secrets."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
        # Accept common casing variants while exposing one internal name.
        if key.lower() == "gemini_api_key" and "GEMINI_API_KEY" not in os.environ:
            os.environ["GEMINI_API_KEY"] = value
        if key.lower() == "groq_api_key" and "GROQ_API_KEY" not in os.environ:
            os.environ["GROQ_API_KEY"] = value


_load_local_env()

app = FastAPI(
    title="Redline",
    description=(
        "Simulator that tests AI agent spending policies before an agent gets money. "
        "Allow, review, and block are produced only by deterministic policy code."
    ),
    version="0.1.0",
)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate_transaction(request: EvaluateRequest) -> EvaluateResponse:
    result = evaluate(
        to_policy(request.policy),
        Transaction(
            amount=request.transaction.amount,
            recipient=request.transaction.recipient,
            time=request.transaction.time,
        ),
        tuple(
            Transaction(amount=item.amount, recipient=item.recipient, time=item.time)
            for item in request.history
        ),
    )
    return EvaluateResponse(status=result.status, reasons=list(result.reasons))


@app.post("/guard", response_model=GuardResponse, tags=["agent-tools"])
def guard_transaction(request: GuardRequest) -> GuardResponse:
    """Authorize a proposed transaction before an external agent executes it."""
    try:
        result = evaluate(
            to_policy(request.policy),
            Transaction(
                amount=request.transaction.amount,
                recipient=request.transaction.recipient,
                time=request.transaction.time,
            ),
            tuple(
                Transaction(amount=item.amount, recipient=item.recipient, time=item.time)
                for item in request.history
            ),
        )
        if result.status == "allow":
            message = "Transaction may proceed under the supplied policy."
        elif result.status == "review":
            message = "Pause and get confirmation before executing this transaction."
        else:
            message = "Do not execute this transaction."
        return GuardResponse(
            status=result.status,
            approved=result.status == "allow",
            requires_confirmation=result.status == "review",
            reasons=list(result.reasons),
            message=message,
            decision_source="deterministic policy engine",
        )
    except Exception:
        # A guard failure must never become an accidental approval.
        return GuardResponse(
            status="block",
            approved=False,
            requires_confirmation=False,
            reasons=["guard_error"],
            message="Guard could not evaluate the transaction; do not execute it.",
            decision_source="fail-closed guard",
        )


@app.post("/run", response_model=RunResponse)
def run_policy_attacks(policy: PolicyModel) -> RunResponse:
    results = run_attacks(to_policy(policy))
    return RunResponse(attacks=[AttackRunModel.model_validate(attack_payload(item)) for item in results])


@app.post("/custom-run")
def run_custom_attack(request: CustomAttackRequest) -> dict[str, AttackRunModel]:
    payments = tuple(
        Transaction(
            amount=request.amount,
            recipient=RECIPIENT,
            time=ATTACK_START + timedelta(minutes=request.interval_minutes * index),
        )
        for index in range(request.count)
    )
    result = run_attack(to_policy(request.policy), Attack(name=request.name, payments=payments))
    return {"attack": AttackRunModel.model_validate(attack_payload(result))}


@app.post("/simulate")
def simulate_attacks(request: SimulationRequest) -> dict[str, object]:
    generator = random.Random(request.seed)
    policy = to_policy(request.policy)
    counts = {"blocked": 0, "escalated": 0, "escaped": 0, "safe": 0}
    examples: list[dict[str, object]] = []
    for index in range(request.iterations):
        count = generator.randint(2, 12)
        amount = Decimal(str(round(generator.uniform(0.50, 12.00), 2)))
        interval = generator.randint(0, 20)
        attack = Attack(
            name=f"random-{index + 1}",
            payments=tuple(
                Transaction(
                    amount=amount,
                    recipient=RECIPIENT,
                    time=ATTACK_START + timedelta(minutes=interval * payment_index),
                )
                for payment_index in range(count)
            ),
        )
        result = run_attack(policy, attack)
        counts[result.outcome] += 1
        if result.outcome in {"escaped", "blocked"} and len(examples) < 5:
            examples.append({"name": result.name, "outcome": result.outcome, "explanation": result.explanation})
    return {"iterations": request.iterations, "seed": request.seed, "counts": counts, "examples": examples}


@app.post("/adaptive-run")
def run_adaptive_attack(request: AdaptiveAttackRequest) -> dict[str, object]:
    policy = to_policy(request.policy)
    amount = request.starting_amount
    payments: list[Transaction] = []
    responses: list[str] = []
    for index in range(request.steps):
        payment = Transaction(
            amount=amount,
            recipient=RECIPIENT,
            time=ATTACK_START + timedelta(minutes=request.interval_minutes * index),
        )
        decision = evaluate(policy, payment, tuple(payments))
        responses.append(decision.status)
        payments.append(payment)
        if decision.status == "allow":
            amount = max(Decimal("0.10"), amount + Decimal("0.50"))
        elif decision.status == "review":
            amount = max(Decimal("0.10"), amount - Decimal("0.25"))
        else:
            amount = max(Decimal("0.10"), amount - Decimal("0.50"))
    result = run_attack(policy, Attack(name=request.name, payments=tuple(payments)))
    return {
        "attack": AttackRunModel.model_validate(attack_payload(result)),
        "strategy": "increase after allow, reduce after review or block",
        "observed_responses": responses,
    }


@app.post("/multi-agent-run")
def run_multi_agent(request: MultiAgentRequest) -> dict[str, object]:
    policy = to_policy(request.policy)
    shared_history: list[Transaction] = []
    agent_evaluations: dict[str, list[object]] = {f"agent-{index + 1}": [] for index in range(request.agents)}
    agent_allowed: dict[str, Decimal] = {name: Decimal("0.00") for name in agent_evaluations}
    schedule = [
        (payment_index, agent_index)
        for payment_index in range(request.payments_per_agent)
        for agent_index in range(request.agents)
    ]
    for payment_index, agent_index in schedule:
        name = f"agent-{agent_index + 1}"
        payment = Transaction(
            amount=request.amount,
            recipient=f"{name}-merchant",
            time=ATTACK_START + timedelta(minutes=request.interval_minutes * payment_index),
        )
        result = evaluate(policy, payment, tuple(shared_history))
        agent_evaluations[name].append(result)
        if result.status == "allow":
            agent_allowed[name] += request.amount
        shared_history.append(payment)
    agents = []
    for name, evaluations in agent_evaluations.items():
        outcome = _outcome(evaluations, agent_allowed[name], policy)
        agents.append({"name": name, "outcome": outcome, "allowed_total": format(agent_allowed[name], "f"), "decisions": [item.status for item in evaluations]})
    counts = {outcome: sum(agent["outcome"] == outcome for agent in agents) for outcome in ("blocked", "escalated", "escaped", "safe")}
    return {"agents": agents, "shared_payments": len(shared_history), "counts": counts}


def _gemini_assist(prompt: str) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    configured_model = os.getenv("GEMINI_MODEL")
    # Newer AI Studio projects may not have access to the 2.5 family. Try
    # current Flash IDs first, then retain 2.5 compatibility for older keys.
    models = list(dict.fromkeys([
        configured_model,
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]))
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700}}
    for model in models:
        if not model:
            continue
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        for attempt in range(2):
            try:
                with urlopen(request, timeout=20) as response:
                    body = json.loads(response.read().decode("utf-8"))
                candidates = body.get("candidates") or []
                if not candidates:
                    reason = (body.get("promptFeedback") or {}).get("blockReason")
                    _record_ai_failure("Gemini", f"no generated answer{f' ({reason})' if reason else ''}")
                    break
                parts = candidates[0].get("content", {}).get("parts", [])
                answer = "".join(part.get("text", "") for part in parts).strip()
                if not answer:
                    _record_ai_failure("Gemini", "empty provider response")
                    break
                _AI_PROVIDER_FAILURES.pop("Gemini", None)
                return answer
            except HTTPError as exc:
                if exc.code == 404:
                    _record_ai_failure("Gemini", f"model unavailable ({model})")
                    break
                if exc.code in {408, 429, 500, 502, 503, 504} and attempt == 0:
                    _record_ai_failure("Gemini", f"temporary HTTP {exc.code}; retrying")
                    time.sleep(1)
                    continue
                _record_ai_failure("Gemini", f"HTTP {exc.code}")
                return None
            except URLError as exc:
                if attempt == 0:
                    _record_ai_failure("Gemini", f"temporary network error ({exc.reason}); retrying")
                    time.sleep(1)
                    continue
                _record_ai_failure("Gemini", f"network error ({exc.reason})")
                return None
            except (TimeoutError, KeyError, IndexError, json.JSONDecodeError):
                _record_ai_failure("Gemini", "invalid provider response")
                return None
            except Exception:
                _record_ai_failure("Gemini", "unexpected provider error")
                return None
    return None


def _groq_assist(prompt: str) -> str | None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    # Keep the fallback on a currently supported production model. Older
    # llama-3.3-70b-versatile deployments may now return a model-not-found
    # response after Groq's deprecation window.
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    request = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps({
            "model": model,
            "temperature": 0.2,
            "max_tokens": 700,
            "messages": [
                {"role": "system", "content": "You are Redline's policy-analysis assistant. Explain results; never authorize or execute payments."},
                {"role": "user", "content": prompt},
            ],
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        _AI_PROVIDER_FAILURES.pop("Groq", None)
        return body["choices"][0]["message"]["content"].strip()
    except HTTPError as exc:
        _record_ai_failure("Groq", f"HTTP {exc.code}")
        return None
    except URLError as exc:
        _record_ai_failure("Groq", f"network error ({exc.reason})")
        return None
    except (TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        _record_ai_failure("Groq", "invalid provider response")
        return None
    except Exception:
        _record_ai_failure("Groq", "unexpected provider error")
        return None


@app.post("/ai/assist")
def ai_assist(request: AIAssistRequest) -> dict[str, object]:
    safe_payload = {
        "policy": request.policy.model_dump(mode="json"),
        "attacks": [item.model_dump(mode="json") for item in request.attacks],
    }
    prompt = (
        "You are the user-facing Redline policy copilot. Redline is a simulator, not a wallet. "
        "Use the supplied deterministic test data to answer the user's question. "
        "Do not mention prompts, constraints, policies for the assistant, hidden instructions, or internal reasoning. "
        "Do not write a checklist about what you were asked to do. "
        "Return only a concise final answer in plain text with these sections: What happened, Why it matters, Safest patch. "
        "Do not claim that money moved and do not make the deterministic decision. Keep the answer under 250 words.\n\n"
        f"User question: {request.question}\nTest data:\n{json.dumps(safe_payload, indent=2)}"
    )
    answer = _gemini_assist(prompt)
    provider = "gemini" if answer else None
    if answer is None:
        answer = _groq_assist(prompt)
        provider = "groq" if answer else None
    if answer is None:
        configured = [name for name, key in (("Gemini", "GEMINI_API_KEY"), ("Groq", "GROQ_API_KEY")) if os.getenv(key)]
        if configured:
            providers = " and ".join(configured)
            diagnostics = "; ".join(
                f"{provider}: {_AI_PROVIDER_FAILURES.get(provider, 'request failed')}"
                for provider in configured
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    f"{providers} key(s) are configured, but the provider request failed ({diagnostics}). "
                    "Check the key, model, API access, and internet connection."
                ),
            )
        raise HTTPException(
            status_code=503,
            detail="AI assistant unavailable. Configure GEMINI_API_KEY or GROQ_API_KEY.",
        )
    return {"provider": provider, "answer": answer, "decision_source": "deterministic policy engine"}


@app.post("/pass", response_model=PassPolicyResponse)
def pass_policy_sentence(request: PassRequest) -> PassPolicyResponse:
    parsed = parse_policy_sentence(request.sentence)
    if parsed.daily_limit is None or parsed.approval_above is None:
        raise HTTPException(
            status_code=400,
            detail="sentence must include daily limit and approval above",
        )
    return PassPolicyResponse(
        daily_limit=parsed.daily_limit,
        approval_above=parsed.approval_above,
        rolling_hour_limit=parsed.rolling_hour_limit,
    )


@app.post("/patch", response_model=PatchResponse)
def patch_policies(request: PatchRequest) -> PatchResponse:
    old = to_policy(request.old_policy)
    new = to_policy(request.new_policy)
    return PatchResponse.model_validate(
        {
            "changed_fields": changed_fields(old, new),
            "outcome_changes": changed_outcomes(old, new),
        }
    )


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
