"""
Flask Web-Server für das RP-System.
Startet mit: python app.py

Umgebungsvariablen (in .env oder Hosting-Dashboard setzen):
  SECRET_KEY   – zufälliger langer String (PFLICHT in Produktion)
  FLASK_ENV    – "production" oder "development"
  PORT         – Port (Standard: 5000)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from functools import wraps
import secrets
import api

# ─── App-Konfiguration ─────────────────────────────────
app = Flask(__name__)

# Secret Key: aus Umgebungsvariable oder sicherer Zufallsfall für Dev
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    if os.environ.get("FLASK_ENV") == "production":
        raise RuntimeError(
            "SECRET_KEY Umgebungsvariable ist nicht gesetzt!\n"
            "Führe aus: export SECRET_KEY=$(python3 -c \"import secrets; print(secrets.token_hex(32))\")"
        )
    _secret = secrets.token_hex(32)  # nur für lokale Entwicklung
app.secret_key = _secret

IS_PRODUCTION = os.environ.get("FLASK_ENV") == "production"

# ─── Sichere Cookie-Einstellungen ──────────────────────
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,        # kein JS-Zugriff auf Session-Cookie
    SESSION_COOKIE_SAMESITE="Lax",       # CSRF-Schutz
    SESSION_COOKIE_SECURE=IS_PRODUCTION, # nur HTTPS in Produktion
    PERMANENT_SESSION_LIFETIME=86400 * 7 # Session läuft nach 7 Tagen ab
)

# ─── HTTPS-Enforcement (nur in Produktion) ─────────────
if IS_PRODUCTION:
    try:
        from flask_talisman import Talisman
        Talisman(
            app,
            force_https=True,
            strict_transport_security=True,
            strict_transport_security_max_age=31536000,  # 1 Jahr HSTS
            content_security_policy={
                "default-src": "'self'",
                "style-src":   "'self' 'unsafe-inline' https://fonts.googleapis.com",
                "font-src":    "'self' https://fonts.gstatic.com",
                "script-src":  "'self' 'unsafe-inline'",
                "img-src":     "'self' data: https:",
            }
        )
        print("✅ HTTPS-Enforcement aktiv (Talisman)")
    except ImportError:
        print("⚠️  flask-talisman nicht installiert – kein HTTPS-Enforcement")

# ─── Rate-Limiting ─────────────────────────────────────
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per minute"],
        storage_uri="memory://",
    )
    _limiter_ok = True
    print("✅ Rate-Limiting aktiv")
except ImportError:
    _limiter_ok = False
    print("⚠️  flask-limiter nicht installiert – kein Rate-Limiting")

def rate_limit(limit_string):
    """Decorator-Wrapper der graceful degradiert wenn limiter fehlt."""
    def decorator(f):
        if _limiter_ok:
            return limiter.limit(limit_string)(f)
        return f
    return decorator

# ─── Helper ────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "account_id" not in session:
            return jsonify({"ok": False, "error": "Nicht eingeloggt"}), 401
        return f(*args, **kwargs)
    return decorated

def get_session_info():
    return {
        "account_id": session.get("account_id"),
        "roblox_name": session.get("roblox_name"),
        "role": session.get("role"),
        "active_character_id": session.get("active_character_id"),
    }

# ─── Seiten-Routes ─────────────────────────────────────

@app.route("/")
def index():
    if "account_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    if "account_id" not in session:
        return redirect(url_for("index"))
    return render_template("dashboard.html", user=get_session_info())

@app.route("/admin")
def admin_panel():
    if "account_id" not in session:
        return redirect(url_for("index"))
    role = session.get("role", "player")
    if role not in ("admin", "superadmin", "mod"):
        return redirect(url_for("dashboard"))
    return render_template("admin.html", user=get_session_info())

# ─── Auth API ──────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
@rate_limit("10 per hour")   # max 10 Registrierungen pro IP/Stunde
def register():
    d = request.json or {}
    result = api.handle("account.create", {
        "roblox_name": d.get("roblox_name", ""),
        "password": d.get("password", "")
    })
    return jsonify(result)

@app.route("/api/auth/login", methods=["POST"])
@rate_limit("20 per minute")  # Brute-Force-Schutz
def login_route():
    d = request.json or {}
    result = api.handle("account.login", {
        "roblox_name": d.get("roblox_name", ""),
        "password": d.get("password", "")
    })
    if result["ok"]:
        acc = result["data"]
        session.permanent = True
        session["account_id"] = acc["id"]
        session["roblox_name"] = acc["roblox_name"]
        session["role"] = acc["role"]
        session["active_character_id"] = None
        chars = api.handle("character.list", {"account_id": acc["id"]})
        if chars["ok"]:
            active = next((c for c in chars["data"] if c.get("is_active") and not c.get("is_dead")), None)
            if active:
                session["active_character_id"] = active["id"]
        # Passwort-Hash nie an den Client schicken
        result["data"].pop("password_hash", None)
    return jsonify(result)

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/auth/me")
def me():
    if "account_id" not in session:
        return jsonify({"ok": False, "error": "Nicht eingeloggt"})
    return jsonify({"ok": True, "data": get_session_info()})

# ─── Account API ───────────────────────────────────────

@app.route("/api/account/warns")
@login_required
def get_warns():
    return jsonify(api.handle("account.warns", {"account_id": session["account_id"]}))

@app.route("/api/account/change_password", methods=["POST"])
@login_required
def change_password():
    d = request.json
    return jsonify(api.handle("account.change_password", {
        "account_id": session["account_id"],
        "old_password": d.get("old_password"),
        "new_password": d.get("new_password")
    }))

@app.route("/api/account/request_delete", methods=["POST"])
@login_required
def request_delete():
    return jsonify(api.handle("account.request_delete", {"account_id": session["account_id"]}))

# ─── Charakter API ─────────────────────────────────────

@app.route("/api/characters")
@login_required
def list_characters():
    return jsonify(api.handle("character.list", {"account_id": session["account_id"]}))

@app.route("/api/characters/create", methods=["POST"])
@login_required
def create_character():
    d = request.json
    d["account_id"] = session["account_id"]
    return jsonify(api.handle("character.create", d))

@app.route("/api/characters/set_active", methods=["POST"])
@login_required
def set_active_character():
    d = request.json
    result = api.handle("character.set_active", {
        "account_id": session["account_id"],
        "character_id": d.get("character_id")
    })
    if result["ok"]:
        session["active_character_id"] = d.get("character_id")
    return jsonify(result)

@app.route("/api/characters/<char_id>/medical", methods=["POST"])
@login_required
def update_medical(char_id):
    d = request.json
    d["character_id"] = char_id
    return jsonify(api.handle("character.medical_update", d))

# ─── Wirtschaft API ────────────────────────────────────

@app.route("/api/economy/transfer", methods=["POST"])
@login_required
def transfer():
    d = request.json
    d["sender_id"] = session.get("active_character_id")
    return jsonify(api.handle("economy.transfer", d))

@app.route("/api/economy/history")
@login_required
def tx_history():
    char_id = session.get("active_character_id")
    if not char_id:
        return jsonify({"ok": False, "error": "Kein aktiver Charakter"})
    return jsonify(api.handle("economy.history", {"character_id": char_id}))

# ─── Notruf API ────────────────────────────────────────

@app.route("/api/emergency/calls")
@login_required
def get_calls():
    call_type = request.args.get("type")
    return jsonify(api.handle("emergency.open", {"type": call_type}))

@app.route("/api/emergency/create", methods=["POST"])
@login_required
def create_call():
    d = request.json
    d["caller_id"] = session.get("active_character_id")
    return jsonify(api.handle("emergency.create", d))

@app.route("/api/emergency/update", methods=["POST"])
@login_required
def update_call():
    d = request.json
    d["responder_id"] = session.get("active_character_id")
    return jsonify(api.handle("emergency.update", d))

# ─── Fraktionen API ────────────────────────────────────

@app.route("/api/factions/<faction_id>/members")
@login_required
def faction_members(faction_id):
    return jsonify(api.handle("faction.members", {"faction_id": faction_id}))

@app.route("/api/factions/announce", methods=["POST"])
@login_required
def faction_announce():
    d = request.json
    d["leader_character_id"] = session.get("active_character_id")
    return jsonify(api.handle("faction.announce", d))

# ─── News API ──────────────────────────────────────────

@app.route("/api/news")
def get_news():
    limit = int(request.args.get("limit", 20))
    return jsonify(api.handle("rp.news", {"limit": limit}))

@app.route("/api/news/publish", methods=["POST"])
@login_required
def publish_news():
    d = request.json
    d["author_character_id"] = session.get("active_character_id")
    d["is_admin"] = session.get("role") in ("admin", "superadmin")
    return jsonify(api.handle("rp.publish_news", d))

# ─── Fahndung API ──────────────────────────────────────

@app.route("/api/wanted")
def get_wanted():
    return jsonify(api.handle("police.active_posters", {}))

# ─── Shop API ──────────────────────────────────────────

@app.route("/api/shops/buy", methods=["POST"])
@login_required
def shop_buy():
    d = request.json
    d["buyer_character_id"] = session.get("active_character_id")
    return jsonify(api.handle("shop.buy", d))

# ─── Admin API ─────────────────────────────────────────

@app.route("/api/admin/accounts/search")
@login_required
def admin_search_accounts():
    if session.get("role") not in ("mod", "admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    q = request.args.get("q", "")
    return jsonify(api.handle("account.search", {"query": q}))

@app.route("/api/admin/accounts/filter")
@login_required
def admin_filter_accounts():
    if session.get("role") not in ("mod", "admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    banned = request.args.get("banned")
    has_warns = request.args.get("has_warns")
    new_only = request.args.get("new_only", "false") == "true"
    payload = {"new_only": new_only}
    if banned is not None:
        payload["banned"] = banned == "true"
    if has_warns is not None:
        payload["has_warns"] = has_warns == "true"
    return jsonify(api.handle("account.filter", payload))

@app.route("/api/admin/moderation/add", methods=["POST"])
@login_required
def admin_add_moderation():
    if session.get("role") not in ("mod", "admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json
    d["issued_by"] = session["account_id"]
    return jsonify(api.handle("mod.add", d))

@app.route("/api/admin/moderation/log/<account_id>")
@login_required
def admin_mod_log(account_id):
    if session.get("role") not in ("mod", "admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    return jsonify(api.handle("mod.log", {"account_id": account_id}))

@app.route("/api/admin/account/reset_password", methods=["POST"])
@login_required
@rate_limit("30 per hour")
def admin_reset_password():
    """Admin setzt das Passwort eines Spielers zurück."""
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Nur Admins dürfen Passwörter zurücksetzen"}), 403
    d = request.json or {}
    target_id = d.get("account_id", "").strip()
    new_password = d.get("new_password", "").strip()
    if not target_id or not new_password:
        return jsonify({"ok": False, "error": "account_id und new_password sind Pflichtfelder"})
    if len(new_password) < 6:
        return jsonify({"ok": False, "error": "Neues Passwort muss mind. 6 Zeichen haben"})
    # Mods dürfen kein Passwort zurücksetzen (nur Admin+)
    # Super Admin darf alle; Admin darf nur normale Spieler (nicht andere Admins)
    from models.db import get_by_id, update
    from managers.account_manager import hash_password
    target = get_by_id("accounts", target_id)
    if not target:
        return jsonify({"ok": False, "error": "Account nicht gefunden"})
    if session.get("role") == "admin" and target["role"] in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Admins dürfen keine anderen Admin-Accounts zurücksetzen"})
    update("accounts", target_id, {"password_hash": hash_password(new_password)})
    # Intern loggen
    from models.models import ModerationEntry
    from models.db import insert
    entry = ModerationEntry(
        account_id=target_id,
        action="note",
        reason=f"Passwort durch Admin zurückgesetzt (von: {session['account_id']})",
        issued_by=session["account_id"]
    )
    insert("moderation", entry.to_dict())
    return jsonify({"ok": True, "data": "Passwort erfolgreich zurückgesetzt"})

@app.route("/api/admin/economy/adjust", methods=["POST"])
@login_required
def admin_economy_adjust():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json
    d["admin_id"] = session["account_id"]
    return jsonify(api.handle("economy.admin_adjust", d))

@app.route("/api/admin/economy/bank_lock", methods=["POST"])
@login_required
def admin_bank_lock():
    if session.get("role") not in ("superadmin",):
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    d = request.json
    d["superadmin_id"] = session["account_id"]
    return jsonify(api.handle("economy.bank_lock", d))

@app.route("/api/admin/character/kill", methods=["POST"])
@login_required
def admin_kill_char():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json
    d["admin_id"] = session["account_id"]
    return jsonify(api.handle("character.kill", d))

@app.route("/api/admin/rp/log_event", methods=["POST"])
@login_required
def admin_log_event():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json
    d["admin_id"] = session["account_id"]
    return jsonify(api.handle("rp.log_event", d))

@app.route("/api/admin/stats")
@login_required
def admin_stats():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    return jsonify(api.handle("rp.stats", {}))

@app.route("/api/admin/server/settings", methods=["GET"])
@login_required
def server_settings_get():
    return jsonify(api.handle("server.settings", {}))

@app.route("/api/admin/server/settings", methods=["POST"])
@login_required
def server_settings_update():
    if session.get("role") != "superadmin":
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    d = request.json
    d["superadmin_id"] = session["account_id"]
    return jsonify(api.handle("server.update", d))

@app.route("/api/admin/server/maintenance", methods=["POST"])
@login_required
def server_maintenance():
    if session.get("role") != "superadmin":
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    d = request.json
    d["superadmin_id"] = session["account_id"]
    return jsonify(api.handle("server.maintenance", d))

@app.route("/api/admin/server/announce", methods=["POST"])
@login_required
def server_announce():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json
    d["superadmin_id"] = session["account_id"]
    return jsonify(api.handle("server.announce", d))

@app.route("/api/admin/factions/create", methods=["POST"])
@login_required
def admin_create_faction():
    if session.get("role") != "superadmin":
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    d = request.json
    d["superadmin_id"] = session["account_id"]
    return jsonify(api.handle("faction.create", d))

@app.route("/api/admin/account/set_role", methods=["POST"])
@login_required
def admin_set_role():
    if session.get("role") != "superadmin":
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    d = request.json
    d["superadmin_id"] = session["account_id"]
    return jsonify(api.handle("account.set_role", d))

@app.route("/api/admin/items/create", methods=["POST"])
@login_required
def admin_create_item():
    if session.get("role") != "superadmin":
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    d = request.json
    d["superadmin_id"] = session["account_id"]
    return jsonify(api.handle("item.create_global", d))

@app.route("/api/admin/items")
@login_required
def admin_list_items():
    return jsonify(api.handle("item.global_list", {}))

@app.route("/api/admin/shops/activate", methods=["POST"])
@login_required
def admin_activate_shop():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json
    d["admin_id"] = session["account_id"]
    return jsonify(api.handle("shop.activate", d))

@app.route("/api/admin/wanted/issue", methods=["POST"])
@login_required
def admin_issue_wanted():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json
    d["admin_id"] = session["account_id"]
    return jsonify(api.handle("rp.issue_wanted", d))


# ─── Profil API ────────────────────────────────────────

@app.route("/api/account/profile")
@login_required
def get_profile():
    from models.db import get_by_id
    acc = get_by_id("accounts", session["account_id"])
    if not acc:
        return jsonify({"ok": False, "error": "Account nicht gefunden"})
    # Passwort-Hash nie rausschicken
    acc.pop("password_hash", None)
    return jsonify({"ok": True, "data": acc})

@app.route("/api/account/profile", methods=["POST"])
@login_required
def update_profile():
    from models.db import update
    d = request.json or {}
    allowed = {}
    if "bio" in d:
        allowed["bio"] = str(d["bio"])[:500]
    if "profile_picture" in d:
        allowed["profile_picture"] = str(d["profile_picture"])[:300]
    update("accounts", session["account_id"], allowed)
    return jsonify({"ok": True, "data": "Profil aktualisiert"})

# ─── Inventar API ──────────────────────────────────────

@app.route("/api/inventory")
@login_required
def get_inventory():
    char_id = session.get("active_character_id")
    if not char_id:
        return jsonify({"ok": False, "error": "Kein aktiver Charakter"})
    return jsonify(api.handle("item.inventory", {"character_id": char_id}))

@app.route("/api/inventory/trade", methods=["POST"])
@login_required
def trade_item():
    char_id = session.get("active_character_id")
    if not char_id:
        return jsonify({"ok": False, "error": "Kein aktiver Charakter"})
    d = request.json or {}
    return jsonify(api.handle("item.trade", {
        "item_id": d.get("item_id", ""),
        "from_character_id": char_id,
        "to_character_id": d.get("to_character_id", ""),
        "price": d.get("price", 0.0)
    }))

# ─── Notruf Notiz API ──────────────────────────────────

@app.route("/api/emergency/note", methods=["POST"])
@login_required
def add_emergency_note():
    d = request.json or {}
    return jsonify(api.handle("emergency.note", {
        "call_id": d.get("call_id", ""),
        "note": d.get("note", "")
    }))

@app.route("/api/emergency/false_alarm", methods=["POST"])
@login_required
def mark_false_alarm():
    d = request.json or {}
    return jsonify(api.handle("emergency.false_alarm", {
        "call_id": d.get("call_id", ""),
        "account_id": session["account_id"]
    }))

# ─── Admin: Item spawnen ────────────────────────────────

@app.route("/api/admin/items/spawn", methods=["POST"])
@login_required
def admin_spawn_item():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json or {}
    d["admin_id"] = session["account_id"]
    return jsonify(api.handle("item.spawn", d))

# ─── Admin: Events ─────────────────────────────────────

@app.route("/api/admin/server/event", methods=["POST"])
@login_required
def server_event():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json or {}
    d["superadmin_id"] = session["account_id"]
    action = "server.event_start" if d.get("active") else "server.event_end"
    return jsonify(api.handle(action, d))

# ─── Admin: Scheduler manuell ──────────────────────────

@app.route("/api/admin/scheduler/run", methods=["POST"])
@login_required
def run_scheduler():
    if session.get("role") != "superadmin":
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    d = request.json or {}
    action = d.get("action", "all")
    if action == "tax":
        return jsonify(api.handle("economy.wealth_tax", {
            "superadmin_id": session["account_id"],
            "rate_percent": d.get("rate_percent", 5.0)
        }))
    elif action == "salaries":
        return jsonify(api.handle("economy.force_salaries", {
            "superadmin_id": session["account_id"]
        }))
    return jsonify(api.handle("scheduler.run", {}))

# ─── Admin: Gesetze setzen ─────────────────────────────

@app.route("/api/admin/server/laws", methods=["POST"])
@login_required
def set_laws():
    if session.get("role") != "superadmin":
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    d = request.json or {}
    d["superadmin_id"] = session["account_id"]
    return jsonify(api.handle("server.set_laws", d))

# ─── Admin: Charakter Reputation & Führerschein ────────

@app.route("/api/admin/character/reputation", methods=["POST"])
@login_required
def admin_character_reputation():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json or {}
    return jsonify(api.handle("character.reputation", d))

@app.route("/api/admin/character/drivers_license", methods=["POST"])
@login_required
def admin_drivers_license():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"ok": False, "error": "Keine Berechtigung"}), 403
    d = request.json or {}
    return jsonify(api.handle("character.drivers_license", d))

# ─── Admin: Löschanträge ───────────────────────────────

@app.route("/api/admin/account/confirm_delete", methods=["POST"])
@login_required
def admin_confirm_delete():
    if session.get("role") != "superadmin":
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    d = request.json or {}
    return jsonify(api.handle("account.confirm_delete", {
        "account_id": d.get("account_id"),
        "superadmin_id": session["account_id"]
    }))

@app.route("/api/admin/account/pending_deletes")
@login_required
def admin_pending_deletes():
    if session.get("role") != "superadmin":
        return jsonify({"ok": False, "error": "Nur Super Admin"}), 403
    from models.db import load_all
    accs = load_all("accounts")
    pending = [a for a in accs if a.get("pending_delete")]
    for a in pending:
        a.pop("password_hash", None)
    return jsonify({"ok": True, "data": pending})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = not IS_PRODUCTION
    if IS_PRODUCTION:
        print("🚀 RP-System startet im PRODUCTION-Modus")
        print(f"   → Besser: gunicorn -w 4 -b 0.0.0.0:{port} app:app")
    else:
        print(f"🚀 RP-System startet im DEV-Modus auf http://localhost:{port}")
    app.run(debug=debug, host="0.0.0.0", port=port)
