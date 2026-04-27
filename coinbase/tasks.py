import logging
import requests
import time

from celery import shared_task
from celery.contrib.abortable import AbortableTask
from rbzk.celery import app
from wbsockets.websocket_handler import CoinbaseWebSocketHandler
from rbzk.settings import GLOBAL_WS_TASK_NAME
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
    
    handler = CoinbaseWebSocketHandler(ticker_symbols, task_id)

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





@shared_task
def setup_history_logs():
    # curl --request GET \
#   --url 'https://api.coinbase.com/api/v3/brokerage/market/products/XLM-USD/candles?granularity=ONE_DAY&end=1777234896&start=1772482896&limit=90' \
#   --header 'Authorization: Bearer <token>'
#   
    end_time = int(time.time())
    start_time = end_time - (56 * 86400)
    granularity = '86400'
    
    # Note: Modern Advanced Trade API requires JWT or API Key authentication
    # See official docs for signing requests: https://docs.cdp.coinbase.com/
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer <YOUR_ACCESS_TOKEN>"
    }

    trading_pairs = TradingPair.objects.all()

    for pair in trading_pairs:
        if pair.ticker_symbol:
            url = f"https://api.coinbase.com/api/v3/brokerage/products/{pair.ticker_symbol}/candles"
            params = {
                "start": str(start_time),
                "end": str(end_time),
                "granularity": granularity,
            }
            response = requests.get(url, params=params, headers=headers)
            data = response.json()
 

            # DayPriceLog.objects.create(
            #     coinbase_date = datetime.now(),
            #     ticker_symbol=pair.ticker_symbol,
            #     high_price= respinse["high"],
            #     low_price=response["low"],       
            #     last_price=response["close"],
            #     n_atr = 44,
            # )