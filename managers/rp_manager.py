"""
RP-Tools Manager — Fahndung, Gericht, Zeitung, Events, Server-Einstellungen
"""
from models.db import insert, update, get_by_id, find, load_all, load_settings, save_settings
from models.models import RPEvent, WantedNotice, CourtCase, NewsArticle, ServerSettings, now


# ─── RP-Event Log ────────────────────────────

def log_rp_event(title: str, description: str, involved_ids: list, admin_id: str) -> dict:
    _require_admin(admin_id)
    event = RPEvent(
        title=title,
        description=description,
        involved_character_ids=involved_ids,
        created_by=admin_id
    )
    return insert("rp_events", event.to_dict())


# ─── Fahndungsliste ───────────────────────────

def issue_wanted(character_id: str, description: str, reward: float, admin_id: str) -> dict:
    _require_admin(admin_id)
    notice = WantedNotice(
        character_id=character_id,
        description=description,
        reward=reward,
        issued_by=admin_id
    )
    return insert("wanted", notice.to_dict())


def resolve_wanted(notice_id: str, admin_id: str) -> dict:
    _require_admin(admin_id)
    return update("wanted", notice_id, {"is_active": False})


def get_active_wanted() -> list[dict]:
    return [w for w in load_all("wanted") if w.get("is_active")]


# ─── Gerichts-System ─────────────────────────

def create_court_case(
    defendant_id: str,
    charges: str,
    verdict: str,
    sentence: str,
    admin_id: str
) -> dict:
    _require_admin(admin_id)
    case = CourtCase(
        defendant_character_id=defendant_id,
        charges=charges,
        verdict=verdict,
        sentence=sentence,
        documented_by=admin_id
    )
    return insert("court", case.to_dict())


# ─── Zeitung / News ───────────────────────────

def publish_news(title: str, content: str, author_character_id: str, is_admin: bool = False) -> dict:
    article = NewsArticle(
        title=title,
        content=content,
        author_character_id=author_character_id,
        is_admin_post=is_admin
    )
    return insert("news", article.to_dict())


def get_news(limit: int = 20) -> list[dict]:
    articles = sorted(load_all("news"), key=lambda x: x["published_at"], reverse=True)
    return articles[:limit]


# ─── Server-Einstellungen ────────────────────

def get_settings() -> dict:
    s = load_settings()
    if not s:
        default = ServerSettings()
        save_settings(default.to_dict())
        return default.to_dict()
    return s


def update_settings(superadmin_id: str, **kwargs) -> dict:
    admin = get_by_id("accounts", superadmin_id)
    if not admin or admin["role"] != "superadmin":
        raise PermissionError("Nur Super Admin darf Server-Einstellungen ändern.")
    settings = get_settings()
    for key, val in kwargs.items():
        settings[key] = val
    save_settings(settings)
    return settings


def set_maintenance(superadmin_id: str, active: bool, message: str = "") -> dict:
    return update_settings(superadmin_id, maintenance_mode=active, maintenance_message=message)


def start_event(superadmin_id: str, event_type: str) -> dict:
    settings = get_settings()
    events = settings.get("active_events", [])
    if event_type not in events:
        events.append(event_type)
    return update_settings(superadmin_id, active_events=events)


def end_event(superadmin_id: str, event_type: str) -> dict:
    settings = get_settings()
    events = [e for e in settings.get("active_events", []) if e != event_type]
    return update_settings(superadmin_id, active_events=events)


def send_announcement(superadmin_id: str, message: str) -> dict:
    _require_superadmin(superadmin_id)
    entry = {"message": message, "sent_at": now(), "by": superadmin_id}
    settings = get_settings()
    anns = settings.get("announcements", [])
    anns.insert(0, entry)
    return update_settings(superadmin_id, announcements=anns[:50])  # letzten 50


def set_laws(superadmin_id: str, laws: list[str]) -> dict:
    return update_settings(superadmin_id, laws=laws)


# ─── Statistiken ─────────────────────────────

def get_stats() -> dict:
    from datetime import date
    today = date.today().isoformat()
    all_accounts = load_all("accounts")
    all_chars = load_all("characters")
    all_calls = load_all("emergency")
    all_tx = load_all("transactions")
    all_items = load_all("items")

    calls_today = [c for c in all_calls if c["created_at"].startswith(today)]
    tx_today = [t for t in all_tx if t["timestamp"].startswith(today)]

    # Meistgekaufte Items
    from collections import Counter
    shop_tx = [t for t in all_tx if t.get("tx_type") == "shop"]

    return {
        "active_accounts": sum(1 for a in all_accounts if not a["is_banned"] and not a["is_deleted"]),
        "total_characters": len(all_chars),
        "active_characters": sum(1 for c in all_chars if c.get("is_active") and not c.get("is_dead")),
        "calls_today": len(calls_today),
        "open_calls": sum(1 for c in all_calls if c["status"] != "closed"),
        "transactions_today": len(tx_today),
        "volume_today": round(sum(t["amount"] for t in tx_today), 2),
    }


# ─── Hilfsfunktionen ─────────────────────────

def _require_admin(account_id: str):
    acc = get_by_id("accounts", account_id)
    if not acc or acc["role"] not in ("admin", "superadmin"):
        raise PermissionError("Nur Admins haben diese Berechtigung.")


def _require_superadmin(account_id: str):
    acc = get_by_id("accounts", account_id)
    if not acc or acc["role"] != "superadmin":
        raise PermissionError("Nur Super Admins haben diese Berechtigung.")
