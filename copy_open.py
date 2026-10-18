import os
import time
import json
import hmac
import hashlib
import urllib.request
import urllib.error

MASTER_KEY = os.environ.get("MASTER_API_KEY")
MASTER_SECRET = os.environ.get("MASTER_API_SECRET")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

BASE_URL = "https://apiv2.thetruetrade.io"

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
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read() or b"{}")
    except Exception as e:
        print(f"خطا در درخواست: {e}")
        return None

def get_active_users():
    url = f"{SUPABASE_URL}/rest/v1/copy_traders?is_active=eq.true&select=api_key,api_secret"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"خطا در خواندن دیتابیس: {e}")
        return []

def main():
    print("🚀 شروع کپی معاملات...")
    
    # ۱. خواندن پوزیشن‌های باز تو
    master_positions = request("GET", "/futures/positions", MASTER_KEY, MASTER_SECRET)
    if not master_positions:
        print("خطا در خواندن پوزیشن‌ها.")
        return

    # فیلتر کردن فقط پوزیشن‌هایی که واقعاً باز هستند
    items = master_positions.get("items", []) if isinstance(master_positions, dict) else master_positions
    open_items = [p for p in items if p.get("status") == "OPENED" and p.get("isActive") == True]
    
    if not open_items:
        print("حساب شما هیچ پوزیشن بازی ندارد.")
        return

    print(f"تعداد {len(open_items)} پوزیشن واقعاً باز پیدا شد.")
    
    # ۲. گرفتن لیست کاربران از Supabase
    users = get_active_users()
    print(f"تعداد {len(users)} کاربر برای کپی پیدا شد.")
    
    if len(users) == 0:
        print("هیچ کاربری برای کپی پیدا نشد. لطفا کلیدهای دیتابیس (Secrets) را چک کنید.")
        return

    # ۳. باز کردن معامله برای هر کاربر
    for p in open_items:
        symbol = p["symbol"]
        side = p["side"]
        leverage = p["leverage"]
        cost = "1.0" 
        
        for user in users:
            print(f"باز کردن {symbol} برای کاربر...")
            order = {
                "symbol": symbol, "side": side, "tradeType": "MARKET",
                "leverage": leverage, "cost": cost
            }
            res = request("POST", "/futures/positions", user["api_key"], user["api_secret"], order)
            if res:
                print("✅ موفق")
            time.sleep(1)

if __name__ == "__main__":
    main()
