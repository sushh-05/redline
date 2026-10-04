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
