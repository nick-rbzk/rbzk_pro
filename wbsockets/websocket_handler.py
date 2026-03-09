import json
import websocket
import threading
from django.core.cache import cache
# from your_app.models import PriceRecord  # If you want to store in DB
import logging

logger = logging.getLogger(__name__)

class CoinbaseWebSocketHandler:
    """Handles Coinbase WebSocket connection and data streaming"""
    
    def __init__(self, product_ids=None):
        self.product_ids = product_ids or ["BTC-USD", "ETH-USD"]
        self.ws = None
        self.running = False
        self.thread = None
        
    def on_message(self, ws, message):
        """Process incoming messages and store in cache/DB"""
        try:
            data = json.loads(message)
            if data.get('type') == 'ticker':
                # Store in Redis cache for real-time access
                if data['product_id'] == 'BTC-USD':
                    price_data = {
                        'product_id': data['product_id'],
                        'price': float(data['price']),
                        'volume': data.get('volume_24h'),
                        'timestamp': data.get('time')
                    }
                    cache_key = "coinbase_price_BTC"
                    cache.set(cache_key, price_data, timeout=300)

                if data['product_id'] == 'ETH-USD':
                    price_data = {
                        'product_id': data['product_id'],
                        'price': float(data['price']),
                        'volume': data.get('volume_24h'),
                        'timestamp': data.get('time')
                    }   
                    # Store in cache with 5-minute expiry
                    cache_key = "coinbase_price_ETH"
                    cache.set(cache_key, price_data, timeout=300)

                # Optionally store in database
                # PriceRecord.objects.create(**price_data)


                # TODO:
                # include compression header for websocket connection

                # setup email for webvision ltd
                # read up dajngo array field
                # Turtle trading
                # what other channles are there in websocket connection?



                # {
                #     'type': 'ticker', 
                #     'sequence': 123559917683, 
                #     'product_id': 'BTC-USD', 
                #     'price': '67183.35', 
                #     'open_24h': '68277.44', 
                #     'volume_24h': '3209.31668779', 
                #     'low_24h': '66921.33', 
                #     'high_24h': '68544.79', 
                #     'volume_30d': '311506.38062542', 
                #     'best_bid': '67183.34', 
                #     'best_bid_size': '0.05807832', 
                #     'best_ask': '67183.35', 
                #     'best_ask_size': '0.09469657', 
                #     'side': 'buy', 
                #     'time': '2026-03-08T00:53:03.576679Z', 
                #     'trade_id': 976055502, 
                #     'last_size': '0.00000011'
                # }


                # {
                #     'type': 'ticker', 
                #     'sequence': 94877087667, 
                #     'product_id': 'ETH-USD', 
                #     'price': '1967.4', 
                #     'open_24h': '1981.45', 
                #     'high_24h': '1996.51', 
                #     'low_24h': '1948.09', 
                #     'volume_24h': '54823.25148690', 
                #     'volume_30d': '5139108.87995923', 
                #     'best_bid': '1967.35', 
                #     'best_bid_size': '0.97569543', 
                #     'best_ask': '1967.40', 
                #     'best_ask_size': '0.52923031', 
                #     'side': 'buy', 
                #     'time': '2026-03-08T00:53:03.385858Z', 
                #     'trade_id': 781371209, 
                #     'last_size': '0.00009145'
                # }

                
                logger.debug(f"Price update: {price_data}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
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