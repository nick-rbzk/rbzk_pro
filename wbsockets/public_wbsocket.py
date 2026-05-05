import json
import logging
import time
import asyncio


from cb_trades.tasks import redis_store_price, strategy_s1

logger = logging.getLogger(__name__)

# Alternative implementation using websockets library with better compression support
class CoinbaseWebSocketHandlerAdvanced:
    """Advanced WebSocket handler with proper compression headers as per Coinbase docs"""
    
    def __init__(self, product_ids=None, task_id=None):
        self.product_ids = product_ids or ["BTC-USD", "ETH-USD"]
        self.task_id = task_id
        self.running = False
        self.websocket = None
        self.heartbeat_interval = 30
        self.last_pong_time = None
        
    async def connect(self):
        """Async connection with proper compression headers"""
        import websockets
        from websockets import client
        from websockets.extensions import permessage_deflate
        
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
        
        logger.info(f"Connected to Coinbase with compression enabled. Headers negotiated: {self.websocket.response_headers}")
        
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
                    
                    # Process market data
                    redis_store_price.delay(message)
                    strategy_s1.delay(message)
                    
            except websockets.ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}. Reconnecting...")
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
                    
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.running:
                    logger.info(f"Reconnecting in {self.reconnect_delay} second...")
                    await asyncio.sleep(self.reconnect_delay)
        
    def start(self):
        """Start the WebSocket connection"""
        import asyncio
        self.running = True
        self.reconnect_delay = 1
        
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
        import asyncio
        self.running = False
        if self.websocket:
            try:
                # Get or create event loop
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
