#!/usr/bin/env python3
"""
Standalone WebSocket service for Coinbase price streaming using the advanced handler.
Publishes price updates to Redis channels for real-time consumption.
"""

import json
import logging
import time
import asyncio
import signal
import sys
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

import redis
from websockets.extensions import permessage_deflate

from config import (
    COINBASE_API_KEY,
    COINBASE_API_SECRET,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    PRODUCT_IDS,
    WEBSOCKET_HEALTH_PORT
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    """Simple HTTP health check endpoint"""
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            # Access server attributes via self.server
            ws_status = getattr(self.server, 'ws_status', 'unknown')
            
            response = {
                'status': 'running',
                'products': PRODUCT_IDS,
                'connections': ws_status
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress HTTP server logs


class CoinbaseWebSocketHandlerAdvanced:
    """Advanced WebSocket handler with proper compression headers as per Coinbase docs"""
    
    def __init__(self, product_ids=None, task_id=None, redis_client=None):
        self.product_ids = product_ids or ["BTC-USD", "ETH-USD"]
        self.task_id = task_id
        self.running = False
        self.websocket = None
        self.heartbeat_interval = 30
        self.last_pong_time = None
        self.reconnect_delay = 1
        self.redis_client = redis_client
        self.last_prices = {}  # Cache for latest prices
        
    async def connect(self):
        """Async connection with proper compression headers"""
        import websockets
        from websockets import client
        
        uri = "wss://ws-feed.exchange.coinbase.com"
        
        # Create compression extension with proper parameters as per Coinbase docs
        compression_extensions = [
            permessage_deflate.ClientPerMessageDeflateFactory(
                client_max_window_bits=15,  # Default window bits
                compress_settings={
                    "memLevel": 8,  # Memory level for compression
                    "level": 6,      # Compression level (1-9)
                }
            )
        ]
        
        # Setup headers for compression negotiation
        extra_headers = {
            "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits=15",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "CoinbaseWebSocketClient/1.0"
        }
        
        # Establish connection with compression
        self.websocket = await websockets.connect(
            uri,
            compression="deflate",  # Enable permessage-deflate
            extensions=compression_extensions,
            extra_headers=extra_headers,
            ping_interval=self.heartbeat_interval,
            ping_timeout=10,
            close_timeout=10,
            max_size=2**23,  # 8MB max message size
            max_queue=32     # Max queue size for incoming messages
        )
        
        logger.info(f"Connected to Coinbase with compression enabled")
        
        # Subscribe to channels
        subscribe_message = {
            "type": "subscribe",
            "channels": [{
                "name": "ticker",
                "product_ids": self.product_ids
            }]
        }
        await self.websocket.send(json.dumps(subscribe_message))
        logger.info(f"Subscribed to {self.product_ids}")
        self.last_pong_time = time.time()
    
    def publish_price(self, product_id: str, price_data: dict):
        """Publish price update to Redis with multiple methods"""
        if not self.redis_client:
            return
        
        try:
            # # Method 1: Store latest price in a hash (for quick lookups)
            # self.redis_client.hset(
            #     f"coinbase:price:{product_id}",
            #     mapping=price_data
            # )
            # # Set expiry (prices older than 1 hour are stale)
            # self.redis_client.expire(f"coinbase:price:{product_id}", 3600)
            
            # Method 2: Publish to a product-specific channel
            self.redis_client.publish(
                f"coinbase:updates:{product_id}",
                json.dumps(price_data)
            )
            
            # Method 3: Publish to a global channel for all updates
            self.redis_client.publish(
                "coinbase:updates:all",
                json.dumps({
                    'product_id': product_id,
                    'price_data': price_data,
                })
            )
            
            # Cache latest price
            self.last_prices[product_id] = price_data
            
        except Exception as e:
            logger.error(f"Failed to publish to Redis: {e}")
    
    async def run(self):
        """Main run loop with auto-restart and compression"""
        import websockets
        
        while self.running:
            try:
                await self.connect()
                
                async for message in self.websocket:
                    # Handle pong responses
                    try:
                        data = json.loads(message)
                        if data.get('type') == 'pong':
                            self.last_pong_time = time.time()
                            continue
                    except:
                        pass
                    
                    # Process market data and publish to Redis
                    await self.process_message(message)
                    
            except websockets.ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}. Reconnecting...")
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
                    
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.running:
                    logger.info(f"Reconnecting in {self.reconnect_delay} second...")
                    await asyncio.sleep(self.reconnect_delay)
    
    async def process_message(self, message: str):
        """Process incoming message and publish to Redis"""
        # print("----------------Message-----------------------")
        # print(message)
        try:
            data = json.loads(message)
            channel = data.get('channel')
                # ticker_data = json.loads(data)
            # if ticker_data.get('type') == 'ticker':
            if data.get('type') == 'ticker':
                # for event in data.get('events', []):
                #     for ticker in event.get('tickers', []):
                product_id = data.get('product_id')
                price_data = {
                    'product_id': data.get('product_id'),
                    'price': data.get('price'),
                    'volume_24h': data.get('volume_24_h'),
                    'best_bid': data.get('best_bid'),
                    'best_ask': data.get('best_ask'),
                    'side': data.get('side'),
                    'trade_id': data.get('trade_id'),
                    'time': data.get('time'),
                    'timestamp': int(time.time())
                }
                # print("---------------Price Data----------------------")
                # print(price_data)
                # print("---------------Product ID Data----------------------")
                # print(product_id)
                if product_id is not None and price_data is not None:
                    self.publish_price(
                        product_id,
                        price_data
                    )
                        
            elif channel == 'heartbeats':
                logger.debug("Heartbeat received")
                
            elif channel == 'subscriptions':
                logger.info(f"Subscription confirmed: {data}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def start(self):
        """Start the WebSocket connection"""
        self.running = True
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self.run())
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            loop.close()
        
    def stop(self):
        """Stop the WebSocket connection"""
        self.running = False
        if self.websocket:
            try:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                if loop.is_running():
                    asyncio.create_task(self.websocket.close())
                else:
                    loop.run_until_complete(self.websocket.close())
            except Exception as e:
                logger.error(f"Error closing websocket: {e}")


class CoinbaseWebSocketService:
    """
    Standalone WebSocket service that publishes price data to Redis.
    Uses Redis pub/sub for real-time updates.
    """
    
    def __init__(self):
        self.running = False
        self.redis_client = None
        self.health_server = None
        self.handler = None
        
    def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False
    
    def start_health_server(self):
        """Start HTTP health check server in a separate thread"""
        server_address = ('0.0.0.0', WEBSOCKET_HEALTH_PORT)
        httpd = HTTPServer(server_address, HealthHandler)
        httpd.ws_status = 'running'
        logger.info(f"Health server listening on port {WEBSOCKET_HEALTH_PORT}")
        httpd.serve_forever()
    
    def run(self):
        """Main service entry point"""
        logger.info("Starting Coinbase WebSocket Service")
        
        # Connect to Redis
        if not self.connect_redis():
            logger.error("Cannot start without Redis connection")
            sys.exit(1)
        
        # Start health check server in background
        health_thread = Thread(target=self.start_health_server, daemon=True)
        health_thread.start()
        
        # Set up signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            logger.info("Shutdown signal received")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize and run WebSocket handler
        self.handler = CoinbaseWebSocketHandlerAdvanced(
            product_ids=PRODUCT_IDS,
            redis_client=self.redis_client
        )
        
        self.running = True
        self.handler.start()
    
    def stop(self):
        """Stop the service"""
        logger.info("Stopping WebSocket service")
        self.running = False
        if self.handler:
            self.handler.stop()


if __name__ == "__main__":
    service = CoinbaseWebSocketService()
    service.run()