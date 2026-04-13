"""
Steckbrief-System — Polizei kann Steckbriefe auf Charaktere ausstellen
"""
from models.db import insert, update, get_by_id, find, load_all
from models.models import now
import uuid


def _short_id():
    return str(uuid.uuid4())[:8]


def _require_police_or_admin(character_id: str = None, account_id: str = None):
    """Erlaubt Polizei-Fraktion oder Admins."""
    if account_id:
        acc = get_by_id("accounts", account_id)
        if acc and acc["role"] in ("admin", "superadmin"):
            return
    if character_id:
        char = get_by_id("characters", character_id)
        if char:
            faction = get_by_id("factions", char.get("faction_id", ""))
            if faction and faction["name"].lower() in ("stadtpolizei", "polizei", "police"):
                return
    raise PermissionError("Nur Polizei-Fraktion oder Admins dürfen Steckbriefe ausstellen.")


def create_wanted_poster(
    issuer_character_id: str,
    target_character_id: str,
    crime_description: str,
    evidence: str = "",
    reward: float = 0.0,
    dangerous: bool = False
) -> dict:
    """Polizei-Charakter stellt Steckbrief aus."""
    _require_police_or_admin(character_id=issuer_character_id)

    target = get_by_id("characters", target_character_id)
    if not target:
        raise ValueError("Ziel-Charakter nicht gefunden.")

    poster = {
        "id": _short_id(),
        "target_character_id": target_character_id,
        "target_name": target["name"],
        "target_appearance": target.get("appearance", ""),
        "target_faction": target.get("faction_id"),
        "crime_description": crime_description,
        "evidence": evidence,
        "reward": reward,
        "dangerous": dangerous,
        "issued_by_character": issuer_character_id,
        "issued_at": now(),
        "is_active": True,
        "resolved_at": None,
        "resolved_by": None,
        "resolution_note": "",
    }
    inserted = insert("wanted_posters", poster)

    # Ruf des Ziel-Charakters verringern
    char_data = get_by_id("characters", target_character_id)
    new_rep = char_data["reputation"] - 10
    update("characters", target_character_id, {"reputation": new_rep})

    return inserted


def resolve_poster(
    poster_id: str,
    resolved_by_character_id: str,
    resolution_note: str = ""
) -> dict:
    """Steckbrief als erledigt markieren (Verhaftung, Freispruch etc.)."""
    _require_police_or_admin(character_id=resolved_by_character_id)
    return update("wanted_posters", poster_id, {
        "is_active": False,
        "resolved_at": now(),
        "resolved_by": resolved_by_character_id,
        "resolution_note": resolution_note
    })


def get_active_posters() -> list[dict]:
    return [p for p in load_all("wanted_posters") if p.get("is_active")]


def get_posters_for_character(character_id: str) -> list[dict]:
    return find("wanted_posters", target_character_id=character_id)


def add_evidence(poster_id: str, officer_character_id: str, evidence_text: str) -> dict:
    _require_police_or_admin(character_id=officer_character_id)
    poster = get_by_id("wanted_posters", poster_id)
    existing = poster.get("evidence", "")
    new_evidence = f"{existing}\n[{now()}] {evidence_text}".strip()
    return update("wanted_posters", poster_id, {"evidence": new_evidence})


# ─── Polizeiakte ─────────────────────────────

def get_police_file(character_id: str, requesting_character_id: str) -> dict:
    """Vollständige Polizeiakte eines Charakters (nur für Polizei/Admin)."""
    _require_police_or_admin(character_id=requesting_character_id)

    char = get_by_id("characters", character_id)
    if not char:
        raise ValueError("Charakter nicht gefunden.")

    posters = get_posters_for_character(character_id)

    # Notruf-Historie bei der der Char involviert war
    all_calls = load_all("emergency")
    involved_calls = [
        c for c in all_calls
        if character_id in c.get("assigned_to", []) or c.get("caller_character_id") == character_id
    ]

    # Gerichtsverfahren
    court_cases = find("court", defendant_character_id=character_id)

    return {
        "character": {
            "id": char["id"],
            "name": char["name"],
            "age": char["age"],
            "appearance": char["appearance"],
            "faction_id": char.get("faction_id"),
            "reputation": char["reputation"],
            "drivers_license": char["drivers_license"],
        },
        "wanted_posters": posters,
        "court_cases": court_cases,
        "involved_in_calls": len(involved_calls),
        "generated_at": now()
    }
