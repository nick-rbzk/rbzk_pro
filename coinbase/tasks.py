import logging

from celery import shared_task
from celery.contrib.abortable import AbortableTask
from rbzk.celery import app
from wbsockets.websocket_handler import CoinbaseWebSocketHandler
from rbzk.settings import GLOBAL_WS_TASK_NAME
from .models import TradingPair, WebSocketTask


logger = logging.getLogger(__name__)


@shared_task(bind=True, base=AbortableTask)
def run_coinbase_websocket(self, pair_id):
    """
    Long-running Celery task for Coinbase WebSocket connection
    """

    task_id = self.request.id
    pair = TradingPair.objects.get(pk=pair_id)
    active_task = WebSocketTask.objects.create(
        task_id=task_id, 
        name=f"{GLOBAL_WS_TASK_NAME}:{pair.ticker_symbol}",
    )
    pair.is_active = True
    pair.running_task = active_task
    pair.save()

    logger.info(f"Starting Coinbase WebSocket task {task_id}")
    
    product_ids = [pair.ticker_symbol]
    handler = CoinbaseWebSocketHandler(product_ids, task_id)

    try:
        handler.start()
    except Exception as e:
        logger.error(f"WebSocket task error: {e}")

    return "WebSocket task completed"

@shared_task
def stop_coinbase_websocket(pair_id):
    """Stop a running WebSocket task"""

    active_pair = TradingPair.objects.get(pk=pair_id)
    active_pair.is_active = False
    task_id = active_pair.running_task.task_id
    app.control.revoke(task_id, terminate=True)
    active_pair.running_task.delete()
    active_pair.running_task = None
    active_pair.is_active = False
    active_pair.save()

    return "Stop WebSocket Task Completed"
