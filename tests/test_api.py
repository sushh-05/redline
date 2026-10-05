from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.policy_text import parse_policy_sentence

client = TestClient(app)

DEFAULT_POLICY = {
    "daily_limit": "100.00",
    "approval_above": "5.00",
    "rolling_hour_limit": None,
}


def test_run_returns_every_attack_with_outcome_decisions_and_explanation() -> None:
    response = client.post("/run", json=DEFAULT_POLICY)
    assert response.status_code == 200
    body = response.json()
    names = [item["name"] for item in body["attacks"]]
    assert names == ["split-second", "boundary", "velocity"]
    split, edge, speed = body["attacks"]
    assert split["outcome"] == "escaped"
    assert split["explanation"] == "4 payments of 4.99 avoided approval while moving 19.96."
    assert len(split["decisions"]) == 4
    assert all(item["status"] == "allow" for item in split["decisions"])
    assert edge["outcome"] == "escalated"
    assert edge["decisions"][-1] == {
        "status": "review",
        "reasons": ["amount_above_approval"],
    }
    assert speed["outcome"] == "escaped"
    assert len(speed["decisions"]) == 10


def test_custom_run_uses_the_same_deterministic_engine() -> None:
    response = client.post(
        "/custom-run",
        json={
            "policy": DEFAULT_POLICY,
            "name": "merchant burst",
            "amount": "2.50",
            "count": 5,
            "interval_minutes": 2,
        },
    )
    assert response.status_code == 200
    attack = response.json()["attack"]
    assert attack["name"] == "merchant burst"
    assert attack["outcome"] == "escaped"
    assert len(attack["decisions"]) == 5


def test_simulate_is_seeded_and_returns_outcome_counts() -> None:
    payload = {"policy": DEFAULT_POLICY, "iterations": 12, "seed": 7}
    first = client.post("/simulate", json=payload)
    second = client.post("/simulate", json=payload)
    assert first.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["iterations"] == 12
    assert sum(body["counts"].values()) == 12


def test_adaptive_run_returns_observed_responses_and_attack_details() -> None:
    response = client.post(
        "/adaptive-run",
        json={
            "policy": DEFAULT_POLICY,
            "starting_amount": "1.00",
            "steps": 8,
            "interval_minutes": 5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["observed_responses"]) == 8
    assert len(body["attack"]["payments"]) == 8
    assert "increase after allow" in body["strategy"]


def test_multi_agent_run_uses_a_shared_payment_history() -> None:
    response = client.post(
        "/multi-agent-run",
        json={
            "policy": {"daily_limit": "10", "approval_above": "25", "rolling_hour_limit": "10"},
            "agents": 3,
            "payments_per_agent": 4,
            "amount": "2.00",
            "interval_minutes": 5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["agents"]) == 3
    assert body["shared_payments"] == 12
    assert sum(body["counts"].values()) == 3


def test_policy_rejects_incomplete_or_reversed_allowed_hours() -> None:
    incomplete = client.post(
        "/run",
        json={**DEFAULT_POLICY, "allowed_start_hour": 9},
    )
    reversed_window = client.post(
        "/run",
        json={**DEFAULT_POLICY, "allowed_start_hour": 17, "allowed_end_hour": 9},
    )
    assert incomplete.status_code == 422
    assert reversed_window.status_code == 422


def test_ai_assist_reports_when_both_configured_providers_are_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    response = client.post(
        "/ai/assist",
        json={"policy": DEFAULT_POLICY, "attacks": [], "question": "Explain this policy."},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "AI assistant unavailable. Configure GEMINI_API_KEY or GROQ_API_KEY."


def test_guard_allows_a_transaction_before_an_agent_executes_it() -> None:
    response = client.post(
        "/guard",
        json={
            "policy": DEFAULT_POLICY,
            "transaction": {
                "amount": "2.00",
                "recipient": "merchant",
                "time": "2026-10-05T12:00:00Z",
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["approved"] is True
    assert response.json()["decision_source"] == "deterministic policy engine"


def test_guard_requires_confirmation_for_a_review() -> None:
    response = client.post(
        "/guard",
        json={
            "policy": DEFAULT_POLICY,
            "transaction": {
                "amount": "5.01",
                "recipient": "merchant",
                "time": "2026-10-05T12:00:00Z",
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "review"
    assert response.json()["requires_confirmation"] is True


def test_pass_reads_limits_from_a_sentence() -> None:
    response = client.post(
        "/pass",
        json={
            "sentence": (
                "Set a daily limit of 80, approval above 25, "
                "and a rolling hour limit of 10."
            )
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "daily_limit": "80.00",
        "approval_above": "25.00",
        "rolling_hour_limit": "10.00",
    }


def test_pass_leaves_rolling_hour_limit_optional() -> None:
    parsed = parse_policy_sentence("daily limit 100 approval above 5")
    assert parsed.daily_limit == Decimal("100.00")
    assert parsed.approval_above == Decimal("5.00")
    assert parsed.rolling_hour_limit is None
    response = client.post(
        "/pass",
        json={"sentence": "Daily limit $100. Approval above 5."},
    )
    assert response.status_code == 200
    assert response.json()["rolling_hour_limit"] is None


def test_pass_accepts_common_natural_policy_phrasing() -> None:
    response = client.post(
        "/pass",
        json={
            "sentence": (
                "Allow spending up to $100 per day, require approval for purchases over $5, "
                "and cap spending at $25 per hour."
            )
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "daily_limit": "100.00",
        "approval_above": "5.00",
        "rolling_hour_limit": "25.00",
    }


def test_pass_rejects_a_sentence_missing_required_limits() -> None:
    response = client.post("/pass", json={"sentence": "rolling hour limit 10"})
    assert response.status_code == 400


def test_patch_reports_changed_fields_and_attack_outcomes() -> None:
    response = client.post(
        "/patch",
        json={
            "old_policy": DEFAULT_POLICY,
            "new_policy": {
                "daily_limit": "100.00",
                "approval_above": "5.00",
                "rolling_hour_limit": "10.00",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["changed_fields"] == [
        {
            "field": "rolling_hour_limit",
            "old": None,
            "new": "10.00",
        }
    ]
    names = [item["name"] for item in body["outcome_changes"]]
    assert "split-second" in names
    split = next(item for item in body["outcome_changes"] if item["name"] == "split-second")
    assert split == {"name": "split-second", "old": "escaped", "new": "escalated"}
    assert all(item["old"] != item["new"] for item in body["outcome_changes"])


def test_patch_with_identical_policies_is_empty() -> None:
    response = client.post(
        "/patch",
        json={"old_policy": DEFAULT_POLICY, "new_policy": DEFAULT_POLICY},
    )
    assert response.status_code == 200
    assert response.json() == {"changed_fields": [], "outcome_changes": []}
