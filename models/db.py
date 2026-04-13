"""
JSON-Datenbank — Laden, Speichern, Suchen
Alle Daten werden in /data/*.json gespeichert.
"""
import json
import os
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# Dateipfade
FILES = {
    "accounts":      DATA_DIR / "accounts.json",
    "characters":    DATA_DIR / "characters.json",
    "items":         DATA_DIR / "items.json",
    "transactions":  DATA_DIR / "transactions.json",
    "emergency":     DATA_DIR / "emergency_calls.json",
    "shops":         DATA_DIR / "shops.json",
    "factions":      DATA_DIR / "factions.json",
    "moderation":    DATA_DIR / "moderation.json",
    "rp_events":     DATA_DIR / "rp_events.json",
    "wanted":        DATA_DIR / "wanted_notices.json",
    "wanted_posters": DATA_DIR / "wanted_posters.json",
    "court":         DATA_DIR / "court_cases.json",
    "news":          DATA_DIR / "news.json",
    "settings":      DATA_DIR / "settings.json",
    "global_items":  DATA_DIR / "global_items.json",  # Admin-Warenliste
}


def _load(key: str) -> list | dict:
    path = FILES[key]
    if not path.exists():
        return {} if key == "settings" else []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(key: str, data: list | dict) -> None:
    with open(FILES[key], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Generische CRUD-Helfer ───────────────────

def load_all(key: str) -> list[dict]:
    return _load(key)


def save_all(key: str, records: list[dict]) -> None:
    _save(key, records)


def get_by_id(key: str, record_id: str) -> dict | None:
    return next((r for r in load_all(key) if r.get("id") == record_id), None)


def insert(key: str, record: dict) -> dict:
    records = load_all(key)
    records.append(record)
    save_all(key, records)
    return record


def update(key: str, record_id: str, updates: dict) -> dict | None:
    records = load_all(key)
    for i, r in enumerate(records):
        if r.get("id") == record_id:
            records[i] = {**r, **updates}
            save_all(key, records)
            return records[i]
    return None


def delete(key: str, record_id: str) -> bool:
    records = load_all(key)
    filtered = [r for r in records if r.get("id") != record_id]
    if len(filtered) == len(records):
        return False
    save_all(key, filtered)
    return True


def find(key: str, **kwargs) -> list[dict]:
    """Filtert Records nach beliebig vielen Feldern (exakter Match)."""
    records = load_all(key)
    for field, value in kwargs.items():
        records = [r for r in records if r.get(field) == value]
    return records


# ─── Settings (singleton dict) ───────────────

def load_settings() -> dict:
    return _load("settings")


def save_settings(settings: dict) -> None:
    _save("settings", settings)
