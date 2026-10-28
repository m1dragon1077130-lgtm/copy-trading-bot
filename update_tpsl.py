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
            raw = resp.read()
            result = json.loads(raw) if raw else {}
            if isinstance(result, dict) and "error" in result:
                print(f"⚠️ خطای صرافی: {result}")
                return None
            return result
    except urllib.error.HTTPError as e:
        print(f"خطای HTTP {e.code} برای {api_key[:5]}: {e.read().decode(errors='replace')}")
        return None
    except Exception as e:
        print(f"خطا برای {api_key[:5]}: {e}")
        return None

def get_active_users():
    url = f"{DB_URL}/rest/v1/copy_traders?is_active=eq.true&select=api_key,api_secret"
    req = urllib.request.Request(url, headers={"apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"خطا در خواندن دیتابیس: {e}")
        return []

# ==========================================
# ۳. منطق بروزرسانی TP/SL
# ==========================================
def update_user_tpsl(master_pos, user_key, user_secret):
    symbol = master_pos["symbol"]
    side = master_pos["side"]
    master_entry = float(master_pos["entryPrice"])
    
    master_sl = master_pos.get("stopLoss")
    master_tp = master_pos.get("takeProfit")
    
    if not master_sl or not master_tp:
        print(f"⚠️ معامله مستر {symbol} TP/SL معتبر ندارد.")
        return
        
    # محاسبه درصدها از روی معامله مستر
    sl_pct = abs((float(master_sl) - master_entry) / master_entry)
    tp_pct = abs((float(master_tp) - master_entry) / master_entry)
    
    # پیدا کردن معامله باز کاربر روی همون نماد
    user_positions = request("GET", f"{FUTURES_PREFIX}/positions", user_key, user_secret)
    if not user_positions: return
    
    items = user_positions.get("items", []) if isinstance(user_positions, dict) else user_positions
    target = next((p for p in items if p.get("symbol") == symbol and p.get("status") == "OPENED"), None)
    
    if not target:
        print(f"ℹ️ کاربر {user_key[:5]} پوزیشن بازی روی {symbol} ندارد.")
        return
        
    pos_id = target["id"]
    user_entry = float(target["entryPrice"])
    
    # محاسبه SL و TP جدید بر اساس درصدهای مستر و قیمت ورود کاربر
    if side == "LONG":
        new_sl = round(user_entry * (1 - sl_pct), 8)
        new_tp = round(user_entry * (1 + tp_pct), 8)
    else:
        new_sl = round(user_entry * (1 + sl_pct), 8)
        new_tp = round(user_entry * (1 - tp_pct), 8)
        
    print(f"⏳ آپدیت {symbol} برای {user_key[:5]} (SL: {new_sl}, TP: {new_tp})...")
    
    body = {
        "stopLoss": str(new_sl),
        "takeProfit": str(new_tp),
        "stopLossOrderType": "STOP_MARKET",
        "takeProfitOrderType": "TAKE_PROFIT_MARKET"
    }
    
    res = request("PATCH", f"{FUTURES_PREFIX}/positions/{pos_id}/tpsl", user_key, user_secret, body)
    if res is not None:
        print(f"✅ TP/SL کاربر {user_key[:5]} بروزرسانی شد.")
    else:
        print(f"❌ خطا در بروزرسانی {user_key[:5]}.")

# ==========================================
# ۴. اجرای اصلی
# ==========================================
def main():
    print("🔄 شروع بروزرسانی TP/SL...")
    
    # ۱. خواندن پوزیشن‌های باز مستر
    master_positions = request("GET", f"{FUTURES_PREFIX}/positions", MASTER_KEY, MASTER_SECRET)
    if not master_positions: return

    items = master_positions.get("items", []) if isinstance(master_positions, dict) else master_positions
    master_open = [p for p in items if p.get("status") == "OPENED" and p.get("isActive") == True]
    
    if not master_open:
        print("حساب اصلی پوزیشن بازی ندارد.")
        return

    print(f"تعداد {len(master_open)} پوزیشن باز در حساب اصلی پیدا شد.")
    
    users = get_active_users()
    print(f"تعداد {len(users)} کاربر برای بروزرسانی پیدا شد.")
    if len(users) == 0: return

    # ۲. برای هر پوزیشن مستر، TP/SL کاربران رو آپدیت کن
    for m_pos in master_open:
        print(f"\n--- بروزرسانی {m_pos['symbol']} ---")
        for user in users:
            update_user_tpsl(m_pos, user["api_key"], user["api_secret"])
            time.sleep(1)

if __name__ == "__main__":
    main()
