import os
import time
import json
import hmac
import hashlib
import urllib.request
import urllib.error

# ==========================================
# ۱. تنظیمات
# ==========================================
MASTER_KEY = os.environ.get("MASTER_API_KEY")
MASTER_SECRET = os.environ.get("MASTER_API_SECRET")
DB_URL = os.environ.get("SUPABASE_URL")
DB_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

BASE_URL = "https://apiv2.thetruetrade.io"
FUTURES_PREFIX = "/futures"

# تنظیمات کپی‌تریدینگ
FOLLOWER_MARGIN = "1.0"   # مارجین هر کاربر (۱ دلار)
STOP_LOSS_PCT = 0.01      # حد ضرر ۱ درصد
TAKE_PROFIT_PCT = 0.05    # حد سود ۵ درصد

# ==========================================
# ۲. توابع API
# ==========================================
def sign(secret, timestamp, method, uri):
    payload = f"{timestamp}{method.upper()}{uri}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def request(method, uri, api_key, api_secret, body=None):
    timestamp = str(int(time.time() * 1000))
    signature = sign(api_secret, timestamp, method, uri)
    headers = {
        "X-API-Key": api_key, "X-Timestamp": timestamp, "X-Signature": signature,
        "Accept": "application/json", "User-Agent": "Mozilla/5.0"
    }
    data = json.dumps(body).encode() if body else None
    if data: headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(BASE_URL + uri, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        print(f"خطای HTTP {e.code} برای {api_key[:5]}: {e.read().decode(errors='replace')}")
        return None
    except Exception as e:
        print(f"خطا برای {api_key[:5]}: {e}")
        return None

def get_active_users():
    url = f"{DB_URL}/rest/v1/copy_traders?is_active=eq.true&select=api_key,api_secret"
    req = urllib.request.Request(url, headers={
        "apikey": DB_KEY,
        "Authorization": f"Bearer {DB_KEY}"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"خطا در خواندن دیتابیس: {e}")
        return []

# ==========================================
# ۳. توابع کمکی برای هر کاربر
# ==========================================
def open_trade_for_user(user_key, user_secret, symbol, side, leverage):
    print(f"⏳ ارسال سفارش برای کاربر {user_key[:5]}...")
    
    order_body = {
        "symbol": symbol,
        "side": side,
        "tradeType": "MARKET",
        "leverage": leverage,
        "cost": FOLLOWER_MARGIN
    }
    
    response = request("POST", f"{FUTURES_PREFIX}/positions", user_key, user_secret, order_body)
    if response is None:
        print(f"❌ سفارش برای کاربر {user_key[:5]} ثبت نشد.")
        return False
        
    print(f"✅ سفارش برای کاربر {user_key[:5]} ارسال شد. در حال جستجوی پوزیشن...")
    time.sleep(3) # صبر برای ثبت پوزیشن
    
    # پیدا کردن پوزیشن باز
    positions = request("GET", f"{FUTURES_PREFIX}/positions", user_key, user_secret)
    if positions is None:
        return False
        
    items = positions.get("items", []) if isinstance(positions, dict) else positions
    target_position = None
    for p in items:
        if p.get("symbol") == symbol and p.get("status") == "OPENED" and p.get("isActive") == True:
            if target_position is None or p.get("createdAt", "") > target_position.get("createdAt", ""):
                target_position = p
                
    if target_position is None:
        print(f"❌ پوزیشن باز برای کاربر {user_key[:5]} پیدا نشد.")
        return False
        
    position_id = target_position.get("id")
    entry_price = float(target_position.get("entryPrice"))
    print(f"✅ پوزیشن کاربر {user_key[:5]} پیدا شد (ID: {position_id}, قیمت: {entry_price})")
    
    # تنظیم TP/SL
    if side == "LONG":
        sl_price = round(entry_price * (1 - STOP_LOSS_PCT), 2)
        tp_price = round(entry_price * (1 + TAKE_PROFIT_PCT), 2)
    else:
        sl_price = round(entry_price * (1 + STOP_LOSS_PCT), 2)
        tp_price = round(entry_price * (1 - TAKE_PROFIT_PCT), 2)
        
    tpsl_body = {
        "stopLoss": str(sl_price),
        "takeProfit": str(tp_price),
        "stopLossOrderType": "STOP_MARKET",
        "takeProfitOrderType": "TAKE_PROFIT_MARKET"
    }
    
    tpsl_response = request("PATCH", f"{FUTURES_PREFIX}/positions/{position_id}/tpsl", user_key, user_secret, tpsl_body)
    if tpsl_response is not None:
        print(f"✅ TP/SL برای کاربر {user_key[:5]} تنظیم شد.")
        return True
    else:
        print(f"⚠️ خطا در تنظیم TP/SL برای کاربر {user_key[:5]}.")
        return False

# ==========================================
# ۴. اجرای اصلی
# ==========================================
def main():
    print("🚀 شروع کپی معاملات (نسخه نهایی)...")
    
    # ۱. خواندن پوزیشن‌های باز حساب اصلی
    master_positions = request("GET", f"{FUTURES_PREFIX}/positions", MASTER_KEY, MASTER_SECRET)
    if not master_positions:
        print("خطا در خواندن پوزیشن‌های حساب اصلی.")
        return

    items = master_positions.get("items", []) if isinstance(master_positions, dict) else master_positions
    open_items = [p for p in items if p.get("status") == "OPENED" and p.get("isActive") == True]
    
    if not open_items:
        print("حساب اصلی هیچ پوزیشن بازی ندارد.")
        return

    print(f"تعداد {len(open_items)} پوزیشن باز در حساب اصلی پیدا شد.")
    
    # ۲. گرفتن لیست کاربران
    users = get_active_users()
    print(f"تعداد {len(users)} کاربر برای کپی پیدا شد.")
    
    if len(users) == 0:
        print("هیچ کاربری برای کپی پیدا نشد.")
        return

    # ۳. کپی کردن معاملات برای هر کاربر
    for p in open_items:
        symbol = p["symbol"]
        side = p["side"]
        leverage = p["leverage"]
        
        print(f"\n--- کپی کردن {symbol} {side} ---")
        for user in users:
            open_trade_for_user(user["api_key"], user["api_secret"], symbol, side, leverage)
            time.sleep(1) # فاصله بین کاربران

if __name__ == "__main__":
    main()
