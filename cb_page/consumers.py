"""
Django Channels WebSocket consumer for real-time price updates.
Connects to Redis pub/sub and forwards messages to WebSocket clients.
"""

import json
import redis
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.conf import settings
import asyncio


class PriceConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that subscribes to Redis pub/sub channels
    and forwards price updates to connected clients.
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.product_id = self.scope['url_route']['kwargs'].get('product_id')
        self.room_group_name = f'price_{self.product_id}' if self.product_id else 'price_all'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Start Redis subscription in background
        asyncio.create_task(self.start_redis_subscription())
        
        # Send initial price
        from .websocket_client import price_client
        if self.product_id:
            price = price_client.get_latest_price(self.product_id)
            if price:
                await self.send(text_data=json.dumps({
                    'type': 'initial',
                    'data': price
                }))
    
    async def start_redis_subscription(self):
        """Subscribe to Redis pub/sub channel and forward messages to WebSocket"""
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        pubsub = redis_client.pubsub()
        
        # Subscribe to product-specific channel or all updates
        channel = f"coinbase:updates:{self.product_id}" if self.product_id else "coinbase:updates:all"
        pubsub.subscribe(channel)
        
        # Forward messages to WebSocket
        for message in pubsub.listen():
            if message['type'] == 'message':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'price_update',
                        'data': message['data']
                    }
                )
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages (for client control)"""
        try:
            data = json.loads(text_data)
            command = data.get('command')
            
            if command == 'subscribe':
                product_id = data.get('product_id')
                if product_id:
                    new_group = f'price_{product_id}'
                    await self.channel_layer.group_add(
                        new_group,
                        self.channel_name
                    )
                    await self.send(text_data=json.dumps({
                        'type': 'subscribed',
                        'product_id': product_id
                    }))
                    
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON'
            }))
    
    async def price_update(self, event):
        """Send price update to WebSocket client"""
        await self.send(text_data=json.dumps({
            'type': 'update',
            'data': json.loads(event['data'])
        }))