"""
Item Manager — globale Warenliste, Inventar, Handel, Verfall, Diebstahl
"""
from datetime import datetime
from typing import Optional
from models.db import insert, update, get_by_id, find, load_all, save_all
from models.models import Item, now


# ─── Globale Warenliste (Super Admin) ────────

def create_global_item(
    superadmin_id: str,
    name: str,
    category: str,
    rarity: str = "common",
    description: str = "",
    requires_license: bool = False,
    is_vehicle_key: bool = False,
    base_price: float = 0.0,
    max_per_character: int = 99
) -> dict:
    _require_superadmin(superadmin_id)
    entry = {
        "id": f"gitem_{name.lower().replace(' ', '_')}_{_short_id()}",
        "name": name,
        "category": category,
        "rarity": rarity,
        "description": description,
        "requires_license": requires_license,
        "is_vehicle_key": is_vehicle_key,
        "base_price": base_price,
        "max_per_character": max_per_character,
        "created_at": now(),
        "created_by": superadmin_id,
    }
    items = load_all("global_items")
    items.append(entry)
    save_all("global_items", items)
    return entry


def get_global_items(category: str = None) -> list[dict]:
    items = load_all("global_items")
    if category:
        items = [i for i in items if i.get("category") == category]
    return items


def get_global_item(global_item_id: str) -> Optional[dict]:
    return next((i for i in load_all("global_items") if i["id"] == global_item_id), None)


def update_global_item(superadmin_id: str, global_item_id: str, **kwargs) -> dict:
    _require_superadmin(superadmin_id)
    items = load_all("global_items")
    for i, item in enumerate(items):
        if item["id"] == global_item_id:
            items[i] = {**item, **kwargs}
            save_all("global_items", items)
            return items[i]
    raise ValueError("Globales Item nicht gefunden.")


def delete_global_item(superadmin_id: str, global_item_id: str) -> bool:
    _require_superadmin(superadmin_id)
    items = load_all("global_items")
    filtered = [i for i in items if i["id"] != global_item_id]
    if len(filtered) == len(items):
        raise ValueError("Item nicht gefunden.")
    save_all("global_items", filtered)
    return True


# ─── Instanz-Items (im Spiel) ────────────────

def spawn_item(
    global_item_id: str,
    owner_character_id: str,
    admin_id: str,
    condition: str = "new",
    expires_at: Optional[str] = None
) -> dict:
    """Admin gibt einem Charakter ein Item-Exemplar."""
    _require_admin(admin_id)
    global_item = get_global_item(global_item_id)
    if not global_item:
        raise ValueError("Globales Item nicht gefunden.")

    # Limit prüfen
    owned = find("items", owner_character_id=owner_character_id)
    same = [i for i in owned if i["global_item_id"] == global_item_id and not i.get("is_trashed")]
    if len(same) >= global_item.get("max_per_character", 99):
        raise ValueError(f"Charakter hat bereits das Maximum dieses Items ({global_item['max_per_character']}).")

    item = {
        "id": _short_id(),
        "global_item_id": global_item_id,
        "name": global_item["name"],
        "category": global_item["category"],
        "rarity": global_item["rarity"],
        "condition": condition,
        "owner_character_id": owner_character_id,
        "expires_at": expires_at,
        "requires_license": global_item["requires_license"],
        "is_vehicle_key": global_item["is_vehicle_key"],
        "is_stolen": False,
        "is_trashed": False,
        "created_at": now(),
        "given_by": admin_id,
    }
    inserted = insert("items", item)

    # Inventar des Charakters aktualisieren
    char = get_by_id("characters", owner_character_id)
    inv = char.get("inventory", [])
    inv.append(inserted["id"])
    update("characters", owner_character_id, {"inventory": inv})
    return inserted


def get_inventory(character_id: str) -> list[dict]:
    """Gibt alle aktiven Items eines Charakters zurück, prüft Verfall."""
    items = find("items", owner_character_id=character_id)
    result = []
    for item in items:
        if item.get("is_trashed"):
            continue
        # Verfall prüfen
        if item.get("expires_at"):
            if datetime.fromisoformat(item["expires_at"]) < datetime.now():
                update("items", item["id"], {"is_trashed": True, "condition": "broken"})
                _remove_from_char_inv(character_id, item["id"])
                continue
        result.append(item)
    return result


