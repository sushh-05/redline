from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer, field_validator, model_validator

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
    allowed_recipients: list[str] | None = None
    allowed_start_hour: int | None = Field(default=None, ge=0, le=23)
    allowed_end_hour: int | None = Field(default=None, ge=0, le=23)
    per_recipient_daily_limit: Money | None = None

    @model_validator(mode="after")
    def _hours_must_form_a_window(self) -> "PolicyModel":
        if (self.allowed_start_hour is None) != (self.allowed_end_hour is None):
            raise ValueError("allowed start and end hours must be provided together")
        if self.allowed_start_hour is not None and self.allowed_end_hour is not None:
            if self.allowed_start_hour >= self.allowed_end_hour:
                raise ValueError("allowed start hour must be before end hour")
        return self

    @field_validator("daily_limit", "approval_above", "rolling_hour_limit", "per_recipient_daily_limit")
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


class GuardRequest(BaseModel):
    policy: PolicyModel
    transaction: TransactionModel
    history: list[TransactionModel] = Field(default_factory=list)


class GuardResponse(BaseModel):
    status: Status
    approved: bool
    requires_confirmation: bool
    reasons: list[str]
    message: str
    decision_source: str


class DecisionModel(BaseModel):
    status: Status
    reasons: list[str]


class PaymentResultModel(BaseModel):
    amount: Money
    time: datetime
    status: Status
    reasons: list[str]


class AttackRunModel(BaseModel):
    name: str
    outcome: Outcome
    explanation: str
    decisions: list[DecisionModel]
    payments: list[PaymentResultModel] = Field(default_factory=list)


class RunResponse(BaseModel):
    attacks: list[AttackRunModel]


class CustomAttackRequest(BaseModel):
    policy: PolicyModel
    name: str = Field(min_length=1, max_length=60)
    amount: Money
    count: int = Field(ge=1, le=100)
    interval_minutes: int = Field(ge=0, le=1440)


class SimulationRequest(BaseModel):
    policy: PolicyModel
    iterations: int = Field(default=100, ge=1, le=1000)
    seed: int = Field(default=42, ge=0)


class AdaptiveAttackRequest(BaseModel):
    policy: PolicyModel
    name: str = Field(default="adaptive attacker", min_length=1, max_length=60)
    starting_amount: Money = Field(default="1.00")
    steps: int = Field(default=12, ge=1, le=100)
    interval_minutes: int = Field(default=5, ge=0, le=1440)


class MultiAgentRequest(BaseModel):
    policy: PolicyModel
    agents: int = Field(default=3, ge=1, le=20)
    payments_per_agent: int = Field(default=5, ge=1, le=50)
    amount: Money = Field(default="2.00")
    interval_minutes: int = Field(default=5, ge=0, le=1440)


class AIAssistRequest(BaseModel):
    policy: PolicyModel
    attacks: list[AttackRunModel] = Field(default_factory=list)
    question: str = Field(default="Explain the current attack results and suggest the safest next patch.", min_length=1, max_length=2000)


class PassRequest(BaseModel):
    sentence: str = Field(min_length=1)


class PassPolicyResponse(BaseModel):
    daily_limit: Money
    approval_above: Money
    rolling_hour_limit: Money | None = None


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
        allowed_recipients=(frozenset(model.allowed_recipients) if model.allowed_recipients else None),
        allowed_start_hour=model.allowed_start_hour,
        allowed_end_hour=model.allowed_end_hour,
        per_recipient_daily_limit=model.per_recipient_daily_limit,
    )
