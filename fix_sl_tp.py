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
# ۲. توابع API (مشابه کد قبلی)
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
    except Exception as e:
        print(f"خطا در {method} {uri}: {e}")
        return None

def get_active_users():
    url = f"{DB_URL}/rest/v1/copy_traders?is_active=eq.true&select=api_key,api_secret"
    req = urllib.request.Request(url, headers={"apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except Exception:
        return []

# ==========================================
# ۳. اجرای تعمیر TP/SL برای همه کاربران
# ==========================================
def main():
    print("🔧 شروع تعمیر TP/SL برای تمام کاربران...")
    
    # ۱. خواندن پوزیشن‌های باز حساب اصلی
    master_positions = request("GET", f"{FUTURES_PREFIX}/positions", MASTER_KEY, MASTER_SECRET)
    if not master_positions: return

    items = master_positions.get("items", []) if isinstance(master_positions, dict) else master_positions
    master_open = [p for p in items if p.get("status") == "OPENED" and p.get("isActive") == True]
    
    if not master_open:
        print("حساب اصلی پوزیشن بازی ندارد.")
        return

    users = get_active_users()
    if not users: return

    # ۲. برای هر پوزیشن اصلی، TP/SL رو روی کاربران اعمال کن
    for m_pos in master_open:
        symbol = m_pos["symbol"]
        master_sl = m_pos.get("stopLoss")
        master_tp = m_pos.get("takeProfit")
        
        if not master_sl or not master_tp:
            print(f"⚠️ معامله {symbol} در حساب اصلی TP/SL ندارد. رد شد.")
            continue
            
        print(f"\n--- تعمیر {symbol} (SL: {master_sl}, TP: {master_tp}) ---")
        
        for user in users:
            # پیدا کردن پوزیشن باز کاربر روی همون نماد
            user_positions = request("GET", f"{FUTURES_PREFIX}/positions", user["api_key"], user["api_secret"])
            if not user_positions: continue
            
            u_items = user_positions.get("items", []) if isinstance(user_positions, dict) else user_positions
            target = next((p for p in u_items if p.get("symbol") == symbol and p.get("status") == "OPENED"), None)
            
            if target:
                pos_id = target["id"]
                # تلاش برای تنظیم TP/SL
                body = {
                    "stopLoss": str(master_sl),
                    "takeProfit": str(master_tp),
                    "stopLossOrderType": "STOP_MARKET",
                    "takeProfitOrderType": "TAKE_PROFIT_MARKET"
                }
                res = request("PATCH", f"{FUTURES_PREFIX}/positions/{pos_id}/tpsl", user["api_key"], user["api_secret"], body)
                if res is not None:
                    print(f"✅ TP/SL برای کاربر {user['api_key'][:5]} تنظیم شد.")
                else:
                    print(f"❌ خطا در تنظیم برای {user['api_key'][:5]}.")

if __name__ == "__main__":
    main()
