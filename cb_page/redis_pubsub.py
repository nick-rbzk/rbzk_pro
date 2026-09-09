"""
Redis pub/sub client for real-time price updates.
Supports both synchronous and asynchronous consumption patterns.
"""

import json
import threading
import time
import logging
import redis
from django.conf import settings
from django.core.cache import cache
from cb_trades.tasks import strategy_s1, redis_store_price


logger = logging.getLogger(__name__)


class RedisPriceSubscriber:
    """
    Redis pub/sub subscriber for price updates.
    Can run in background thread or be used with Django Channels.
    """
    def __init__(self, product_id=None):
        self.product_id = product_id
        self.redis_client = None
        self.pubsub = None
        self.running = False
        self.callbacks = []
        self.thread = None
        
    def connect(self):
        """Connect to Redis"""
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()
        return self
    
    def subscribe(self, channel=None):
        """Subscribe to a Redis channel"""
        if not self.pubsub:
            self.connect()
        
        channel = "coinbase:updates:all"
        
        # Subscribe to the channel
        self.pubsub.subscribe(**{channel: self._handle_message})
        logger.info(f"Subscribed to Redis channel: {channel}")
        return self
    
    def add_callback(self, callback):
        """Add callback function to be called on each message"""
        self.callbacks.append(callback)
        return self
    
    def _handle_message(self, message):
        """Handle incoming Redis message"""
        if message['type'] == 'message':

            data = json.loads(message.get('data'))
            ticker_data = data.get('price_data')

            # strategy_s1(ticker_data)

            redis_store_price(ticker_data)
            try:
                # Call all registered callbacks
                for callback in self.callbacks:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")



    
    def start(self, background=True):
        """Start listening for messages"""
        if not self.pubsub:
            self.connect()
        
        self.running = True
        
        if background:
            # Run in background thread
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            logger.info("Redis subscriber started in background")
        else:
            # Run in current thread (blocking)
            self._run()
    
    def _run(self):
        """Main loop for message processing"""
        while self.running:
            try:
                self.pubsub.get_message(timeout=1.0)
            except Exception as e:
                logger.error(f"Redis pub/sub error: {e}")
                time.sleep(1)
    
    def stop(self):
        """Stop listening"""
        self.running = False
        if self.pubsub:
            self.pubsub.unsubscribe()
            self.pubsub.close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        logger.info("Redis subscriber stopped")


# Global subscriber instances
_subscribers = {}

def get_price_subscriber(product_id=None):
    """Get or create a subscriber instance"""
    key = product_id or "all"
    if key not in _subscribers:
        _subscribers[key] = RedisPriceSubscriber(product_id).connect().subscribe()
    return _subscribers[key]


def start_global_subscriber():
    """Start global subscriber for all price updates"""
    subscriber = get_price_subscriber()
    subscriber.start(background=True)
    return subscriber