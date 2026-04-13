"""
Fraktionen Manager
"""
from models.db import insert, update, get_by_id, find, load_all
from models.models import Faction, FactionRank, FactionMember, now


def create_faction(
    superadmin_id: str,
    name: str,
    description: str,
    color: str,
    faction_type: str,
    ranks: list[dict] = None
) -> dict:
    admin = get_by_id("accounts", superadmin_id)
    if not admin or admin["role"] != "superadmin":
        raise PermissionError("Nur Super Admin darf Fraktionen erstellen.")
    f = Faction(
        name=name,
        description=description,
        color=color,
        faction_type=faction_type,
        ranks=[FactionRank(**r) for r in (ranks or [])]
    )
    return insert("factions", f.to_dict())


def appoint_leader(faction_id: str, character_id: str, admin_id: str) -> dict:
    admin = get_by_id("accounts", admin_id)
    if not admin or admin["role"] not in ("admin", "superadmin"):
        raise PermissionError("Nur Admins dürfen Fraktionsleiter ernennen.")
    return update("factions", faction_id, {"leader_character_id": character_id})


def add_member(faction_id: str, character_id: str, rank_name: str, leader_character_id: str) -> dict:
    faction = get_by_id("factions", faction_id)
    if faction["leader_character_id"] != leader_character_id:
        raise PermissionError("Nur der Fraktionsleiter kann Mitglieder aufnehmen.")
    members = faction.get("members", [])
    if any(m["character_id"] == character_id for m in members):
        raise ValueError("Charakter ist bereits Mitglied.")
    members.append(FactionMember(character_id=character_id, rank_name=rank_name).to_dict())
    # Charakter-Fraktion setzen
    update("characters", character_id, {"faction_id": faction_id})
    return update("factions", faction_id, {"members": members})


def remove_member(faction_id: str, character_id: str, leader_character_id: str) -> dict:
    faction = get_by_id("factions", faction_id)
    if faction["leader_character_id"] != leader_character_id:
        raise PermissionError("Nur der Fraktionsleiter kann Mitglieder entlassen.")
    members = [m for m in faction.get("members", []) if m["character_id"] != character_id]
    update("characters", character_id, {"faction_id": None})
    return update("factions", faction_id, {"members": members})


def post_announcement(faction_id: str, leader_character_id: str, text: str) -> dict:
    faction = get_by_id("factions", faction_id)
    if faction["leader_character_id"] != leader_character_id:
        raise PermissionError("Nur Fraktionsleiter dürfen Ankündigungen posten.")
    anns = faction.get("announcements", [])
    anns.append({"text": text, "posted_at": now(), "by": leader_character_id})
    return update("factions", faction_id, {"announcements": anns})


def get_members(faction_id: str) -> list[dict]:
    faction = get_by_id("factions", faction_id)
    return faction.get("members", []) if faction else []
