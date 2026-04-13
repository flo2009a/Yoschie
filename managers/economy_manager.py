"""
Wirtschaft & Transaktionen Manager
"""
from datetime import datetime
from typing import Optional
from models.db import insert, update, get_by_id, find, load_settings, save_settings
from models.models import Transaction, now


def _get_char(cid: str) -> dict:
    c = get_by_id("characters", cid)
    if not c:
        raise ValueError(f"Charakter '{cid}' nicht gefunden.")
    return c


def _update_balance(character_id: str, delta: float, black_market: bool = False) -> dict:
    char = _get_char(character_id)
    key = "black_market_balance" if black_market else "balance"
    new_bal = char[key] + delta
    debt_limit = -10000.0  # Schulden-Limit
    if new_bal < debt_limit:
        raise ValueError(f"Schulden-Limit erreicht ({debt_limit}).")
    return update("characters", character_id, {key: round(new_bal, 2)})


def transfer(
    sender_id: str,
    receiver_id: str,
    amount: float,
    note: str = "",
    black_market: bool = False
) -> dict:
    if amount <= 0:
        raise ValueError("Betrag muss positiv sein.")

    settings = load_settings()
    bank_locked = settings.get("economy", {}).get("bank_locked", False)
    if bank_locked and not black_market:
        raise PermissionError("Bank ist gesperrt (Bankraub-Event).")

    # Steuer abziehen
    tax_rate = settings.get("economy", {}).get("tax_rate", 0.0)
    tax = round(amount * tax_rate / 100, 2)
    net_amount = amount - tax

    _update_balance(sender_id, -amount, black_market)
    _update_balance(receiver_id, net_amount, black_market)

    tx = Transaction(
        sender_id=sender_id,
        receiver_id=receiver_id,
        amount=amount,
        note=note,
        tx_type="black_market" if black_market else "transfer"
    )
    record = insert("transactions", tx.to_dict())

    if tax > 0:
        tax_tx = Transaction(
            sender_id=sender_id,
            receiver_id="treasury",
            amount=tax,
            note=f"Steuer auf Überweisung #{record['id']}",
            tx_type="tax"
        )
        insert("transactions", tax_tx.to_dict())

    return record


def admin_adjust_balance(
    admin_id: str,
    character_id: str,
    amount: float,        # positiv = auszahlen, negativ = abziehen
    note: str = ""
) -> dict:
    from models.db import get_by_id as gbi
    admin = gbi("accounts", admin_id)
    if not admin or admin["role"] not in ("admin", "superadmin"):
        raise PermissionError("Nur Admins dürfen Guthaben anpassen.")
    _update_balance(character_id, amount)
    tx = Transaction(
        sender_id="admin:" + admin_id,
        receiver_id=character_id,
        amount=amount,
        note=note,
        tx_type="admin"
    )
    return insert("transactions", tx.to_dict())


def pay_salary(faction_id: str) -> list[dict]:
    """Zahlt Gehalt an alle Fraktionsmitglieder (wird per Scheduler aufgerufen)."""
    faction = get_by_id("factions", faction_id)
    if not faction:
        raise ValueError("Fraktion nicht gefunden.")
    results = []
    for member in faction.get("members", []):
        cid = member["character_id"]
        char = _get_char(cid)
        # Gehalt aus Fraktionskasse
        salary = 200.0  # Standardgehalt — kann je Rang angepasst werden
        if faction["treasury"] < salary:
            continue
        update("factions", faction_id, {"treasury": round(faction["treasury"] - salary, 2)})
        _update_balance(cid, salary)
        tx = Transaction(
            sender_id="faction:" + faction_id,
            receiver_id=cid,
            amount=salary,
            note="Gehalt",
            tx_type="salary"
        )
        results.append(insert("transactions", tx.to_dict()))
    return results


def get_transaction_history(character_id: str) -> list[dict]:
    all_tx = find("transactions")
    return [
        t for t in find("transactions")
        if t["sender_id"] == character_id or t["receiver_id"] == character_id
    ]


def set_bank_lock(locked: bool, superadmin_id: str) -> dict:
    from models.db import get_by_id as gbi
    admin = gbi("accounts", superadmin_id)
    if not admin or admin["role"] != "superadmin":
        raise PermissionError("Nur Super Admin darf Bankraub-Event starten.")
    settings = load_settings()
    settings.setdefault("economy", {})["bank_locked"] = locked
    save_settings(settings)
    return {"bank_locked": locked}
