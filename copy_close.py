import os
import time
import json
import hmac
import hashlib
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
BASE_URL = "https://apiv2.thetruetrade.io"

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
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read() or b"{}")
    except Exception:
        return None

def get_active_users():
    url = f"{SUPABASE_URL}/rest/v1/copy_traders?is_active=eq.true&select=api_key,api_secret"
    req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except:
        return []

def main():
    print("⏹ شروع بستن معاملات...")
    users = get_active_users()
    for user in users:
        print("در حال بستن معاملات کاربر...")
        # دستور بستن همه پوزیشن‌ها
        res = request("POST", "/futures/positions/close-all", user["api_key"], user["api_secret"])
        if res: print("✅ بسته شد.")
        time.sleep(1)

if __name__ == "__main__":
    main()
