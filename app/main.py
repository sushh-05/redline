from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.attacks import run_attacks
from app.compare import attack_payload, changed_fields, changed_outcomes
from app.engine import Transaction, evaluate
from app.models import (
    AttackRunModel,
    EvaluateRequest,
    EvaluateResponse,
    PassRequest,
    PatchRequest,
    PatchResponse,
    PolicyModel,
    RunResponse,
    to_policy,
)
from app.policy_text import parse_policy_sentence

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


@app.post("/run", response_model=RunResponse)
def run_policy_attacks(policy: PolicyModel) -> RunResponse:
    results = run_attacks(to_policy(policy))
    return RunResponse(attacks=[AttackRunModel.model_validate(attack_payload(item)) for item in results])


@app.post("/pass", response_model=PolicyModel)
def pass_policy_sentence(request: PassRequest) -> PolicyModel:
    parsed = parse_policy_sentence(request.sentence)
    if parsed.daily_limit is None or parsed.approval_above is None:
        raise HTTPException(
            status_code=400,
            detail="sentence must include daily limit and approval above",
        )
    return PolicyModel(
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
