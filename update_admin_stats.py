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

def request(method, uri, api_key, api_secret):
    timestamp = str(int(time.time() * 1000))
    signature = sign(api_secret, timestamp, method, uri)
    headers = {
        "X-API-Key": api_key, "X-Timestamp": timestamp, "X-Signature": signature,
        "Accept": "application/json", "User-Agent": "Mozilla/5.0"
    }
    req = urllib.request.Request(BASE_URL + uri, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read() or b"{}")
    except Exception:
        return None

def get_active_users():
    url = f"{DB_URL}/rest/v1/copy_traders?is_active=eq.true&select=api_key,api_secret"
    req = urllib.request.Request(url, headers={"apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except Exception:
        return []

def update_stats_in_db(api_key, balance, pos_count, pnl, has_tpsl):
    url = f"{DB_URL}/rest/v1/admin_stats"
    headers = {
        "apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    body = {
        "api_key": api_key,
        "balance": balance,
        "open_positions_count": pos_count,
        "total_unrealized_pnl": pnl,
        "has_tpsl": has_tpsl,
        "updated_at": "now()"
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            pass
    except Exception as e:
        print(f"خطا در ذخیره اطلاعات {api_key[:5]}: {e}")

# ==========================================
# ۳. اجرای اصلی
# ==========================================
def main():
    print("📊 شروع بروزرسانی آمار ادمین...")
    users = get_active_users()
    
    for u in users:
        api_key = u["api_key"]
        api_secret = u["api_secret"]
        
        assets = request("GET", f"{FUTURES_PREFIX}/assets", api_key, api_secret)
        balance = 0.0
        if assets and "summary" in assets:
            balance = float(assets["summary"].get("totalAssets", 0))
            
        positions = request("GET", f"{FUTURES_PREFIX}/positions", api_key, api_secret)
        pos_count = 0
        total_pnl = 0.0
        has_tpsl = False
        
        if positions:
            items = positions.get("items", [])
            open_pos = [p for p in items if p.get("status") == "OPENED"]
            pos_count = len(open_pos)
            
            for p in open_pos:
                total_pnl += float(p.get("unrealizedPnL") or 0)
                if p.get("stopLoss") and p.get("takeProfit"):
                    has_tpsl = True
                    
        print(f"👤 کاربر {api_key[:5]}: موجودی={balance}, پوزیشن={pos_count}, PnL={total_pnl}")
        update_stats_in_db(api_key, balance, pos_count, total_pnl, has_tpsl)
        time.sleep(1)

if __name__ == "__main__":
    main()
