"""
Scheduler — Gehälter, Steuern, Item-Verfall, Auto-Events
Kann als Cronjob oder manuell ausgeführt werden.
Speichert den letzten Ausführungszeitpunkt in settings.json.
"""
import json
from datetime import datetime, timedelta
from models.db import load_all, load_settings, save_settings, get_by_id, update
from models.models import Transaction, now
from models.db import insert


INTERVAL_HOURS = {
    "daily":  24,
    "weekly": 168,
}


def run_all_schedulers(superadmin_id: str = "system") -> dict:
    """Führt alle Scheduler-Jobs aus. Gibt Bericht zurück."""
    report = {
        "run_at": now(),
        "salaries": [],
        "expired_items": [],
        "auto_bans_lifted": [],
    }

    settings = load_settings()
    economy = settings.get("economy", {})
    interval = economy.get("salary_interval", "weekly")
    hours = INTERVAL_HOURS.get(interval, 168)

    last_salary = settings.get("last_salary_run")
    due = True
    if last_salary:
        last_dt = datetime.fromisoformat(last_salary)
        due = (datetime.now() - last_dt).total_seconds() / 3600 >= hours

    if due:
        report["salaries"] = _pay_all_salaries(economy)
        settings["last_salary_run"] = now()
        save_settings(settings)

    report["expired_items"] = _expire_items()
    report["auto_bans_lifted"] = _lift_expired_bans()

    return report


# ─── Gehälter ────────────────────────────────

def _pay_all_salaries(economy: dict) -> list[dict]:
    """Zahlt Gehalt an alle aktiven Fraktionsmitglieder aus Fraktionskasse."""
    factions = load_all("factions")
    log = []

    for faction in factions:
        members = faction.get("members", [])
        if not members:
            continue

        # Gehalt je Rang bestimmen
        rank_salary_map = _build_rank_salary(faction.get("ranks", []))
        treasury = faction.get("treasury", 0.0)

        for member in members:
            cid = member["character_id"]
            char = get_by_id("characters", cid)
            if not char or char.get("is_dead") or not char.get("is_active"):
                continue

            rank_name = member.get("rank_name", "")
            salary = rank_salary_map.get(rank_name, 200.0)

            if treasury < salary:
                log.append({
                    "character": char["name"],
                    "faction": faction["name"],
                    "status": "skipped_no_funds",
                    "amount": 0
                })
                continue

            treasury = round(treasury - salary, 2)
            new_bal = round(char["balance"] + salary, 2)
            update("characters", cid, {"balance": new_bal})

            tx = Transaction(
                sender_id="faction:" + faction["id"],
                receiver_id=cid,
                amount=salary,
                note=f"Gehalt [{rank_name}] — {faction['name']}",
                tx_type="salary"
            )
            insert("transactions", tx.to_dict())
            log.append({
                "character": char["name"],
                "faction": faction["name"],
                "rank": rank_name,
                "amount": salary,
                "status": "paid"
            })

        update("factions", faction["id"], {"treasury": treasury})

    return log


def _build_rank_salary(ranks: list[dict]) -> dict[str, float]:
    """Gehalt je nach Rang-Level: Basis 200 + 50 pro Level."""
    result = {}
    for rank in ranks:
        level = rank.get("level", 0)
        result[rank["name"]] = 200.0 + level * 50.0
    return result


# ─── Item-Verfall ─────────────────────────────

def _expire_items() -> list[dict]:
    from managers.item_manager import check_expiring_items
    return check_expiring_items()


# ─── Bans ablaufen lassen ────────────────────

def _lift_expired_bans() -> list[dict]:
    accounts = load_all("accounts")
    lifted = []
    for acc in accounts:
        if not acc.get("is_banned"):
            continue
        exp = acc.get("ban_expires")
        if exp and datetime.fromisoformat(exp) <= datetime.now():
            update("accounts", acc["id"], {"is_banned": False, "ban_expires": None})
            lifted.append({"account": acc["roblox_name"], "was_banned_until": exp})
    return lifted


# ─── Manuelle Gehaltsauszahlung ──────────────

def force_salary_run(superadmin_id: str) -> list[dict]:
    acc = get_by_id("accounts", superadmin_id)
    if not acc or acc["role"] != "superadmin":
        raise PermissionError("Nur Super Admins dürfen Gehälter manuell auslösen.")
    settings = load_settings()
    economy = settings.get("economy", {})
    result = _pay_all_salaries(economy)
    settings["last_salary_run"] = now()
    save_settings(settings)
    return result


# ─── Steuer auf alle Guthaben ────────────────

def collect_wealth_tax(superadmin_id: str, rate_percent: float) -> dict:
    """Einmalige Vermögenssteuer auf alle Charakter-Konten."""
    acc = get_by_id("accounts", superadmin_id)
    if not acc or acc["role"] != "superadmin":
        raise PermissionError("Nur Super Admins dürfen Vermögenssteuern erheben.")

    chars = load_all("characters")
    total_collected = 0.0
    log = []
    for char in chars:
        if char.get("is_dead"):
            continue
        balance = char.get("balance", 0.0)
        if balance <= 0:
            continue
        tax = round(balance * rate_percent / 100, 2)
        new_bal = round(balance - tax, 2)
        update("characters", char["id"], {"balance": new_bal})
        total_collected += tax

        tx = Transaction(
            sender_id=char["id"],
            receiver_id="treasury",
            amount=tax,
            note=f"Vermögenssteuer {rate_percent}%",
            tx_type="tax"
        )
        insert("transactions", tx.to_dict())
        log.append({"character": char["name"], "tax": tax})

    return {"total_collected": round(total_collected, 2), "entries": log}
