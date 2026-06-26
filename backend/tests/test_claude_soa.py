"""Claude SoA parser — exercised with a mock client (no real API call).

PRD §10.2 risk mitigation: the parser is tested without burning API credits
on every test run. Live API is only called in the manual smoke step.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from app.services import claude_soa
from app.services.claude_soa import ParsedSoa

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "claude_soa_response.json"


def _mock_anthropic_client(response_json: dict) -> MagicMock:
    """Build a sync Anthropic client whose messages.parse returns the fixture.

    Mimics the SDK's response surface: .parsed_output (the Pydantic instance),
    .to_dict() (the raw response), .stop_reason.
    """
    # The SDK's `.parsed_output` is built by validating the text block against
    # the supplied output_format. We mimic that here by parsing the JSON ourselves.
    text = response_json["content"][0]["text"]
    parsed = ParsedSoa.model_validate_json(text)

    mock_response = MagicMock()
    mock_response.parsed_output = parsed
    mock_response.stop_reason = response_json["stop_reason"]
    mock_response.to_dict = MagicMock(return_value=response_json)

    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response
    return mock_client


def test_parse_sync_returns_parsed_soa_and_raw() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    client = _mock_anthropic_client(fixture)

    parsed, raw = claude_soa.parse_sync(b"fake-pdf-bytes", client=client)

    assert isinstance(parsed, ParsedSoa)
    assert len(parsed.visits) == 4
    # Confidence bands are populated as the prompt instructs.
    names = [v.name for v in parsed.visits]
    assert "Screening" in names
    assert "Randomization" in names
    # The low-confidence row should carry a flagged_reason.
    pk = next(v for v in parsed.visits if v.name == "PK Sub-study Visit")
    assert pk.confidence < 0.6
    assert pk.flagged_reason is not None
    # Raw is the full response dict — proves replay would work later.
    assert raw["id"] == "msg_test_01"
    assert raw["model"] == "claude-opus-4-7"


def test_parse_sync_passes_system_with_cache_control() -> None:
    """The system prompt must be sent with cache_control so subsequent parses
    in the same session read the cached prefix (prompt-caching skill §Placement)."""
    fixture = json.loads(FIXTURE_PATH.read_text())
    client = _mock_anthropic_client(fixture)

    claude_soa.parse_sync(b"fake-pdf-bytes", client=client)

    call = client.messages.parse.call_args
    system = call.kwargs["system"]
    assert isinstance(system, list)
    assert len(system) == 1
    assert system[0]["text"] == claude_soa.SYSTEM_PROMPT
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_parse_sync_uses_configured_model_with_adaptive_thinking() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    client = _mock_anthropic_client(fixture)

    claude_soa.parse_sync(b"fake-pdf-bytes", client=client)

    kwargs = client.messages.parse.call_args.kwargs
    # The model is read from settings (default Sonnet 4.6), not hardcoded.
    assert kwargs["model"] == claude_soa.model_id() == "claude-sonnet-4-6"
    assert kwargs["thinking"] == {"type": "adaptive"}
    # PRD §10.2 mitigation hinges on Pydantic-validated output.
    assert kwargs["output_format"] is ParsedSoa


def test_parse_sync_sends_pdf_as_base64_document_block() -> None:
    """The user-turn message must carry the PDF as a base64 document block —
    that's what vision-capable Claude expects."""
    fixture = json.loads(FIXTURE_PATH.read_text())
    client = _mock_anthropic_client(fixture)

    claude_soa.parse_sync(b"hello-pdf", client=client)

    messages = client.messages.parse.call_args.kwargs["messages"]
    assert len(messages) == 1
    content = messages[0]["content"]
    doc_block = next(b for b in content if b["type"] == "document")
    assert doc_block["source"]["type"] == "base64"
    assert doc_block["source"]["media_type"] == "application/pdf"
    # Round-trip the base64 to confirm we encoded our bytes correctly.
    import base64

    assert base64.standard_b64decode(doc_block["source"]["data"]) == b"hello-pdf"


def test_prompt_version_is_set() -> None:
    """A stored job's prompt_version must be non-empty so replay against a
    later prompt revision is possible."""
    assert claude_soa.PROMPT_VERSION
    assert claude_soa.model_id() == "claude-sonnet-4-6"
