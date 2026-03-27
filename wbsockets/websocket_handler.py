import json
import websocket
import logging

from cb_trades.tasks import record_price


logger = logging.getLogger(__name__)


class CoinbaseWebSocketHandler:
    """Handles Coinbase WebSocket connection and data streaming"""
    
    def __init__(self, product_ids=None, task_id=None):
        self.product_ids = product_ids or ["BTC-USD", "ETH-USD"]
        self.task_id = task_id
        self.ws = None
        self.running = False
        self.thread = None
        
    def on_message(self, ws, message):
        """Process incoming messages and store in DB"""
        record_price.delay(self.product_ids, message)
    
    def on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        logger.info("WebSocket connection closed")
        self.running = False
    
    def on_open(self, ws):
        # TODO
        # include compression header for websocket connection
        """Subscribe to channels when connection opens"""
        subscribe_message = {
            "type": "subscribe",
            "channels": [{
                "name": "ticker",
                "product_ids": self.product_ids
            }]
        }
        ws.send(json.dumps(subscribe_message))
        logger.info(f"Subscribed to {self.product_ids}")
    
    def start(self):
        """Start WebSocket connection in current thread"""
        ws_url = "wss://ws-feed.exchange.coinbase.com"
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.running = True
        self.ws.run_forever()

    def stop(self):
        """Stop WebSocket connection"""
        self.running = False
        if self.ws:
            self.ws.close()