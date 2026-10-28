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
    except urllib.error.HTTPError as e:
        print(f"❌ خطای HTTP {e.code} برای {api_key[:5]}: {e.read().decode(errors='replace')}")
        return None
    except Exception as e:
        print(f"❌ خطای شبکه برای {api_key[:5]}: {e}")
        return None

def get_active_users():
    url = f"{DB_URL}/rest/v1/copy_traders?is_active=eq.true&select=api_key,api_secret"
    req = urllib.request.Request(url, headers={"apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"❌ خطا در خواندن دیتابیس: {e}")
        return []

def update_stats_in_db(api_key, balance, pos_count, pnl, has_tpsl):
    delete_url = f"{DB_URL}/rest/v1/admin_stats?api_key=eq.{api_key}"
    del_headers = {"apikey": DB_KEY, "Authorization": f"Bearer {DB_KEY}"}
    try:
        req_del = urllib.request.Request(delete_url, headers=del_headers, method="DELETE")
        urllib.request.urlopen(req_del)
    except:
        pass

    url = f"{DB_URL}/rest/v1/admin_stats"
    headers = {
        "apikey": DB_KEY, 
        "Authorization": f"Bearer {DB_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "api_key": api_key,
        "balance": balance,
        "open_positions_count": pos_count,
        "total_unrealized_pnl": pnl,
        "has_tpsl": has_tpsl
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            pass
    except Exception as e:
        print(f"❌ خطا در ذخیره اطلاعات {api_key[:5]}: {e}")

# ==========================================
# ۳. اجرای اصلی
# ==========================================
def main():
    print("📊 شروع بروزرسانی آمار ادمین...")
    users = get_active_users()
    
    if not users:
        print("⚠️ هیچ کاربری در دیتابیس پیدا نشد.")
        return
        
    print(f"👥 تعداد {len(users)} کاربر برای بررسی پیدا شد.")
    
    for u in users:
        api_key = u["api_key"]
        api_secret = u["api_secret"]
        
        # ۱. گرفتن موجودی
        assets = request("GET", f"{FUTURES_PREFIX}/assets", api_key, api_secret)
        
        # 🌟 اگر خطا داد (None برگشت)، از این کاربر رد شو و اطلاعات غلط ذخیره نکن
        if assets is None:
            print(f"⚠️ رد کردن کاربر {api_key[:5]} به دلیل خطا در دریافت اطلاعات.")
            continue
            
        balance = 0.0
        if "summary" in assets:
            balance = float(assets["summary"].get("totalAssets", 0))
            
        # ۲. گرفتن پوزیشن‌ها
        positions = request("GET", f"{FUTURES_PREFIX}/positions", api_key, api_secret)
        
        if positions is None:
            print(f"⚠️ رد کردن کاربر {api_key[:5]} به دلیل خطا در دریافت پوزیشن‌ها.")
            continue
            
        pos_count = 0
        total_pnl = 0.0
        has_tpsl = False
        
        items = positions.get("items", [])
        open_pos = [p for p in items if p.get("status") == "OPENED"]
        pos_count = len(open_pos)
        
        for p in open_pos:
            total_pnl += float(p.get("unrealizedPnL") or 0)
            if p.get("stopLoss") and p.get("takeProfit"):
                has_tpsl = True
                
        print(f"👤 کاربر {api_key[:5]}: موجودی={balance:.2f}$, پوزیشن={pos_count}, PnL={total_pnl:.2f}$, TP/SL={has_tpsl}")
        
        # ۳. ذخیره در دیتابیس
        update_stats_in_db(api_key, balance, pos_count, total_pnl, has_tpsl)
        time.sleep(1)

if __name__ == "__main__":
    main()
