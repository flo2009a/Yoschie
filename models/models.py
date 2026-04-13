"""
RP-System Datenmodelle — alle Klassen für JSON-Serialisierung
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal
from datetime import datetime
import uuid


def new_id() -> str:
    return str(uuid.uuid4())[:8]

def now() -> str:
    return datetime.now().isoformat()


# ─────────────────────────────────────────────
# ACCOUNT & PROFIL
# ─────────────────────────────────────────────

@dataclass
class Account:
    roblox_name: str
    password_hash: str
    role: Literal["player", "mod", "admin", "superadmin"] = "player"
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)
    last_login: str = field(default_factory=now)
    bio: str = ""
    profile_picture: str = ""          # URL oder base64
    warn_count: int = 0                # nur Anzahl sichtbar für Spieler
    character_ids: list[str] = field(default_factory=list)   # max 3
    is_banned: bool = False
    ban_expires: Optional[str] = None  # ISO-Datum oder None = permanent
    is_deleted: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────
# CHARAKTER
# ─────────────────────────────────────────────

@dataclass
class MedicalRecord:
    notes: list[str] = field(default_factory=list)
    blood_type: str = ""
    allergies: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=now)

    def to_dict(self): return asdict(self)


@dataclass
class Character:
    account_id: str
    name: str
    age: int
    appearance: str
    job: str
    backstory: str
    faction_id: Optional[str]
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)
    is_active: bool = True
    is_dead: bool = False
    profile_picture: str = ""
    reputation: int = 0                # positiv / negativ
    medical_record: MedicalRecord = field(default_factory=MedicalRecord)
    vehicle_licenses: list[str] = field(default_factory=list)  # erlaubte Fahrzeugklassen
    drivers_license: Literal["valid", "revoked", "never"] = "never"
    balance: float = 0.0
    black_market_balance: float = 0.0  # versteckt, nur kriminelle Fraktionen
    inventory: list[str] = field(default_factory=list)  # Item-IDs

    def to_dict(self) -> dict:
        d = asdict(self)
        d["medical_record"] = self.medical_record.to_dict()
        return d


# ─────────────────────────────────────────────
# GELD & WIRTSCHAFT
# ─────────────────────────────────────────────

@dataclass
class Transaction:
    sender_id: str        # Charakter-ID oder "system"
    receiver_id: str
    amount: float
    note: str = ""
    id: str = field(default_factory=new_id)
    timestamp: str = field(default_factory=now)
    tx_type: Literal["transfer", "salary", "tax", "admin", "shop", "black_market"] = "transfer"

    def to_dict(self): return asdict(self)


@dataclass
class EconomySettings:
    tax_rate: float = 0.0              # Prozent (0–100)
    salary_interval: Literal["daily", "weekly"] = "weekly"
    starting_capital: float = 500.0
    bank_locked: bool = False          # Bankraub-Event

    def to_dict(self): return asdict(self)


# ─────────────────────────────────────────────
# INVENTAR & ITEMS
# ─────────────────────────────────────────────

@dataclass
class Item:
    name: str
    category: Literal["weapon", "vehicle", "clothing", "equipment", "food", "document"]
    rarity: Literal["common", "uncommon", "rare", "legendary"] = "common"
    condition: Literal["new", "used", "damaged", "broken"] = "new"
    id: str = field(default_factory=new_id)
    description: str = ""
    owner_character_id: Optional[str] = None
    expires_at: Optional[str] = None   # ISO-Datum für Lebensmittel etc.
    requires_license: bool = False     # z. B. Waffenschein
    is_stolen: bool = False
    is_vehicle_key: bool = False       # Fahrzeugschlüssel

    def to_dict(self): return asdict(self)


# ─────────────────────────────────────────────
# NOTRUF-SYSTEM
# ─────────────────────────────────────────────

@dataclass
class EmergencyCall:
    caller_character_id: Optional[str]  # None = anonym
    location: str
    description: str
    call_type: Literal["police", "fire", "ems", "all"]
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)
    status: Literal["open", "accepted", "in_progress", "closed"] = "open"
    assigned_to: list[str] = field(default_factory=list)  # Charakter-IDs
    notes: list[str] = field(default_factory=list)
    is_false_alarm: bool = False
    closed_at: Optional[str] = None
    anonymous: bool = False

    def to_dict(self): return asdict(self)


# ─────────────────────────────────────────────
# SHOP-SYSTEM
# ─────────────────────────────────────────────

@dataclass
class ShopItem:
    global_item_id: str
    stock: int = 0
    buy_price: float = 0.0            # Einkaufspreis vom Admin
    sell_price: float = 0.0           # Verkaufspreis an Spieler
    discount_percent: float = 0.0

    def to_dict(self): return asdict(self)


@dataclass
class Shop:
    name: str
    owner_character_id: str
    category: Literal["food", "weapons", "vehicles", "clothing", "medicine", "black_market"]
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)
    is_active: bool = False            # muss von Admin aktiviert werden
    is_open: bool = False              # Öffnungszeiten-RP
    balance: float = 0.0
    inventory: list[ShopItem] = field(default_factory=list)
    allowed_faction_ids: list[str] = field(default_factory=list)  # Schwarzmarkt
    ratings: list[dict] = field(default_factory=list)  # {"character_id", "rating": 1-5, "comment"}
    transaction_log: list[str] = field(default_factory=list)  # Transaction-IDs

    def to_dict(self) -> dict:
        d = asdict(self)
        d["inventory"] = [i.to_dict() for i in self.inventory]
        return d


# ─────────────────────────────────────────────
# FRAKTIONEN
# ─────────────────────────────────────────────

@dataclass
class FactionRank:
    name: str
    level: int = 0                     # 0 = niedrigster
    permissions: list[str] = field(default_factory=list)

    def to_dict(self): return asdict(self)


@dataclass
class FactionMember:
    character_id: str
    rank_name: str
    joined_at: str = field(default_factory=now)

    def to_dict(self): return asdict(self)


@dataclass
class Faction:
    name: str
    description: str
    color: str                         # Hex-Farbe
    faction_type: Literal["legal", "illegal"]
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)
    logo: str = ""
    leader_character_id: Optional[str] = None
    ranks: list[FactionRank] = field(default_factory=list)
    members: list[FactionMember] = field(default_factory=list)
    treasury: float = 0.0
    announcements: list[dict] = field(default_factory=list)
    owned_item_ids: list[str] = field(default_factory=list)
    headquarters: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ranks"] = [r.to_dict() for r in self.ranks]
        d["members"] = [m.to_dict() for m in self.members]
        return d


# ─────────────────────────────────────────────
# MODERATION
# ─────────────────────────────────────────────

@dataclass
class ModerationEntry:
    account_id: str
    action: Literal["warn", "kick", "ban", "unban", "note"]
    reason: str                        # intern, Spieler sieht dies NICHT
    issued_by: str                     # Account-ID des Mods/Admins
    id: str = field(default_factory=new_id)
    timestamp: str = field(default_factory=now)
    ban_expires: Optional[str] = None  # None = permanent bei ban
    is_active: bool = True             # false = aufgehoben

    def to_dict(self): return asdict(self)


# ─────────────────────────────────────────────
# RP-TOOLS & KOMMUNIKATION
# ─────────────────────────────────────────────

@dataclass
class RPEvent:
    title: str
    description: str
    involved_character_ids: list[str]
    created_by: str                    # Account-ID
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)

    def to_dict(self): return asdict(self)


@dataclass
class WantedNotice:
    character_id: str
    description: str
    reward: float
    issued_by: str                     # Account-ID
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)
    is_active: bool = True

    def to_dict(self): return asdict(self)


@dataclass
class CourtCase:
    defendant_character_id: str
    charges: str
    verdict: str
    sentence: str
    documented_by: str                 # Account-ID
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)

    def to_dict(self): return asdict(self)


@dataclass
class NewsArticle:
    title: str
    content: str
    author_character_id: str
    id: str = field(default_factory=new_id)
    published_at: str = field(default_factory=now)
    is_admin_post: bool = False

    def to_dict(self): return asdict(self)


@dataclass
class ServerSettings:
    server_name: str = "RP-Server"
    logo: str = ""
    description: str = ""
    rules: str = ""
    maintenance_mode: bool = False
    maintenance_message: str = "Wartung läuft..."
    economy: EconomySettings = field(default_factory=EconomySettings)
    laws: list[str] = field(default_factory=list)  # Strafkatalog-Einträge
    active_events: list[str] = field(default_factory=list)  # z. B. "bank_robbery"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["economy"] = self.economy.to_dict()
        return d
