import json
import websocket
import logging

from cb_trades.tasks import db_record_price, redis_store_price


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
        redis_store_price.delay(message)
  
    
    def on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        logger.info("WebSocket connection closed")
        self.running = False
    
    def on_open(self, ws):
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



# {
#     'type': 'ticker', 
#     'sequence': 32448322892, 
#     'product_id': 'XLM-USD', 
#     'price': '0.160368', 
#     'open_24h': '0.159737', 
#     'volume_24h': '14671905.98494844', 
#     'low_24h': '0.15888', 
#     'high_24h': '0.16102', 
#     'volume_30d': '994495995.19697110', 
#     'best_bid': '0.160367', 
#     'best_bid_size': '900.00000000', 
#     'best_ask': '0.160402', 
#     'best_ask_size': '2982.05052067', 
#     'side': 'sell', 
#     'time': '2026-05-02T23:00:38.589372Z', 
#     'trade_id': 159000892, 
#     'last_size': '6.9'
#     }