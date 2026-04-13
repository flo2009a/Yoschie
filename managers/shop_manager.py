"""
Shop Manager
"""
from models.db import insert, update, get_by_id, find, load_all
from models.models import Shop, ShopItem, Transaction, now


def create_shop(name: str, owner_character_id: str, category: str) -> dict:
    shop = Shop(name=name, owner_character_id=owner_character_id, category=category)
    return insert("shops", shop.to_dict())


def admin_activate_shop(shop_id: str, admin_id: str, active: bool) -> dict:
    from models.db import get_by_id as gbi
    admin = gbi("accounts", admin_id)
    if not admin or admin["role"] not in ("admin", "superadmin"):
        raise PermissionError("Nur Admins dürfen Shops aktivieren.")
    return update("shops", shop_id, {"is_active": active})


def set_shop_open(shop_id: str, owner_character_id: str, is_open: bool) -> dict:
    shop = get_by_id("shops", shop_id)
    if not shop:
        raise ValueError("Shop nicht gefunden.")
    if shop["owner_character_id"] != owner_character_id:
        raise PermissionError("Nicht der Besitzer dieses Shops.")
    if not shop["is_active"]:
        raise PermissionError("Shop wurde noch nicht von Admin aktiviert.")
    return update("shops", shop_id, {"is_open": is_open})


def stock_item(shop_id: str, global_item_id: str, quantity: int, buy_price: float, sell_price: float) -> dict:
    shop = get_by_id("shops", shop_id)
    inventory = shop.get("inventory", [])
    for item in inventory:
        if item["global_item_id"] == global_item_id:
            item["stock"] += quantity
            return update("shops", shop_id, {"inventory": inventory})
    inventory.append(ShopItem(
        global_item_id=global_item_id,
        stock=quantity,
        buy_price=buy_price,
        sell_price=sell_price
    ).to_dict())
    return update("shops", shop_id, {"inventory": inventory})


def buy_item(shop_id: str, global_item_id: str, buyer_character_id: str) -> dict:
    shop = get_by_id("shops", shop_id)
    if not shop["is_open"]:
        raise PermissionError("Shop ist geschlossen.")

    # Fraktion-Check für Schwarzmarkt
    if shop["category"] == "black_market":
        char = get_by_id("characters", buyer_character_id)
        allowed = shop.get("allowed_faction_ids", [])
        if allowed and char.get("faction_id") not in allowed:
            raise PermissionError("Kein Zugang zu diesem Shop.")

    inventory = shop.get("inventory", [])
    for item in inventory:
        if item["global_item_id"] == global_item_id:
            if item["stock"] <= 0:
                raise ValueError("Artikel nicht mehr auf Lager.")

            price = round(item["sell_price"] * (1 - item.get("discount_percent", 0) / 100), 2)

            # Zahlung vom Charakter
            char = get_by_id("characters", buyer_character_id)
            if char["balance"] < price:
                raise ValueError("Nicht genug Guthaben.")

            update("characters", buyer_character_id, {"balance": round(char["balance"] - price, 2)})
            update("shops", shop_id, {"balance": round(shop["balance"] + price, 2)})
            item["stock"] -= 1

            # Item ins Inventar
            char_inv = char.get("inventory", [])
            char_inv.append(global_item_id)
            update("characters", buyer_character_id, {"inventory": char_inv})
            update("shops", shop_id, {"inventory": inventory})

            tx = Transaction(
                sender_id=buyer_character_id,
                receiver_id="shop:" + shop_id,
                amount=price,
                note=f"Kauf: {global_item_id}",
                tx_type="shop"
            )
            tx_record = insert("transactions", tx.to_dict())

            # Log
            log = shop.get("transaction_log", [])
            log.append(tx_record["id"])
            update("shops", shop_id, {"transaction_log": log})
            return tx_record

    raise ValueError("Artikel nicht im Shop.")


def withdraw_from_shop(shop_id: str, owner_character_id: str, amount: float) -> dict:
    shop = get_by_id("shops", shop_id)
    if shop["owner_character_id"] != owner_character_id:
        raise PermissionError("Nicht der Besitzer.")
    if shop["balance"] < amount:
        raise ValueError("Nicht genug Guthaben im Shop.")
    update("shops", shop_id, {"balance": round(shop["balance"] - amount, 2)})
    char = get_by_id("characters", owner_character_id)
    update("characters", owner_character_id, {"balance": round(char["balance"] + amount, 2)})
    tx = Transaction(
        sender_id="shop:" + shop_id,
        receiver_id=owner_character_id,
        amount=amount,
        note="Auszahlung aus Shop-Konto",
        tx_type="shop"
    )
    return insert("transactions", tx.to_dict())


def rate_shop(shop_id: str, buyer_character_id: str, rating: int, comment: str = "") -> dict:
    if not 1 <= rating <= 5:
        raise ValueError("Bewertung muss zwischen 1 und 5 liegen.")
    shop = get_by_id("shops", shop_id)
    ratings = shop.get("ratings", [])
    ratings.append({"character_id": buyer_character_id, "rating": rating, "comment": comment, "at": now()})
    return update("shops", shop_id, {"ratings": ratings})


def rob_shop(shop_id: str, admin_id: str) -> dict:
    """Admin-Event: Lager wird geleert."""
    admin = get_by_id("accounts", admin_id)
    if not admin or admin["role"] not in ("admin", "superadmin"):
        raise PermissionError("Nur Admins können Shops ausrauben.")
    shop = get_by_id("shops", shop_id)
    emptied = [dict(i, stock=0) for i in shop.get("inventory", [])]
    return update("shops", shop_id, {"inventory": emptied})
