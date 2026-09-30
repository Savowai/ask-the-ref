"""Strict provider contracts and transport-independent public answer objects."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuestionPlan(StrictModel):
    disposition: Literal["rules", "off_topic", "clarification", "historical"]
    competition: Literal["generic", "premier_league", "uefa", "fifa", "other"]
    scenario: bool
    queries: list[str] = Field(min_length=1, max_length=6)


class Support(StrictModel):
    evidence_id: str
    quote: str = Field(min_length=15, max_length=2000)


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    supports: list[Support] = Field(min_length=1, max_length=4)


class AnswerSection(StrictModel):
    label: Literal["Answer", "Decision", "Restart", "Disciplinary sanction", "Why"]
    claims: list[Claim] = Field(min_length=1, max_length=4)


class DraftAnswer(StrictModel):
    status: Literal["answered", "judgment", "insufficient_evidence", "clarification"]
    sections: list[AnswerSection] = Field(max_length=4)


class ClaimCheck(StrictModel):
    claim_id: str
    supported: bool


class AnswerAudit(StrictModel):
    claims: list[ClaimCheck]
    answers_question: bool
    assumptions_supported: bool
    judgment_flag_correct: bool


SCENARIO_LABELS = ["Decision", "Restart", "Disciplinary sanction", "Why"]
MESSAGES = {
    "off_topic": "I can help with the current rules of association football. Please ask a football rules question.",
    "historical": "This app uses only the rules currently in force. Please ask about the current rules.",
    "clarification": "Please add the details needed to decide the situation, such as who touched the ball, where it happened, and whether play had stopped.",
    "scope_unavailable": "Competition-specific rules are not loaded yet. I can currently explain the IFAB Laws; I cannot verify this competition’s regulations.",
    "insufficient_evidence": "I could not verify an answer from the current rule sections retrieved. Please add more detail or check the official rulebook.",
    "validation_failed": "I could not verify the answer against the retrieved rules, so I am withholding it.",
    "corpus_changed": "The rule corpus changed while this answer was being prepared. Please ask again.",
    "provider_error": "The answer service is unavailable. Please try again later.",
    "configuration_error": "Answer generation needs OPENAI_API_KEY in the project .env. Retrieval remains available with ref search.",
    "retrieval_error": "The current rules could not be retrieved. Check the database and local model setup.",
}
