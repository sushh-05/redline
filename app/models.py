from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer, field_validator

from app.engine import Policy
from app.money import as_money

Status = Literal["allow", "review", "block"]
Outcome = Literal["blocked", "escalated", "escaped", "safe"]

Money = Annotated[
    Decimal,
    Field(max_digits=12, decimal_places=2),
    PlainSerializer(lambda value: format(as_money(value), "f"), return_type=str, when_used="json"),
]


class PolicyModel(BaseModel):
    daily_limit: Money
    approval_above: Money
    rolling_hour_limit: Money | None = None

    @field_validator("daily_limit", "approval_above", "rolling_hour_limit")
    @classmethod
    def _limits_must_be_non_negative(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        money = as_money(value)
        if money < 0:
            raise ValueError("policy limits must be non-negative")
        return money


class TransactionModel(BaseModel):
    amount: Money
    recipient: str = Field(min_length=1)
    time: datetime

    @field_validator("amount")
    @classmethod
    def _quantize_amount(cls, value: Decimal) -> Decimal:
        return as_money(value)


class EvaluateRequest(BaseModel):
    policy: PolicyModel
    transaction: TransactionModel
    history: list[TransactionModel] = Field(default_factory=list)


class EvaluateResponse(BaseModel):
    status: Status
    reasons: list[str]


class DecisionModel(BaseModel):
    status: Status
    reasons: list[str]


class AttackRunModel(BaseModel):
    name: str
    outcome: Outcome
    explanation: str
    decisions: list[DecisionModel]


class RunResponse(BaseModel):
    attacks: list[AttackRunModel]


class PassRequest(BaseModel):
    sentence: str = Field(min_length=1)


class PatchRequest(BaseModel):
    old_policy: PolicyModel
    new_policy: PolicyModel


class FieldChangeModel(BaseModel):
    field: str
    old: str | None
    new: str | None


class OutcomeChangeModel(BaseModel):
    name: str
    old: Outcome
    new: Outcome


class PatchResponse(BaseModel):
    changed_fields: list[FieldChangeModel]
    outcome_changes: list[OutcomeChangeModel]


def to_policy(model: PolicyModel) -> Policy:
    return Policy(
        daily_limit=model.daily_limit,
        approval_above=model.approval_above,
        rolling_hour_limit=model.rolling_hour_limit,
    )
