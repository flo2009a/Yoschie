"""
Account & Moderation Manager
"""
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from models.db import insert, update, get_by_id, find, load_all, save_all
from models.models import Account, ModerationEntry, now

# ─── Passwort-Hashing ────────────────────────

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ─── Account CRUD ────────────────────────────

def create_account(roblox_name: str, password: str) -> dict:
    existing = find("accounts", roblox_name=roblox_name)
    if existing:
        raise ValueError(f"Roblox-Name '{roblox_name}' bereits vergeben.")
    acc = Account(roblox_name=roblox_name, password_hash=hash_password(password))
    return insert("accounts", acc.to_dict())


def login(roblox_name: str, password: str) -> dict:
    results = find("accounts", roblox_name=roblox_name)
    if not results:
        raise ValueError("Account nicht gefunden.")
    acc = results[0]
    if acc["is_banned"]:
        exp = acc.get("ban_expires")
        if exp is None or datetime.fromisoformat(exp) > datetime.now():
            reason = "Du bist permanent gesperrt." if exp is None else f"Du bist gesperrt bis {exp}."
            raise PermissionError(reason)
        # Ban abgelaufen → automatisch aufheben
        update("accounts", acc["id"], {"is_banned": False, "ban_expires": None})
    if acc["is_deleted"]:
        raise PermissionError("Dieser Account wurde gelöscht.")
    if acc["password_hash"] != hash_password(password):
        raise ValueError("Falsches Passwort.")
    update("accounts", acc["id"], {"last_login": now()})
    return acc


def change_password(account_id: str, old_pw: str, new_pw: str) -> bool:
    acc = get_by_id("accounts", account_id)
    if not acc or acc["password_hash"] != hash_password(old_pw):
        raise ValueError("Altes Passwort falsch.")
    update("accounts", account_id, {"password_hash": hash_password(new_pw)})
    return True


def request_delete_account(account_id: str) -> str:
    """Markiert Account als löschbereit — Super Admin muss bestätigen."""
    update("accounts", account_id, {"pending_delete": True})
    return "Löschantrag gestellt. Super Admin muss bestätigen."


def confirm_delete_account(account_id: str, superadmin_id: str) -> bool:
    admin = get_by_id("accounts", superadmin_id)
    if not admin or admin["role"] != "superadmin":
        raise PermissionError("Nur Super Admins dürfen Accounts löschen.")
    update("accounts", account_id, {"is_deleted": True, "pending_delete": False})
    return True


def search_accounts(query: str) -> list[dict]:
    """Suche nach Roblox-Name (case-insensitive Teilstring)."""
    all_accs = load_all("accounts")
    q = query.lower()
    return [a for a in all_accs if q in a["roblox_name"].lower()]


def filter_accounts(
    banned: Optional[bool] = None,
    has_warns: Optional[bool] = None,
    new_only: bool = False
) -> list[dict]:
    accs = load_all("accounts")
    if banned is not None:
        accs = [a for a in accs if a["is_banned"] == banned]
    if has_warns is not None:
        accs = [a for a in accs if (a["warn_count"] > 0) == has_warns]
    if new_only:
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        accs = [a for a in accs if a["created_at"] >= cutoff]
    return accs


# ─── Rollen-Verwaltung ───────────────────────

def set_role(account_id: str, new_role: str, superadmin_id: str) -> dict:
    admin = get_by_id("accounts", superadmin_id)
    # Bootstrap: wenn noch kein Superadmin existiert, darf der erste sich selbst ernennen
    all_accs = load_all("accounts")
    any_superadmin = any(a["role"] == "superadmin" for a in all_accs)
    if any_superadmin:
        if not admin or admin["role"] != "superadmin":
            raise PermissionError("Nur Super Admins dürfen Rollen vergeben.")
    return update("accounts", account_id, {"role": new_role})


# ─── Moderation ──────────────────────────────

def _can_issue(action: str, issuer_role: str) -> bool:
    allowed = {
        "warn":   ["mod", "admin", "superadmin"],
        "kick":   ["mod", "admin", "superadmin"],
        "note":   ["mod", "admin", "superadmin"],
        "ban":    ["admin", "superadmin"],
        "unban":  ["admin", "superadmin"],
    }
    return issuer_role in allowed.get(action, [])


def add_moderation(
    account_id: str,
    action: str,
    reason: str,
    issued_by_id: str,
    ban_days: Optional[int] = None
) -> dict:
    issuer = get_by_id("accounts", issued_by_id)
    if not issuer:
        raise ValueError("Ausführender Account nicht gefunden.")
    if not _can_issue(action, issuer["role"]):
        raise PermissionError(f"Rolle '{issuer['role']}' darf keine Aktion '{action}' ausführen.")

    ban_expires = None
    if action == "ban":
        ban_expires = (datetime.now() + timedelta(days=ban_days)).isoformat() if ban_days else None
        update("accounts", account_id, {"is_banned": True, "ban_expires": ban_expires})
    elif action == "unban":
        update("accounts", account_id, {"is_banned": False, "ban_expires": None})

    # Warn-Zähler erhöhen
    if action == "warn":
        acc = get_by_id("accounts", account_id)
        new_count = acc["warn_count"] + 1
        update("accounts", account_id, {"warn_count": new_count})
        if new_count >= 3:
            # Automatische Warnung (kann als Notiz gespeichert werden)
            auto = ModerationEntry(
                account_id=account_id,
                action="note",
                reason="⚠️ Automatisch: Account hat 3 Warns erreicht.",
                issued_by="system"
            )
            insert("moderation", auto.to_dict())

    entry = ModerationEntry(
        account_id=account_id,
        action=action,
        reason=reason,
        issued_by=issued_by_id,
        ban_expires=ban_expires
    )
    return insert("moderation", entry.to_dict())


def get_moderation_log(account_id: str) -> list[dict]:
    return find("moderation", account_id=account_id)


def player_visible_warns(account_id: str) -> int:
    """Spieler sieht nur die Anzahl, nicht den internen Text."""
    acc = get_by_id("accounts", account_id)
    return acc["warn_count"] if acc else 0
