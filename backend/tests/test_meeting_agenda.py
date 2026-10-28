"""Tests for meeting agenda persistence, validation and owner scoping."""

import uuid


async def test_put_agenda_success(client, meeting_payload):
    created = (await client.post("/api/v1/meetings", json=meeting_payload)).json()
    meeting_id = created["id"]

    agenda_payload = {
        "agenda": {
            "items": [
                {"topic": "Intro", "owner": "Alice", "minutes": 15},
                {"topic": "Roadmap", "owner": None, "minutes": 30},
            ],
            "action_items": [
                {"task": "Send deck", "owner": "Alice", "due": "2026-10-30"},
            ],
        },
        "ai_suggestion": {
            "suggested": {
                "title": "Planning",
                "items": [{"topic": "Intro", "owner": "Alice", "minutes": 15}],
            },
            "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "prompt_version": "agenda-v1",
        },
    }

    put_res = await client.put(f"/api/v1/meetings/{meeting_id}/agenda", json=agenda_payload)
    assert put_res.status_code == 200, put_res.text
    data = put_res.json()

    assert data["agenda"] is not None
    assert len(data["agenda"]["items"]) == 2
    assert data["agenda"]["items"][0]["topic"] == "Intro"
    assert data["agenda"]["items"][0]["minutes"] == 15
    assert data["agenda"]["items"][1]["owner"] is None
    assert len(data["agenda"]["action_items"]) == 1
    assert data["agenda"]["action_items"][0]["due"] == "2026-10-30"

    assert data["ai_suggestion"] is not None
    assert data["ai_suggestion"]["model"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert data["ai_suggestion"]["prompt_version"] == "agenda-v1"

    # Verify GET also returns the saved agenda
    get_res = await client.get(f"/api/v1/meetings/{meeting_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["agenda"] == data["agenda"]
    assert get_data["ai_suggestion"] == data["ai_suggestion"]


async def test_put_agenda_owner_scoping_is_404(client, other_client, meeting_payload):
    created = (await client.post("/api/v1/meetings", json=meeting_payload)).json()
    meeting_id = created["id"]

    agenda_payload = {
        "agenda": {"items": [{"topic": "Secret", "minutes": 10}], "action_items": []},
    }

    # Another signed-in user cannot update this meeting's agenda
    res = await other_client.put(f"/api/v1/meetings/{meeting_id}/agenda", json=agenda_payload)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"

    # Non-existent ID is also 404
    random_id = uuid.uuid4()
    res_missing = await client.put(f"/api/v1/meetings/{random_id}/agenda", json=agenda_payload)
    assert res_missing.status_code == 404
    assert res_missing.json()["error"]["code"] == "not_found"


async def test_put_agenda_validation_error(client, meeting_payload):
    created = (await client.post("/api/v1/meetings", json=meeting_payload)).json()
    meeting_id = created["id"]

    # minutes exceeds 480 limit
    invalid_payload = {
        "agenda": {
            "items": [{"topic": "Too long", "minutes": 500}],
            "action_items": [],
        }
    }
    res = await client.put(f"/api/v1/meetings/{meeting_id}/agenda", json=invalid_payload)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


async def test_put_agenda_nullable(client, meeting_payload):
    created = (await client.post("/api/v1/meetings", json=meeting_payload)).json()
    meeting_id = created["id"]

    res = await client.put(
        f"/api/v1/meetings/{meeting_id}/agenda",
        json={"agenda": None, "ai_suggestion": None},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["agenda"] is None
    assert data["ai_suggestion"] is None


async def test_new_meeting_has_no_agenda(client, meeting_payload):
    created = (await client.post("/api/v1/meetings", json=meeting_payload)).json()
    assert created["agenda"] is None
    assert created["ai_suggestion"] is None
