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

def get_balance(api_key, api_secret):
    res = request("GET", f"{FUTURES_PREFIX}/assets", api_key, api_secret)
    if res and "summary" in res:
        return float(res["summary"].get("totalAssets", 0))
    return 0.0

# ==========================================
# ۳. منطق کپی برای هر کاربر
# ==========================================
def copy_trade_for_user(master_position, user_key, user_secret, master_balance):
    symbol = master_position["symbol"]
    side = master_position["side"]
    leverage = master_position["leverage"]
    master_entry = float(master_position["entryPrice"])
    
    # محاسبه درصد فاصله حد ضرر و سود از قیمت ورود مستر
    master_sl = master_position.get("stopLoss")
    master_tp = master_position.get("takeProfit")
    
    sl_pct = None
    tp_pct = None
    
    if master_sl and float(master_sl) > 0:
        sl_pct = abs((float(master_sl) - master_entry) / master_entry)
    if master_tp and float(master_tp) > 0:
        tp_pct = abs((float(master_tp) - master_entry) / master_entry)

    master_margin = float(master_position.get("initialMargin", 0))
    if master_balance <= 0:
        print("❌ موجودی حساب اصلی صفر است.")
        return
    
    risk_percent = master_margin / master_balance
    user_balance = get_balance(user_key, user_secret)
    if user_balance <= 0:
        print(f"❌ کاربر {user_key[:5]} موجودی ندارد.")
        return
        
    user_margin = round(user_balance * risk_percent, 2)
    
    # 🌟 جلوگیری از خطای "Collateral is below the minimum"
    if user_margin < 1.0:
        print(f"⚠️ مارجین محاسبه شده برای {user_key[:5]} ({user_margin}$) کمتر از حد مجاز صرافی (۱ دلار) است. رد شد.")
        return

    print(f"⏳ باز کردن {side} برای {user_key[:5]} با مارجین {user_margin}$ و اهرم {leverage}x...")
    order_body = {"symbol": symbol, "side": side, "tradeType": "MARKET", "leverage": leverage, "cost": str(user_margin)}
    response = request("POST", f"{FUTURES_PREFIX}/positions", user_key, user_secret, order_body)
    if response is None: return False
        
    print(f"✅ سفارش ارسال شد. در حال جستجوی پوزیشن...")
    time.sleep(3)
    
    positions = request("GET", f"{FUTURES_PREFIX}/positions", user_key, user_secret)
    if positions is None: return False
        
    items = positions.get("items", []) if isinstance(positions, dict) else positions
    target_position = None
    for p in items:
        if p.get("symbol") == symbol and p.get("status") == "OPENED" and p.get("isActive") == True:
            if target_position is None or p.get("createdAt", "") > target_position.get("createdAt", ""):
                target_position = p
                
    if target_position is None:
        print(f"❌ پوزیشن باز برای {user_key[:5]} پیدا نشد.")
        return False
        
    position_id = target_position.get("id")
    user_entry = float(target_position["entryPrice"])
    
    # محاسبه SL و TP جدید برای کاربر بر اساس درصدهای مستر
    if sl_pct and tp_pct:
        if side == "LONG":
            user_sl = round(user_entry * (1 - sl_pct), 8)
            user_tp = round(user_entry * (1 + tp_pct), 8)
        else:
            user_sl = round(user_entry * (1 + sl_pct), 8)
            user_tp = round(user_entry * (1 - tp_pct), 8)
            
        print(f"⏳ تنظیم SL ({user_sl}) و TP ({user_tp}) برای {user_key[:5]} (بر اساس درصد مستر)...")
        
        tpsl_body = {
            "stopLoss": str(user_sl),
            "takeProfit": str(user_tp),
            "stopLossOrderType": "STOP_MARKET",
            "takeProfitOrderType": "TAKE_PROFIT_MARKET"
        }
        tpsl_response = request("PATCH", f"{FUTURES_PREFIX}/positions/{position_id}/tpsl", user_key, user_secret, tpsl_body)
        
        if tpsl_response is not None:
            print(f"✅ TP/SL برای {user_key[:5]} تنظیم شد.")
            return True
        else:
            print(f"❌ خطا در تنظیم TP/SL برای {user_key[:5]}.")
            return False
    else:
        print(f"⚠️ معامله مستر TP/SL معتبر ندارد. برای کاربر تنظیم نشد.")
        return True

# ==========================================
# ۴. اجرای اصلی
# ==========================================
def main():
    print("🚀 شروع کپی معاملات نسبی...")
    
    master_balance = get_balance(MASTER_KEY, MASTER_SECRET)
    print(f"💰 موجودی حساب اصلی: {master_balance}$")
    if master_balance <= 0: return
        
    master_positions = request("GET", f"{FUTURES_PREFIX}/positions", MASTER_KEY, MASTER_SECRET)
    if not master_positions: return

    items = master_positions.get("items", []) if isinstance(master_positions, dict) else master_positions
    open_items = [p for p in items if p.get("status") == "OPENED" and p.get("isActive") == True]
    
    if not open_items:
        print("حساب اصلی هیچ پوزیشن بازی ندارد.")
        return

    print(f"تعداد {len(open_items)} پوزیشن باز در حساب اصلی پیدا شد.")
    
    users = get_active_users()
    print(f"تعداد {len(users)} کاربر برای کپی پیدا شد.")
    if len(users) == 0: return

    for p in open_items:
        print(f"\n--- کپی کردن {p['symbol']} {p['side']} ---")
        for user in users:
            copy_trade_for_user(p, user["api_key"], user["api_secret"], master_balance)
            time.sleep(1)

if __name__ == "__main__":
    main()
