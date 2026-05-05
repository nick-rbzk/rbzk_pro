import jwt, time, secrets, os, logging, requests, time, os

from cryptography.hazmat.primitives import serialization
from decimal import Decimal
from datetime import datetime
from cdp.auth.utils.jwt import generate_jwt, JwtOptions
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from rbzk.celery import app
from wbsockets.public_wbsocket import CoinbaseWebSocketHandlerAdvanced
# from wbsockets.websocket_handler import CoinbaseWebSocketHandler
# from wbsockets.coinbase_websoket import CoinbaseWebSocketHandler
from rbzk.settings import GLOBAL_WS_TASK_NAME, BASE_DIR
from .models import TradingPair, WebSocketTask, DayPriceLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=AbortableTask)
def run_coinbase_websocket(self, pair_ids):
    """
    Long-running Celery task for Coinbase WebSocket connection
    """

    task_id = self.request.id
    pairs = TradingPair.objects.filter(pk__in=pair_ids)
    
    ticker_symbols = []
    for p in pairs:
        ticker_symbols.append(p.ticker_symbol)

    logger.info(f"Starting Coinbase WebSocket task {task_id}")
    
    # handler = CoinbaseWebSocketHandler(ticker_symbols, task_id)
    handler = CoinbaseWebSocketHandlerAdvanced(ticker_symbols, task_id)

    try:
        handler.start()
    except Exception as e:
        logger.error(f"WebSocket task error: {e}")

    return "WebSocket task completed"

@shared_task
def stop_coinbase_websocket():
    """Stop a running WebSocket task"""
    task_ids = []
    websocket_obj_ids = []
    active_pairs = TradingPair.objects.filter(is_active=True)
    for active_pair in active_pairs:
        if hasattr(active_pair, 'running_task'):
            if active_pair.running_task is not None:
                task_ids.append(active_pair.running_task.task_id)
                websocket_obj_ids.append(active_pair.running_task.pk)
        active_pair.running_task = None
        active_pair.is_active = False
        active_pair.save()

    task_ids = set(task_ids)
    for task_id in list(task_ids):
        if task_id is not None:
            app.control.revoke(task_id, terminate=True)
    websocket_obj_ids = set(websocket_obj_ids)
    websockets = WebSocketTask.objects.filter(pk__in=websocket_obj_ids)
    for w in websockets:
        w.delete()
    return "Stop WebSocket Task Completed"


def build_jwt(ticker_symbol):
    key_name = os.environ.get("COINBASE_KEY_NAME")
    private_key = os.environ.get("COINBASE_KEY_SECRET")
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
def setup_history_logs():
    end_time = int(time.time())
    start_time = end_time - (56 * 86400)
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
                for i in range(len(cs)-1, -1, -1):
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
