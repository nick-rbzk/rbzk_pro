from celery import shared_task
from celery.signals import worker_shutting_down
from wbsockets.websocket_handler import CoinbaseWebSocketHandler
import logging

logger = logging.getLogger(__name__)

# Store handlers globally to manage them
active_handlers = {}

@shared_task(bind=True, max_retries=None)
def run_coinbase_websocket(self, product_ids=None):
    """
    Long-running Celery task for Coinbase WebSocket connection
    """
    task_id = self.request.id
    logger.info(f"Starting Coinbase WebSocket task {task_id}")
    
    handler = CoinbaseWebSocketHandler(product_ids)
    active_handlers[task_id] = handler
    print(active_handlers)
    try:
        handler.start()  # This blocks until connection closes
    except Exception as e:
        logger.error(f"WebSocket task error: {e}")
        # Retry after delay
        self.retry(countdown=30)
    finally:
        if task_id in active_handlers:
            del active_handlers[task_id]
    
    return "WebSocket task completed"

@shared_task
def stop_coinbase_websocket(task_id):
    """Stop a running WebSocket task"""
    print(active_handlers)
    if task_id in active_handlers:
        active_handlers[task_id].stop()
        del active_handlers[task_id]
        return f"Stopped WebSocket task {task_id}"
    return f"Task {task_id} not found"

@worker_shutting_down.connect
def shutdown_websockets(**kwargs):
    """Clean shutdown when Celery worker stops"""
    for handler in active_handlers.values():
        handler.stop()
    active_handlers.clear()