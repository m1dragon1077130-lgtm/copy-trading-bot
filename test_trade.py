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
SIDE = "LONG"           # جهت معامله (LONG یا SHORT)
MARGIN_USD = "2.0"      # مارجین ۲ دلار
LEVERAGE = 10           # اهرم ۱۰
STOP_LOSS_PCT = 0.02    # حد ضرر ۲ درصد
TAKE_PROFIT_PCT = 0.04  # حد سود ۴ درصد

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

# ۱. گرفتن قیمت فعلی بیت‌کوین
print("⏳ دریافت قیمت فعلی BTC...")
# (از آنجا که TTT مسیر عمومی برای قیمت ندارد، فعلاً از یک عدد فرضی یا قیمت مارک استفاده می‌کنیم. 
# اما صرافی خودش قیمت مارکت را در لحظه اعمال می‌کند)
# ما برای محاسبه حد ضرر و سود نیاز به قیمت ورود داریم. 
# راه حل: اول معامله را باز می‌کنیم، بعد قیمت ورود را از پاسخ می‌گیریم و TP/SL را ست می‌کنیم.

# ۲. باز کردن معامله (Market)
order_body = {
    "symbol": SYMBOL,
    "side": SIDE,
    "tradeType": "MARKET",
    "leverage": LEVERAGE,
    "cost": MARGIN_USD
}

print(f"⏳ ارسال درخواست برای باز کردن {SIDE} روی {SYMBOL} با مارجین {MARGIN_USD} دلار...")
response = request("POST", f"{FUTURES_PREFIX}/positions", order_body)

if response is None:
    print("❌ معامله باز نشد. (مشکل از کلید، موجودی یا دسترسی)")
else:
    print("✅ معامله با موفقیت باز شد!")
    print(f"پاسخ سرور: {json.dumps(response, indent=2)}")
    
    # ۳. تلاش برای تنظیم حد ضرر و حد سود
    # (بر اساس پاسخ سرور، آیدی پوزیشن و قیمت ورود را استخراج می‌کنیم)
    # نکته: ساختار پاسخ ممکن است کمی متفاوت باشد، اما معمولاً شامل id و entryPrice است.
    position_id = None
    entry_price = None
    
    if isinstance(response, dict):
        position_id = response.get("id")
        # گاهی پاسخ در کلید items یا data است
        if not position_id and "data" in response:
            position_id = response["data"].get("id")
            entry_price = response["data"].get("entryPrice")
        else:
            entry_price = response.get("entryPrice")

    if position_id and entry_price:
        entry_price = float(entry_price)
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
            print("⚠️ معامله باز شد اما تنظیم TP/SL با خطا مواجه شد. (ممکنه دستی باید انجام بشه)")
    else:
        print("⚠️ معامله باز شد اما آیدی یا قیمت ورود در پاسخ پیدا نشد. (TP/SL تنظیم نشد)")
