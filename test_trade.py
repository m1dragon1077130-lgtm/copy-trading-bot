import os
import time
import json
import hmac
import hashlib
import urllib.request
import urllib.error

# ==========================================
# ۱. تنظیمات (از Secrets گیت‌هاب خوانده می‌شود)
# ==========================================
API_KEY = os.environ.get("MASTER_API_KEY")
API_SECRET = os.environ.get("MASTER_API_SECRET")
BASE_URL = "https://apiv2.thetruetrade.io"
FUTURES_PREFIX = "/futures"

# ==========================================
# ۲. تنظیمات معامله تستی
# ==========================================
SYMBOL = "BTCUSDT"
SIDE = "LONG"           
MARGIN_USD = "2.0"      
LEVERAGE = 10           
STOP_LOSS_PCT = 0.02    # ۲ درصد
TAKE_PROFIT_PCT = 0.04  # ۴ درصد

# ==========================================
# ۳. توابع ارتباط با API
# ==========================================
def sign(secret, timestamp, method, uri):
    payload = f"{timestamp}{method.upper()}{uri}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def request(method, uri, body=None):
    timestamp = str(int(time.time() * 1000))
    signature = sign(API_SECRET, timestamp, method, uri)
    headers = {
        "X-API-Key": API_KEY, "X-Timestamp": timestamp, "X-Signature": signature,
        "Accept": "application/json", "User-Agent": "Mozilla/5.0"
    }
    data = json.dumps(body).encode() if body else None
    if data: headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(BASE_URL + uri, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        print(f"❌ خطای HTTP {e.code}: {e.read().decode(errors='replace')}")
        return None
    except Exception as e:
        print(f"❌ خطا: {e}")
        return None

# ==========================================
# ۴. اجرای معامله
# ==========================================
print("🚀 شروع تست باز کردن معامله...")

# ۱. باز کردن معامله
order_body = {
    "symbol": SYMBOL,
    "side": SIDE,
    "tradeType": "MARKET",
    "leverage": LEVERAGE,
    "cost": MARGIN_USD
}

print(f"⏳ ارسال درخواست برای باز کردن {SIDE} روی {SYMBOL}...")
response = request("POST", f"{FUTURES_PREFIX}/positions", order_body)

if response is None:
    print("❌ معامله باز نشد.")
else:
    print("✅ سفارش با موفقیت ارسال شد. (Order ID:", response.get("orderId"), ")")
    
    # ۲. کمی صبر میکنیم تا صرافی پوزیشن رو ثبت کنه
    print("⏳ صبر ۳ ثانیه‌ای برای ثبت پوزیشن در صرافی...")
    time.sleep(3)
    
    # ۳. لیست پوزیشن‌ها رو می‌گیریم تا جدیدترین پوزیشن باز رو پیدا کنیم
    print("🔍 در حال جستجوی پوزیشن باز...")
    positions = request("GET", f"{FUTURES_PREFIX}/positions")
    
    if positions is None:
        print("❌ خطا در خواندن پوزیشن‌ها.")
    else:
        items = positions.get("items", []) if isinstance(positions, dict) else positions
        
        # پیدا کردن پوزیشن باز روی نماد مورد نظر
        target_position = None
        for p in items:
            if p.get("symbol") == SYMBOL and p.get("status") == "OPENED" and p.get("isActive") == True:
                # اگر چند تا پوزیشن داریم، جدیدترین رو انتخاب میکنیم
                if target_position is None or p.get("createdAt", "") > target_position.get("createdAt", ""):
                    target_position = p
                    
        if target_position is None:
            print("❌ هیچ پوزیشن بازی برای این نماد پیدا نشد.")
        else:
            position_id = target_position.get("id")
            entry_price = float(target_position.get("entryPrice"))
            print(f"✅ پوزیشن پیدا شد! ID: {position_id} | قیمت ورود: {entry_price}")
            
            # ۴. محاسبه حد ضرر و سود
            if SIDE == "LONG":
                sl_price = round(entry_price * (1 - STOP_LOSS_PCT), 2)
                tp_price = round(entry_price * (1 + TAKE_PROFIT_PCT), 2)
            else:
                sl_price = round(entry_price * (1 + STOP_LOSS_PCT), 2)
                tp_price = round(entry_price * (1 - TAKE_PROFIT_PCT), 2)
                
            print(f"⏳ تنظیم حد ضرر ({sl_price}) و حد سود ({tp_price})...")
            
            tpsl_body = {
                "stopLoss": str(sl_price),
                "takeProfit": str(tp_price),
                "stopLossOrderType": "STOP_MARKET",
                "takeProfitOrderType": "TAKE_PROFIT_MARKET"
            }
            
            tpsl_response = request("PATCH", f"{FUTURES_PREFIX}/positions/{position_id}/tpsl", tpsl_body)
            if tpsl_response is not None:
                print("✅ حد ضرر و حد سود با موفقیت تنظیم شد!")
            else:
                print("⚠️ خطا در تنظیم TP/SL.")