def trade_item(
    item_id: str,
    from_character_id: str,
    to_character_id: str,
    price: float = 0.0
) -> dict:
    """Handel zwischen zwei Charakteren."""
    item = get_by_id("items", item_id)
    if not item:
        raise ValueError("Item nicht gefunden.")
    if item["owner_character_id"] != from_character_id:
        raise PermissionError("Charakter besitzt dieses Item nicht.")
    if item.get("is_trashed"):
        raise ValueError("Dieses Item existiert nicht mehr.")

    # Waffenschein prüfen
    if item.get("requires_license"):
        to_char = get_by_id("characters", to_character_id)
        has_license = any(
            i.get("category") == "document" and "waffenschein" in i.get("name", "").lower()
            for i in get_inventory(to_character_id)
        )
        if not has_license:
            raise PermissionError("Empfänger hat keinen Waffenschein.")

    # Zahlung
    if price > 0:
        from_char = get_by_id("characters", from_character_id)
        to_char = get_by_id("characters", to_character_id)
        if to_char["balance"] < price:
            raise ValueError("Empfänger hat nicht genug Guthaben.")
        update("characters", to_character_id, {"balance": round(to_char["balance"] - price, 2)})
        update("characters", from_character_id, {"balance": round(from_char["balance"] + price, 2)})

        from models.models import Transaction
        tx = Transaction(
            sender_id=to_character_id,
            receiver_id=from_character_id,
            amount=price,
            note=f"Item-Handel: {item['name']}",
            tx_type="transfer"
        )
        insert("transactions", tx.to_dict())

    # Besitzer wechseln
    _remove_from_char_inv(from_character_id, item_id)
    to_inv = get_by_id("characters", to_character_id).get("inventory", [])
    to_inv.append(item_id)
    update("characters", to_character_id, {"inventory": to_inv})
    return update("items", item_id, {"owner_character_id": to_character_id})


def steal_item(item_id: str, thief_character_id: str, admin_id: str) -> dict:
    """Admin markiert Item als gestohlen und überträgt Besitz."""
    _require_admin(admin_id)
    item = get_by_id("items", item_id)
    if not item:
        raise ValueError("Item nicht gefunden.")
    old_owner = item["owner_character_id"]
    _remove_from_char_inv(old_owner, item_id)
    new_inv = get_by_id("characters", thief_character_id).get("inventory", [])
    new_inv.append(item_id)
    update("characters", thief_character_id, {"inventory": new_inv})
    return update("items", item_id, {
        "owner_character_id": thief_character_id,
        "is_stolen": True,
        "stolen_from": old_owner,
        "stolen_at": now()
    })


def damage_item(item_id: str, new_condition: str) -> dict:
    if new_condition not in ("used", "damaged", "broken"):
        raise ValueError("Ungültiger Zustand.")
    return update("items", item_id, {"condition": new_condition})


def trash_item(item_id: str, character_id: str) -> bool:
    item = get_by_id("items", item_id)
    if not item or item["owner_character_id"] != character_id:
        raise PermissionError("Kein Zugriff auf dieses Item.")
    update("items", item_id, {"is_trashed": True})
    _remove_from_char_inv(character_id, item_id)
    return True


def check_expiring_items() -> list[dict]:
    """Gibt alle abgelaufenen Items zurück und markiert sie (Cronjob)."""
    all_items = load_all("items")
    expired = []
    for item in all_items:
        if item.get("is_trashed") or not item.get("expires_at"):
            continue
        if datetime.fromisoformat(item["expires_at"]) < datetime.now():
            update("items", item["id"], {"is_trashed": True, "condition": "broken"})
            if item.get("owner_character_id"):
                _remove_from_char_inv(item["owner_character_id"], item["id"])
            expired.append(item)
    return expired


# ─── Hilfsfunktionen ─────────────────────────

def _remove_from_char_inv(character_id: str, item_id: str):
    char = get_by_id("characters", character_id)
    if char:
        inv = [i for i in char.get("inventory", []) if i != item_id]
        update("characters", character_id, {"inventory": inv})


def _short_id() -> str:
    import uuid
    return str(uuid.uuid4())[:8]


def _require_admin(account_id: str):
    acc = get_by_id("accounts", account_id)
    if not acc or acc["role"] not in ("admin", "superadmin"):
        raise PermissionError("Nur Admins haben diese Berechtigung.")


def _require_superadmin(account_id: str):
    acc = get_by_id("accounts", account_id)
    if not acc or acc["role"] != "superadmin":
        raise PermissionError("Nur Super Admins haben diese Berechtigung.")
