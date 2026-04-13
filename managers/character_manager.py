"""
Charakter Manager
"""
from typing import Optional
from models.db import insert, update, get_by_id, find, load_all
from models.models import Character, MedicalRecord, now

MAX_CHARACTERS = 3


def create_character(
    account_id: str,
    name: str,
    age: int,
    appearance: str,
    job: str,
    backstory: str,
    faction_id: Optional[str] = None,
    starting_balance: float = 500.0
) -> dict:
    existing = find("characters", account_id=account_id)
    active = [c for c in existing if not c["is_deleted"]]
    if len(active) >= MAX_CHARACTERS:
        raise ValueError(f"Maximal {MAX_CHARACTERS} Charaktere erlaubt.")

    char = Character(
        account_id=account_id,
        name=name,
        age=age,
        appearance=appearance,
        job=job,
        backstory=backstory,
        faction_id=faction_id,
        balance=starting_balance
    )
    record = char.to_dict()
    inserted = insert("characters", record)

    # Account-Character-Liste aktualisieren
    from models.db import get_by_id as gbi
    acc = gbi("accounts", account_id)
    if acc:
        ids = acc.get("character_ids", [])
        ids.append(inserted["id"])
        update("accounts", account_id, {"character_ids": ids})

    return inserted


def get_characters_for_account(account_id: str) -> list[dict]:
    return [c for c in find("characters", account_id=account_id) if not c.get("is_deleted")]


def set_active_character(account_id: str, character_id: str) -> dict:
    chars = find("characters", account_id=account_id)
    # Alle deaktivieren
    for c in chars:
        update("characters", c["id"], {"is_active": c["id"] == character_id})
    return get_by_id("characters", character_id)


def kill_character(character_id: str, admin_id: str) -> dict:
    char = get_by_id("characters", character_id)
    if not char:
        raise ValueError("Charakter nicht gefunden.")
    if char["is_dead"]:
        raise ValueError("Charakter ist bereits tot.")
    return update("characters", character_id, {"is_dead": True, "is_active": False})


def update_reputation(character_id: str, delta: int, reason: str = "") -> dict:
    char = get_by_id("characters", character_id)
    if not char:
        raise ValueError("Charakter nicht gefunden.")
    new_rep = char["reputation"] + delta
    return update("characters", character_id, {"reputation": new_rep})


def update_medical_record(character_id: str, note: str = None, blood_type: str = None, allergies: list = None) -> dict:
    char = get_by_id("characters", character_id)
    if not char:
        raise ValueError("Charakter nicht gefunden.")
    med = char.get("medical_record", {})
    if note:
        med.setdefault("notes", []).append(note)
    if blood_type:
        med["blood_type"] = blood_type
    if allergies:
        med["allergies"] = allergies
    med["updated_at"] = now()
    return update("characters", character_id, {"medical_record": med})


def set_drivers_license(character_id: str, status: str) -> dict:
    if status not in ("valid", "revoked", "never"):
        raise ValueError("Ungültiger Führerscheinstatus.")
    return update("characters", character_id, {"drivers_license": status})


def add_vehicle_license(character_id: str, vehicle_class: str) -> dict:
    char = get_by_id("characters", character_id)
    licenses = char.get("vehicle_licenses", [])
    if vehicle_class not in licenses:
        licenses.append(vehicle_class)
    return update("characters", character_id, {"vehicle_licenses": licenses})
