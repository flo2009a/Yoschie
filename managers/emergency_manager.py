"""
Notruf Manager
"""
from models.db import insert, update, get_by_id, find, load_all
from models.models import EmergencyCall, now


def create_call(
    location: str,
    description: str,
    call_type: str,
    priority: str = "medium",
    caller_id: str = None,
    anonymous: bool = False
) -> dict:
    call = EmergencyCall(
        caller_character_id=None if anonymous else caller_id,
        location=location,
        description=description,
        call_type=call_type,
        priority=priority,
        anonymous=anonymous
    )
    return insert("emergency", call.to_dict())


def update_call_status(call_id: str, status: str, responder_id: str = None) -> dict:
    updates = {"status": status}
    if status in ("accepted", "in_progress") and responder_id:
        call = get_by_id("emergency", call_id)
        assigned = call.get("assigned_to", [])
        if responder_id not in assigned:
            assigned.append(responder_id)
        updates["assigned_to"] = assigned
    if status == "closed":
        updates["closed_at"] = now()
    return update("emergency", call_id, updates)


def add_note_to_call(call_id: str, note: str) -> dict:
    call = get_by_id("emergency", call_id)
    notes = call.get("notes", [])
    notes.append(f"[{now()}] {note}")
    return update("emergency", call_id, {"notes": notes})


def mark_false_alarm(call_id: str, account_id: str) -> dict:
    # Kann falschen Notruf dem Account anhängen
    call = get_by_id("emergency", call_id)
    caller_id = call.get("caller_character_id")
    if caller_id:
        from managers.account_manager import add_moderation
        char = get_by_id("characters", caller_id)
        if char:
            add_moderation(
                account_id=char["account_id"],
                action="note",
                reason=f"Falscher Notruf: {call['description']} am {call['created_at']}",
                issued_by_id=account_id
            )
    return update("emergency", call_id, {"is_false_alarm": True})


def get_open_calls(call_type: str = None) -> list[dict]:
    calls = [c for c in load_all("emergency") if c["status"] != "closed"]
    if call_type and call_type != "all":
        calls = [c for c in calls if c["call_type"] in (call_type, "all")]
    return sorted(calls, key=lambda x: x["created_at"], reverse=True)
