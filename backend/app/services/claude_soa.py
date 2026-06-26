"""Claude SoA parser (PRD §7.1 / §10.2).

The **only** place in the codebase that holds the SoA parser system prompt.
Versioned via PROMPT_VERSION so saved jobs (raw_output, parsed_visits in
SoaParseJob) can be replayed against later prompt revisions.

The Anthropic client is injected so tests can pass a mock — automated tests
never call the real API. Only the manual smoke step does.

Per PRD §10.2: parser output never flows into forecast math unconfirmed.
This module returns ``ParsedSoa`` (proposed); the route layer writes Visit
rows only after the user clicks Apply.
"""

from __future__ import annotations

import base64
from typing import Literal

from anthropic import Anthropic, AsyncAnthropic
from pydantic import BaseModel, Field

from app.config import get_settings

PROMPT_VERSION = "soa-parser-v1-2026-06-24"


def model_id() -> str:
    """The Claude model the parser runs on, read live from settings
    (``ANTHROPIC_MODEL_ID``; default ``claude-sonnet-4-6``). Reading it here —
    rather than baking a constant — lets the model be switched via env without
    a code change or redeploy. The worker stamps this onto SoaParseJob.model_id
    so each saved job records exactly which model produced it."""
    return get_settings().anthropic_model_id

# Keep the prompt frozen — any byte change invalidates the cache. Per the
# claude-api skill: render order is tools → system → messages, and the cache
# marker sits on the last system block.
SYSTEM_PROMPT = """You are a clinical trial Schedule of Activities (SoA) parser.

You are given a single protocol PDF. Extract the SoA — the list of trial visits
with their day offsets, windows, and types.

Return one row per visit. For each visit, infer:

1. **name** — short, human-readable label (e.g. "Screening", "Randomization",
   "Week 4 Follow-up", "Safety Follow-up").
2. **visit_type** — one of:
   - "screening": visits BEFORE randomization (day offset is negative)
   - "randomization": THE visit at which the patient is randomized (typically
     day 0). Exactly one visit per arm should be "randomization".
   - "follow_up": planned post-randomization visits at fixed day offsets
   - "other": end-of-study, early-termination, unscheduled, etc.
3. **target_day_offset** — signed days from randomization. Randomization = 0.
   Screening visits are negative (e.g. -14). Follow-ups are positive.
4. **window_days** — protocol-allowed ± days around the target. 0 if the
   protocol doesn't specify a window.
5. **confidence** — your self-assessed confidence in the row, 0.0..1.0.
   - 0.85–1.0: row is fully determined from clearly-labeled table cells
   - 0.6–0.84: row required minor inference (e.g. window inferred from text)
   - <0.6: row required significant inference, was ambiguous, or you're
     genuinely unsure — these will be flagged for human review
6. **flagged_reason** — when confidence < 0.85, a short (≤15-word) phrase
   explaining what's uncertain (e.g. "window not stated", "visit type ambiguous",
   "footnote modifies timing"). null when confidence ≥ 0.85.

**Rules:**
- Use the SoA table as the primary source. Footnotes and protocol prose can
  refine timing — fold them in.
- Multi-arm trials: parse the first arm you find unless the document is clearly
  organized around a single common SoA. Multi-arm support is a v1.5 feature.
- If a visit is conditional (e.g. "only if PK sub-study"), include it with
  visit_type="other" and confidence < 0.6.
- If the document has no SoA, return an empty visits list.

Be precise. Lower confidence is better than wrong data — the human reviewer
will see what you flagged."""


class ParsedVisit(BaseModel):
    """One extracted SoA row. Mirrors the Visit model's relevant fields plus
    confidence + flagged_reason."""

    name: str = Field(min_length=1, max_length=200)
    visit_type: Literal["screening", "randomization", "follow_up", "other"]
    target_day_offset: int
    window_days: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    flagged_reason: str | None = None


class ParsedSoa(BaseModel):
    """The parser's structured output. Stored in SoaParseJob.parsed_visits."""

    visits: list[ParsedVisit]


def _build_messages(pdf_bytes: bytes) -> list[dict]:
    """User-turn content: the PDF document plus a kickoff instruction.

    The instruction varies per call (timestamp not included — keep it stable
    too) but stays *after* the cached system prompt, so cache hits still land.
    """
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {
                    "type": "text",
                    "text": "Extract the Schedule of Activities from this protocol.",
                },
            ],
        }
    ]


async def parse_async(
    pdf_bytes: bytes,
    *,
    client: AsyncAnthropic,
) -> tuple[ParsedSoa, dict]:
    """Run the parser. Returns (parsed_soa, raw_response_dict).

    The raw_response_dict is stored on SoaParseJob.raw_output so a job can be
    replayed against a newer prompt or model later without re-billing.

    The system prompt is cached (5-min TTL by default) — same parser called
    many times in a session reads the cached prefix at ~0.1× cost.
    """
    # ``messages.parse`` runs prefill against the Pydantic schema. The system
    # prompt block carries the cache marker; user content (the PDF) goes in
    # `messages` and is not cached (varies per call).
    response = await client.messages.parse(
        model=model_id(),
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=_build_messages(pdf_bytes),
        output_format=ParsedSoa,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise ValueError(f"parser returned no structured output: stop_reason={response.stop_reason}")
    # The full response is preserved for replay/audit; serialize via the SDK
    # so future schema additions (new content blocks, etc.) round-trip cleanly.
    return parsed, response.to_dict()


def parse_sync(
    pdf_bytes: bytes,
    *,
    client: Anthropic,
) -> tuple[ParsedSoa, dict]:
    """Sync variant — used by tests that don't want an event loop."""
    response = client.messages.parse(
        model=model_id(),
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=_build_messages(pdf_bytes),
        output_format=ParsedSoa,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise ValueError(f"parser returned no structured output: stop_reason={response.stop_reason}")
    return parsed, response.to_dict()
