from datetime import date
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from anthropic.types import Usage
from pydantic import ValidationError

from app.ai.agenda import (
    ActionItem,
    AgendaItem,
    AgendaParseError,
    ParsedAgenda,
    parse_agenda,
)
from app.ai.pricing import cost_usd


def _make_tool_response(tool_input: dict, tool_id: str = "tool_1", in_tokens: int = 100, out_tokens: int = 50):
    block = MagicMock()
    block.type = "tool_use"
    block.name = "record_agenda"
    block.id = tool_id
    block.input = tool_input

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    response.usage = Usage(input_tokens=in_tokens, output_tokens=out_tokens)
    return response


def _make_text_response(text: str = "Hello", in_tokens: int = 40, out_tokens: int = 20):
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [block]
    response.usage = Usage(input_tokens=in_tokens, output_tokens=out_tokens)
    return response


def test_valid_tool_call():
    mock_client = MagicMock()
    valid_payload = {
        "title": "Sprint Planning",
        "starts_at": "2026-10-27T10:00:00+02:00",
        "duration_minutes": 60,
        "items": [
            {"topic": "Review backlog", "owner": "Alice", "minutes": 20},
            {"topic": "Task breakdown", "owner": "Bob", "minutes": 40},
        ],
        "action_items": [
            {"task": "Update Jira tickets", "owner": "Alice", "due": "2026-10-28"},
        ],
        "language": "en",
    }
    mock_client.messages.create.return_value = _make_tool_response(valid_payload, in_tokens=120, out_tokens=60)

    today = date(2026, 10, 27)
    tz = ZoneInfo("Europe/Kyiv")
    text = "Sprint Planning meeting tomorrow at 10:00. Alice will review backlog (20m)..."

    agenda, usage = parse_agenda(text, today, tz, client=mock_client)

    assert isinstance(agenda, ParsedAgenda)
    assert agenda.title == "Sprint Planning"
    assert agenda.starts_at == "2026-10-27T10:00:00+02:00"
    assert agenda.duration_minutes == 60
    assert len(agenda.items) == 2
    assert agenda.items[0].topic == "Review backlog"
    assert agenda.items[0].minutes == 20
    assert len(agenda.action_items) == 1
    assert agenda.action_items[0].task == "Update Jira tickets"
    assert agenda.action_items[0].due == date(2026, 10, 28)
    assert agenda.language == "en"
    assert usage.input_tokens == 120
    assert usage.output_tokens == 60

    mock_client.messages.create.assert_called_once()
    kwargs = mock_client.messages.create.call_args.kwargs
    assert "tool_choice" not in kwargs
    user_msg = kwargs["messages"][0]["content"]
    assert "2026-10-27" in user_msg
    assert "Tuesday" in user_msg
    assert "Europe/Kyiv" in user_msg
    assert "<pasted_text>" in user_msg
    assert text in user_msg


def test_nullable_fields_and_min_length_validation():
    # Nullable title, duration_minutes, starts_at, and item minutes
    item = AgendaItem(topic="Quick update", minutes=None)
    assert item.minutes is None

    action = ActionItem(task="Write docs", due=None)
    assert action.due is None

    agenda = ParsedAgenda(title=None, starts_at=None, duration_minutes=None, language="en")
    assert agenda.title is None
    assert agenda.starts_at is None
    assert agenda.duration_minutes is None

    # min_length=1 enforcement
    with pytest.raises(ValidationError):
        AgendaItem(topic="")
    with pytest.raises(ValidationError):
        ActionItem(task="")


def test_invalid_output_then_valid_on_retry():
    mock_client = MagicMock()
    # duration_minutes: 0 violates ge=1
    invalid_payload = {"title": "Retro", "duration_minutes": 0, "items": [], "action_items": [], "language": "en"}
    valid_payload = {"title": "Retro", "duration_minutes": 45, "items": [{"topic": "What went well", "minutes": 45}], "action_items": [], "language": "en"}

    resp1 = _make_tool_response(invalid_payload, tool_id="tool_1", in_tokens=100, out_tokens=30)
    resp2 = _make_tool_response(valid_payload, tool_id="tool_2", in_tokens=150, out_tokens=40)
    mock_client.messages.create.side_effect = [resp1, resp2]

    today = date(2026, 10, 27)
    tz = ZoneInfo("Europe/Kyiv")
    agenda, usage = parse_agenda("Team retro", today, tz, client=mock_client)

    assert isinstance(agenda, ParsedAgenda)
    assert agenda.title == "Retro"
    assert agenda.duration_minutes == 45
    assert usage.input_tokens == 250
    assert usage.output_tokens == 70
    assert mock_client.messages.create.call_count == 2
    retry_kwargs = mock_client.messages.create.call_args_list[1].kwargs
    tool_result = retry_kwargs["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["is_error"] is True


def test_no_tool_call_raises_agenda_parse_error():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_text_response("Just chatting")
    today = date(2026, 10, 27)
    tz = ZoneInfo("Europe/Kyiv")
    with pytest.raises(AgendaParseError, match="record_agenda"):
        parse_agenda("Random text", today, tz, client=mock_client)


def test_invalid_output_retry_fails_raises_agenda_parse_error():
    mock_client = MagicMock()
    invalid_payload = {"title": "Retro", "duration_minutes": 0, "items": [], "action_items": [], "language": "en"}
    resp1 = _make_tool_response(invalid_payload, tool_id="tool_1", in_tokens=100, out_tokens=30)
    resp2 = _make_tool_response(invalid_payload, tool_id="tool_2", in_tokens=150, out_tokens=40)
    mock_client.messages.create.side_effect = [resp1, resp2]

    today = date(2026, 10, 27)
    tz = ZoneInfo("Europe/Kyiv")
    with pytest.raises(AgendaParseError):
        parse_agenda("Team retro", today, tz, client=mock_client)


def test_no_tool_call_on_retry_raises_agenda_parse_error():
    mock_client = MagicMock()
    invalid_payload = {"title": "Retro", "duration_minutes": 0, "items": [], "action_items": [], "language": "en"}
    resp1 = _make_tool_response(invalid_payload, tool_id="tool_1", in_tokens=100, out_tokens=30)
    resp2 = _make_text_response("No tool call here", in_tokens=50, out_tokens=20)
    mock_client.messages.create.side_effect = [resp1, resp2]

    today = date(2026, 10, 27)
    tz = ZoneInfo("Europe/Kyiv")
    with pytest.raises(AgendaParseError, match="retry"):
        parse_agenda("Team retro", today, tz, client=mock_client)


def test_pricing_haiku_4_5():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = cost_usd("us.anthropic.claude-haiku-4-5-20251001-v1:0", usage)
    assert pytest.approx(cost, 0.0001) == 6.00


def test_pricing_unknown_model_returns_zero():
    usage = Usage(input_tokens=1_000, output_tokens=500)
    cost = cost_usd("unknown-model", usage)
    assert cost == 0.0
