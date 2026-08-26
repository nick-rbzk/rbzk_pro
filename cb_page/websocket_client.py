"""
Redis client for accessing WebSocket service data from Django.
"""

import json
import redis
from django.conf import settings


class PriceClient:
    """Client for reading price data from Redis (published by WebSocket service)"""
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
    
    def get_latest_price(self, product_id: str) -> dict:
        """Get the latest price for a product"""
        data = self.redis_client.hgetall(f"coinbase:price:{product_id}")
        if data:
            # Convert price to float for JSON serialization
            if 'price' in data and data['price']:
                data['price'] = float(data['price'])
            if 'best_bid' in data and data['best_bid']:
                data['best_bid'] = float(data['best_bid'])
            if 'best_ask' in data and data['best_ask']:
                data['best_ask'] = float(data['best_ask'])
        return data
    
    def get_all_prices(self) -> dict:
        """Get latest prices for all products"""
        keys = self.redis_client.keys("coinbase:price:*")
        prices = {}
        for key in keys:
            product_id = key.replace("coinbase:price:", "")
            prices[product_id] = self.get_latest_price(product_id)
        return prices


# Singleton instance
price_client = PriceClient()