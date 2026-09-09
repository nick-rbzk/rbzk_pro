import jwt, time, secrets, os, logging, requests, time

from cryptography.hazmat.primitives import serialization
from decimal import Decimal
from datetime import datetime
from cdp.auth.utils.jwt import generate_jwt, JwtOptions
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from rbzk.celery import app
from wbsockets.public_wbsocket import CoinbaseWebSocketHandlerAdvanced
from rbzk.settings import GLOBAL_WS_TASK_NAME, BASE_DIR
from .models import TradingPair, DayPriceLog

logger = logging.getLogger(__name__)


def build_jwt(ticker_symbol):
    key_name = os.environ.get("COINBASE_API_KEY")
    private_key = os.environ.get("COINBASE_API_SECRET")
    if not key_name and not private_key:
        logger.error("Coinbase keys not found")
        return False
    request_method  = "GET"
    request_host    = "api.coinbase.com"
    request_path=f"/api/v3/brokerage/products/{ticker_symbol}/candles"
    private_key = serialization.load_pem_private_key(private_key.encode(), password=None)
    uri = f"{request_method} {request_host}{request_path}"
    payload = {
        'sub': key_name,
        'iss': "cdp",
        'nbf': int(time.time()),
        'exp': int(time.time()) + 120,
        'uri': uri,
    }
    return jwt.encode(payload, private_key, algorithm='ES256',
                      headers={'kid': key_name, 'nonce': secrets.token_hex()})


@shared_task(name="low_priority:setup_history_logs")
def setup_history_logs(days=57, day_offset=-1):
    end_time = int(time.time())
    days = int(days)
    start_time = end_time - (days * 86400)
    granularity = 'ONE_DAY'
    trading_pairs = TradingPair.objects.all()

    for pair in trading_pairs:
        if pair.ticker_symbol:
            ticker_symbol = pair.ticker_symbol
            token = build_jwt(ticker_symbol)
            if not token:
                break
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            url = f"https://api.coinbase.com/api/v3/brokerage/products/{ticker_symbol}/candles"
            params = {
                "start": str(start_time),
                "end": str(end_time),
                "granularity": granularity,
            }
            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                candles = response.json()["candles"]
                cs = list(candles)
                yestarday_close = None
                for i in range(len(cs)-1, day_offset, -1):
                    obj = cs[i]
                    date = datetime.fromtimestamp(int(obj["start"]))
                    high_price = Decimal(obj["high"])
                    low_price = Decimal(obj["low"])
                    n_atr = None
                    if yestarday_close is not None:
                        one = abs(high_price - low_price)
                        two = abs(yestarday_close  - high_price)
                        three = abs(yestarday_close - low_price)
                        n_atr = max([one, two, three])
                    DayPriceLog.objects.create(
                        coinbase_date = date,
                        ticker_symbol=ticker_symbol,
                        open_price=Decimal(obj["open"]),
                        high_price= high_price,
                        low_price=low_price,       
                        last_price=Decimal(obj["close"]),
                        n_atr = n_atr,
                    )
                    yestarday_close = Decimal(obj["close"])
            time.sleep(0.5)


@shared_task(name="low_priority:setup_history_logs")
def setup_initial_trades():
    # Sets up trades according to existin TradingPairs
    # check if trade with trading pair already exists 
    # create one only if it does not.
    # the same buy and sell signal
    
    pass