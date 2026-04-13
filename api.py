"""
API Router — einheitliche Schnittstelle für alle Operationen.
Jede Funktion gibt {"ok": True, "data": ...} oder {"ok": False, "error": "..."} zurück.
Kann direkt von einem Web-Framework (Flask/FastAPI) oder CLI genutzt werden.
"""
from typing import Any


def _ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}


def handle(action: str, payload: dict) -> dict:
    """
    Zentraler Dispatcher.
    action: "resource.operation"  z.B. "account.create", "character.kill"
    payload: dict mit allen nötigen Parametern
    """
    try:
        return _dispatch(action, payload)
    except (ValueError, PermissionError, KeyError) as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"Interner Fehler: {e}")


def _dispatch(action: str, p: dict) -> dict:
    # ── ACCOUNTS ─────────────────────────────
    if action == "account.create":
        from managers.account_manager import create_account
        return _ok(create_account(p["roblox_name"], p["password"]))

    if action == "account.login":
        from managers.account_manager import login
        return _ok(login(p["roblox_name"], p["password"]))

    if action == "account.change_password":
        from managers.account_manager import change_password
        return _ok(change_password(p["account_id"], p["old_password"], p["new_password"]))

    if action == "account.request_delete":
        from managers.account_manager import request_delete_account
        return _ok(request_delete_account(p["account_id"]))

    if action == "account.confirm_delete":
        from managers.account_manager import confirm_delete_account
        return _ok(confirm_delete_account(p["account_id"], p["superadmin_id"]))

    if action == "account.search":
        from managers.account_manager import search_accounts
        return _ok(search_accounts(p["query"]))

    if action == "account.filter":
        from managers.account_manager import filter_accounts
        return _ok(filter_accounts(
            banned=p.get("banned"),
            has_warns=p.get("has_warns"),
            new_only=p.get("new_only", False)
        ))

    if action == "account.set_role":
        from managers.account_manager import set_role
        return _ok(set_role(p["account_id"], p["role"], p["superadmin_id"]))

    if action == "account.warns":
        from managers.account_manager import player_visible_warns
        return _ok({"warn_count": player_visible_warns(p["account_id"])})

    # ── MODERATION ───────────────────────────
    if action == "mod.add":
        from managers.account_manager import add_moderation
        return _ok(add_moderation(
            p["account_id"], p["action"], p["reason"],
            p["issued_by"], p.get("ban_days")
        ))

    if action == "mod.log":
        from managers.account_manager import get_moderation_log
        return _ok(get_moderation_log(p["account_id"]))

    # ── CHARAKTERE ───────────────────────────
    if action == "character.create":
        from managers.character_manager import create_character
        from models.db import load_settings
        economy = load_settings().get("economy", {})
        return _ok(create_character(
            account_id=p["account_id"],
            name=p["name"],
            age=p["age"],
            appearance=p["appearance"],
            job=p["job"],
            backstory=p["backstory"],
            faction_id=p.get("faction_id"),
            starting_balance=economy.get("starting_capital", 500.0)
        ))

    if action == "character.list":
        from managers.character_manager import get_characters_for_account
        return _ok(get_characters_for_account(p["account_id"]))

    if action == "character.set_active":
        from managers.character_manager import set_active_character
        return _ok(set_active_character(p["account_id"], p["character_id"]))

    if action == "character.kill":
        from managers.character_manager import kill_character
        return _ok(kill_character(p["character_id"], p["admin_id"]))

    if action == "character.reputation":
        from managers.character_manager import update_reputation
        return _ok(update_reputation(p["character_id"], p["delta"], p.get("reason", "")))

    if action == "character.medical_update":
        from managers.character_manager import update_medical_record
        return _ok(update_medical_record(
            p["character_id"],
            note=p.get("note"),
            blood_type=p.get("blood_type"),
            allergies=p.get("allergies")
        ))

    if action == "character.drivers_license":
        from managers.character_manager import set_drivers_license
        return _ok(set_drivers_license(p["character_id"], p["status"]))

    # ── WIRTSCHAFT ───────────────────────────
    if action == "economy.transfer":
        from managers.economy_manager import transfer
        return _ok(transfer(
            p["sender_id"], p["receiver_id"], p["amount"],
            p.get("note", ""), p.get("black_market", False)
        ))

    if action == "economy.admin_adjust":
        from managers.economy_manager import admin_adjust_balance
        return _ok(admin_adjust_balance(p["admin_id"], p["character_id"], p["amount"], p.get("note", "")))

    if action == "economy.history":
        from managers.economy_manager import get_transaction_history
        return _ok(get_transaction_history(p["character_id"]))

    if action == "economy.bank_lock":
        from managers.economy_manager import set_bank_lock
        return _ok(set_bank_lock(p["locked"], p["superadmin_id"]))

    if action == "economy.wealth_tax":
        from managers.scheduler import collect_wealth_tax
        return _ok(collect_wealth_tax(p["superadmin_id"], p["rate_percent"]))

    if action == "economy.force_salaries":
        from managers.scheduler import force_salary_run
        return _ok(force_salary_run(p["superadmin_id"]))

    # ── ITEMS ────────────────────────────────
    if action == "item.create_global":
        from managers.item_manager import create_global_item
        return _ok(create_global_item(
            p["superadmin_id"], p["name"], p["category"],
            rarity=p.get("rarity", "common"),
            description=p.get("description", ""),
            requires_license=p.get("requires_license", False),
            is_vehicle_key=p.get("is_vehicle_key", False),
            base_price=p.get("base_price", 0.0),
            max_per_character=p.get("max_per_character", 99)
        ))

    if action == "item.global_list":
        from managers.item_manager import get_global_items
        return _ok(get_global_items(p.get("category")))

    if action == "item.spawn":
        from managers.item_manager import spawn_item
        return _ok(spawn_item(
            p["global_item_id"], p["character_id"], p["admin_id"],
            condition=p.get("condition", "new"),
            expires_at=p.get("expires_at")
        ))

    if action == "item.inventory":
        from managers.item_manager import get_inventory
        return _ok(get_inventory(p["character_id"]))

    if action == "item.trade":
        from managers.item_manager import trade_item
        return _ok(trade_item(p["item_id"], p["from_character_id"], p["to_character_id"], p.get("price", 0.0)))

    if action == "item.steal":
        from managers.item_manager import steal_item
        return _ok(steal_item(p["item_id"], p["thief_character_id"], p["admin_id"]))

    if action == "item.damage":
        from managers.item_manager import damage_item
        return _ok(damage_item(p["item_id"], p["condition"]))

    # ── NOTRUF ───────────────────────────────
    if action == "emergency.create":
        from managers.emergency_manager import create_call
        return _ok(create_call(
            p["location"], p["description"], p["call_type"],
            priority=p.get("priority", "medium"),
            caller_id=p.get("caller_id"),
            anonymous=p.get("anonymous", False)
        ))

    if action == "emergency.update":
        from managers.emergency_manager import update_call_status
        return _ok(update_call_status(p["call_id"], p["status"], p.get("responder_id")))

    if action == "emergency.note":
        from managers.emergency_manager import add_note_to_call
        return _ok(add_note_to_call(p["call_id"], p["note"]))

    if action == "emergency.false_alarm":
        from managers.emergency_manager import mark_false_alarm
        return _ok(mark_false_alarm(p["call_id"], p["account_id"]))

    if action == "emergency.open":
        from managers.emergency_manager import get_open_calls
        return _ok(get_open_calls(p.get("type")))

    # ── SHOPS ────────────────────────────────
    if action == "shop.create":
        from managers.shop_manager import create_shop
        return _ok(create_shop(p["name"], p["owner_character_id"], p["category"]))

    if action == "shop.activate":
        from managers.shop_manager import admin_activate_shop
        return _ok(admin_activate_shop(p["shop_id"], p["admin_id"], p["active"]))

    if action == "shop.set_open":
        from managers.shop_manager import set_shop_open
        return _ok(set_shop_open(p["shop_id"], p["owner_character_id"], p["is_open"]))

    if action == "shop.stock":
        from managers.shop_manager import stock_item
        return _ok(stock_item(p["shop_id"], p["global_item_id"], p["quantity"], p["buy_price"], p["sell_price"]))

    if action == "shop.buy":
        from managers.shop_manager import buy_item
        return _ok(buy_item(p["shop_id"], p["global_item_id"], p["buyer_character_id"]))

    if action == "shop.withdraw":
        from managers.shop_manager import withdraw_from_shop
        return _ok(withdraw_from_shop(p["shop_id"], p["owner_character_id"], p["amount"]))

    if action == "shop.rate":
        from managers.shop_manager import rate_shop
        return _ok(rate_shop(p["shop_id"], p["buyer_character_id"], p["rating"], p.get("comment", "")))

    if action == "shop.rob":
        from managers.shop_manager import rob_shop
        return _ok(rob_shop(p["shop_id"], p["admin_id"]))

    # ── FRAKTIONEN ───────────────────────────
    if action == "faction.create":
        from managers.faction_manager import create_faction
        return _ok(create_faction(
            p["superadmin_id"], p["name"], p["description"],
            p["color"], p["faction_type"],
            ranks=p.get("ranks", [])
        ))

    if action == "faction.appoint_leader":
        from managers.faction_manager import appoint_leader
        return _ok(appoint_leader(p["faction_id"], p["character_id"], p["admin_id"]))

    if action == "faction.add_member":
        from managers.faction_manager import add_member
        return _ok(add_member(p["faction_id"], p["character_id"], p["rank_name"], p["leader_character_id"]))

    if action == "faction.remove_member":
        from managers.faction_manager import remove_member
        return _ok(remove_member(p["faction_id"], p["character_id"], p["leader_character_id"]))

    if action == "faction.announce":
        from managers.faction_manager import post_announcement
        return _ok(post_announcement(p["faction_id"], p["leader_character_id"], p["text"]))

    if action == "faction.members":
        from managers.faction_manager import get_members
        return _ok(get_members(p["faction_id"]))

    # ── POLIZEI / STECKBRIEF ─────────────────
    if action == "police.issue_poster":
        from managers.police_manager import create_wanted_poster
        return _ok(create_wanted_poster(
            p["issuer_character_id"], p["target_character_id"],
            p["crime_description"], p.get("evidence", ""),
            p.get("reward", 0.0), p.get("dangerous", False)
        ))

    if action == "police.resolve_poster":
        from managers.police_manager import resolve_poster
        return _ok(resolve_poster(p["poster_id"], p["resolved_by_character_id"], p.get("note", "")))

    if action == "police.active_posters":
        from managers.police_manager import get_active_posters
        return _ok(get_active_posters())

    if action == "police.file":
        from managers.police_manager import get_police_file
        return _ok(get_police_file(p["character_id"], p["requesting_character_id"]))

    if action == "police.add_evidence":
        from managers.police_manager import add_evidence
        return _ok(add_evidence(p["poster_id"], p["officer_character_id"], p["evidence_text"]))

    # ── RP-TOOLS ─────────────────────────────
    if action == "rp.log_event":
        from managers.rp_manager import log_rp_event
        return _ok(log_rp_event(p["title"], p["description"], p.get("involved_ids", []), p["admin_id"]))

    if action == "rp.issue_wanted":
        from managers.rp_manager import issue_wanted
        return _ok(issue_wanted(p["character_id"], p["description"], p["reward"], p["admin_id"]))

    if action == "rp.court":
        from managers.rp_manager import create_court_case
        return _ok(create_court_case(
            p["defendant_id"], p["charges"], p["verdict"], p["sentence"], p["admin_id"]
        ))

    if action == "rp.publish_news":
        from managers.rp_manager import publish_news
        return _ok(publish_news(p["title"], p["content"], p["author_character_id"], p.get("is_admin", False)))

    if action == "rp.news":
        from managers.rp_manager import get_news
        return _ok(get_news(p.get("limit", 20)))

    if action == "rp.stats":
        from managers.rp_manager import get_stats
        return _ok(get_stats())

    # ── SERVER-EINSTELLUNGEN ─────────────────
    if action == "server.settings":
        from managers.rp_manager import get_settings
        return _ok(get_settings())

    if action == "server.update":
        from managers.rp_manager import update_settings
        kwargs = {k: v for k, v in p.items() if k != "superadmin_id"}
        return _ok(update_settings(p["superadmin_id"], **kwargs))

    if action == "server.maintenance":
        from managers.rp_manager import set_maintenance
        return _ok(set_maintenance(p["superadmin_id"], p["active"], p.get("message", "")))

    if action == "server.event_start":
        from managers.rp_manager import start_event
        return _ok(start_event(p["superadmin_id"], p["event_type"]))

    if action == "server.event_end":
        from managers.rp_manager import end_event
        return _ok(end_event(p["superadmin_id"], p["event_type"]))

    if action == "server.announce":
        from managers.rp_manager import send_announcement
        return _ok(send_announcement(p["superadmin_id"], p["message"]))

    if action == "server.set_laws":
        from managers.rp_manager import set_laws
        return _ok(set_laws(p["superadmin_id"], p["laws"]))

    if action == "scheduler.run":
        from managers.scheduler import run_all_schedulers
        return _ok(run_all_schedulers())

    return _err(f"Unbekannte Aktion: '{action}'")
