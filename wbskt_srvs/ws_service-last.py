#!/usr/bin/env python3
"""
Standalone WebSocket service for Coinbase price streaming.
Supports dynamic product subscription, start/stop control, and health monitoring.
"""

import json
import logging
import time
import asyncio
import signal
import sys
import threading
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from typing import List, Optional, Set
import re

import redis
from websockets.extensions import permessage_deflate

from config import (
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


class ServiceState:
    """Thread-safe service state management"""
    _lock = threading.RLock()
    
    def __init__(self):
        self._running = False
        self._products = set(PRODUCT_IDS)
        self._ws_status = 'stopped'
        self._handler = None
        self._resub_inflight = threading.Event()
        
    @property
    def running(self):
        with self._lock:
            return self._running
    
    @running.setter
    def running(self, value):
        with self._lock:
            self._running = value
    
    @property
    def products(self):
        with self._lock:
            return list(self._products)
    
    @products.setter
    def products(self, value):
        with self._lock:
            self._products = set(value)
    
    @property
    def ws_status(self):
        with self._lock:
            return self._ws_status
    
    @ws_status.setter
    def ws_status(self, value):
        with self._lock:
            self._ws_status = value
    
    @property
    def handler(self):
        with self._lock:
            return self._handler
    
    @handler.setter
    def handler(self, value):
        with self._lock:
            self._handler = value
    
    def update_products(self, new_products):
        """Update products and return whether they changed"""
        with self._lock:
            old_products = set(self._products)
            new_set = set(new_products)
            if new_set != old_products:
                self._products = new_set
                return True
            return False

    def try_begin_resubscribe(self) -> bool:
        """Atomically claim the resubscribe slot. Returns True if claimed."""
        with self._lock:
            if self._resub_inflight.is_set():
                return False
            self._resub_inflight.set()
            return True

    def end_resubscribe(self) -> None:
        with self._lock:
            self._resub_inflight.clear()


# Global state
service_state = ServiceState()


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks and control endpoints"""
    
    def _send_json_response(self, status_code: int, data: dict):
        """Send JSON response with proper headers"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def _validate_product_ids(self, products: List[str]) -> bool:
        """Validate product IDs format (e.g., BTC-USD, ETH-USD)"""
        pattern = re.compile(r'^[A-Z]{2,6}-[A-Z]{2,6}$')
        return all(pattern.match(p) for p in products)
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/health':
            self._send_json_response(200, {
                'status': 'running' if service_state.running else 'stopped',
                'products': service_state.products,
                'connections': service_state.ws_status,
                'timestamp': int(time.time())
            })
        else:
            self._send_json_response(404, {'error': 'Not found'})
    
    def do_POST(self):
        """Handle POST requests for control endpoints"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json_response(400, {'error': 'Invalid JSON'})
            return
        
        if path == '/start':
            self._handle_start(data)
        elif path == '/stop':
            self._handle_stop()
        elif path == '/resubscribe':
            self._handle_resubscribe(data)
        else:
            self._send_json_response(404, {'error': 'Not found'})
    
    def _handle_start(self, data: dict):
        """Handle start request"""
        if service_state.running:
            self._send_json_response(200, {
                "status": "already_running",
                "products": service_state.products,
                "message": "Service is already running",
            })
            return
        
        # Validate and update products if provided
        products = data.get('products')
        if products:
            if not self._validate_product_ids(products):
                self._send_json_response(400, {
                    'error': 'Invalid product IDs format. Use format like BTC-USD, ETH-USD'
                })
                return
            service_state.products = products
        
        # Start the service in a background thread
        def start_service():
            service = CoinbaseWebSocketService()
            service_state.handler = service
            service.run()
        
        thread = Thread(target=start_service, daemon=True)
        thread.start()
        
        # Wait briefly for service to start
        time.sleep(1)
        
        self._send_json_response(200, {
            'status': 'starting',
            'products': service_state.products,
            'message': 'WebSocket service starting'
        })
    
    def _handle_stop(self):
        """Handle stop request"""
        if not service_state.running:
            self._send_json_response(200, {
                'status': 'already_stopped',
                'message': 'Service is already stopped'
            })
            return
        
        # Stop the service
        if service_state.handler:
            service_state.handler.stop()
            service_state.handler = None
        
        service_state.running = False
        service_state.ws_status = 'stopped'
        
        self._send_json_response(200, {
            'status': 'stopped',
            'message': 'WebSocket service stopped successfully'
        })
    
    def _handle_resubscribe(self, data: dict):
        """Handle resubscribe request with new products"""
        products = data.get('products')

        if not service_state.try_begin_resubscribe():
            self._send_json_response(202, {"status": "in_progress"})
            return
        
        if not products:
            self._send_json_response(400, {
                'error': 'Products list required'
            })
            return
        
        if not self._validate_product_ids(products):
            self._send_json_response(400, {
                'error': 'Invalid product IDs format. Use format like BTC-USD, ETH-USD'
            })
            return
        
        # Check if service is running
        if not service_state.running or not service_state.handler:
            # If not running, just update products and start
            service_state.products = products
            self._send_json_response(200, {
                'status': 'products_updated',
                'products': products,
                'message': 'Products updated, start service to apply'
            })
            return
        
        # Update products and trigger resubscribe
        changed = service_state.update_products(products)
        
        if not changed:
            self._send_json_response(200, {
                'status': 'no_change',
                'products': products,
                'message': 'Products already subscribed'
            })
            return
        
        # Signal the handler to resubscribe
        handler = service_state.handler
        if handler and hasattr(handler, 'resubscribe'):
            # Non-blocking call to resubscribe using thread-safe approach
            def do_resubscribe():
                try:
                    # Get the handler's event loop if available
                    if hasattr(handler, '_loop') and handler._loop is not None:
                        loop = handler._loop
                        # Schedule the resubscribe on the handler's loop
                        asyncio.run_coroutine_threadsafe(
                            handler.resubscribe(products),
                            loop
                        )
                    else:
                        # Fallback: create a new loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(handler.resubscribe(products))
                        loop.close()
                except Exception as e:
                    logger.error(f"Resubscribe failed: {e}")
            
            thread = Thread(target=do_resubscribe, daemon=True)
            thread.start()
        
        self._send_json_response(200, {
            'status': 'resubscribing',
            'products': products,
            'message': 'Resubscribing to new products'
        })
    
    def log_message(self, format, *args):
        pass  # Suppress HTTP server logs


class CoinbaseWebSocketHandlerAdvanced:
    """Advanced WebSocket handler with proper compression and dynamic subscription"""
    
    def __init__(self, product_ids: Optional[List[str]] = None, redis_client=None):
        self.product_ids = set(product_ids or PRODUCT_IDS)
        self._current_subscription = set(self.product_ids)
        self.running = False
        self.websocket = None
        self.heartbeat_interval = 30
        self.reconnect_delay = 1
        self.redis_client = redis_client
        self.last_prices = {}
        self._resubscribe_requested = False
        self._new_products = None
        self._lock = threading.RLock()
        self._connection_attempts = 0
        self._max_connection_attempts = 10
        self._loop = None  # Store the loop where websocket was created
        self._resubscribe_task = None  # Track resubscribe task
        self._resub_inflight = threading.Event()
        
    async def connect(self):
        """Async connection with proper compression headers"""
        import websockets
        
        uri = "wss://ws-feed.exchange.coinbase.com"
        
        compression_extensions = [
            permessage_deflate.ClientPerMessageDeflateFactory(
                client_max_window_bits=15,
                compress_settings={
                    "memLevel": 8,
                    "level": 6,
                }
            )
        ]
        
        extra_headers = {
            "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits=15",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "CoinbaseWebSocketClient/1.0"
        }
        
        try:
            self.websocket = await websockets.connect(
                uri,
                compression="deflate",
                extensions=compression_extensions,
                extra_headers=extra_headers,
                ping_interval=self.heartbeat_interval,
                ping_timeout=10,
                close_timeout=10,
                max_size=2**23,
                max_queue=32
            )
            
            # Store the loop where websocket was created
            self._loop = asyncio.get_running_loop()
            
            logger.info(f"Connected to Coinbase with compression enabled")
            self._connection_attempts = 0
            await self._send_subscription()
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Coinbase: {e}")
            self.websocket = None
            self._loop = None
            self._connection_attempts += 1
            
            if self._connection_attempts >= self._max_connection_attempts:
                logger.critical(f"Max connection attempts ({self._max_connection_attempts}) reached. Giving up.")
                self.running = False
                return False
            
            return False
    
    async def _send_subscription(self):
        """Send subscription message for current products"""
        if not self.websocket:
            logger.warning("WebSocket not connected, cannot subscribe")
            return
        
        products = list(self.product_ids)
        if not products:
            logger.warning("No products to subscribe to")
            return
        
        try:
            subscribe_message = {
                "type": "subscribe",
                "channels": [{
                    "name": "ticker",
                    "product_ids": products
                }]
            }
            await self.websocket.send(json.dumps(subscribe_message))
            logger.info(f"Subscribed to {products}")
            self._current_subscription = set(products)
        except Exception as e:
            logger.error(f"Failed to send subscription: {e}")
            raise
    
    async def resubscribe(self, new_products: List[str]):
        """Dynamically resubscribe to new products"""
        with self._lock:
            new_set = set(new_products)
            if new_set == self.product_ids:
                logger.info("Products unchanged, skipping resubscribe")
                return
            
            self.product_ids = new_set
            self._resubscribe_requested = True
            self._new_products = new_set
            
            # Force reconnection to apply new subscription
            if self.websocket:
                try:
                    # Use the websocket's own loop for closing if available
                    if hasattr(self.websocket, '_loop') and self.websocket._loop is not None:
                        loop = self.websocket._loop
                        # Schedule close on the websocket's loop
                        close_task = asyncio.run_coroutine_threadsafe(
                            self.websocket.close(code=1000, reason="Resubscribing"),
                            loop
                        )
                        try:
                            close_task.result(timeout=5)
                        except TimeoutError:
                            logger.warning("Close timeout during resubscribe")
                        except Exception as e:
                            logger.warning(f"Error closing websocket for resubscribe: {e}")
                    else:
                        # Fallback: close directly
                        await self.websocket.close(code=1000, reason="Resubscribing")
                except Exception as e:
                    logger.warning(f"Error closing websocket for resubscribe: {e}")
                
                self.websocket = None
                self._loop = None
    
    def publish_price(self, product_id: str, price_data: dict):
        if not self.redis_client:
            return
        try:
            # Use pipeline as a context manager so it is always reset.
            with self.redis_client.pipeline() as pipe:
                pipe.publish(
                    "coinbase:updates:all",
                    json.dumps({
                        "product_id": product_id, 
                        "price_data": price_data
                    }),
                )
                pipe.execute()
            # Only keep the latest price per product; bounded by #products.
            self.last_prices[product_id] = price_data
        except Exception as e:
            logger.error("Failed to publish to Redis: %s", e)
    
    async def run(self):
        """Main run loop with auto-restart and dynamic subscription"""
        import websockets
        
        while self.running:
            try:
                # Check if resubscribe was requested during connection
                if self._resubscribe_requested:
                    self._resubscribe_requested = False
                    if self.websocket:
                        try:
                            await self.websocket.close()
                            self.websocket = None
                            self._loop = None
                        except:
                            pass
                    # Wait a moment before reconnecting
                    await asyncio.sleep(1)
                
                # Ensure websocket is connected before entering message loop
                if not self.websocket:
                    logger.info("Connecting to WebSocket...")
                    connected = await self.connect()
                    if not connected:
                        logger.warning("Failed to connect, retrying...")
                        await asyncio.sleep(self.reconnect_delay)
                        continue
                
                # Check again if websocket is None before async for
                if not self.websocket:
                    logger.warning("WebSocket is None, skipping message loop")
                    await asyncio.sleep(self.reconnect_delay)
                    continue
                
                # Process messages only if websocket exists
                async for message in self.websocket:
                    # Handle pong responses
                    try:
                        data = json.loads(message)
                        if data.get('type') == 'pong':
                            continue
                    except:
                        pass
                    
                    # Process market data
                    await self.process_message(message)
                    
                    # Check for resubscribe request during message processing
                    if self._resubscribe_requested:
                        logger.info("Resubscribe requested, breaking message loop")
                        break
                    
            except websockets.ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}. Reconnecting...")
                self.websocket = None
                self._loop = None
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
                    
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.websocket = None
                self._loop = None
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
    
    async def process_message(self, message: str):
        """Process incoming message and publish to Redis"""
        try:
            data = json.loads(message)
            # Handle ticker messages (from channel format)
            if data.get('type') == 'ticker':
                product_id = data.get('product_id')
                if product_id:
                    price_data = {
                        'time_received': str(datetime.now()),
                        **data,
                    }
                    self.publish_price(product_id, price_data)
                        
            elif data.get('channel') == 'heartbeats':
                logger.debug("Heartbeat received")
                
            elif data.get('channel') == 'subscriptions':
                logger.info(f"Subscription confirmed: {data}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def start(self):
        """Start the WebSocket connection"""
        self.running = True
        service_state.running = True
        service_state.ws_status = 'connected'
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self.run())
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            loop.close()
        
    def stop(self):
        """
        Stop cleanly. Cancels the run() task on its own loop instead of closing
        the websocket from a foreign loop.
        """
        logger.info("Stopping WebSocket connection...")
        self.running = False
        service_state.running = False
        service_state.ws_status = "stopped"

        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._shutdown_async(), loop)
                try:
                    fut.result(timeout=5)
                except TimeoutError:
                    logger.warning("Timed out waiting for graceful shutdown")
            except Exception:
                logger.exception("Error during graceful shutdown")

        self.websocket = None
        self._loop = None
        logger.info("WebSocket stop complete")


    async def _shutdown_async(self):
        """Close the websocket from within its own loop."""
        ws = self.websocket
        if ws is None:
            return
        try:
            await ws.close(code=1000, reason="Normal closure")
        except Exception:
            logger.exception("Error closing websocket")
    
    async def _close_websocket_safely(self):
        """Safely close the websocket connection"""
        if not self.websocket:
            return
        
        try:
            # Send close frame with proper code
            await self.websocket.close(code=1000, reason="Normal closure")
            logger.info("WebSocket closed gracefully")
        except Exception as e:
            logger.warning(f"Error during websocket close: {e}")
            # Try to close without handshake
            if self.websocket:
                try:
                    await self.websocket.close()
                except:
                    pass


class CoinbaseWebSocketService:
    """
    Standalone WebSocket service that publishes price data to Redis.
    """
    
    def __init__(self):
        self.redis_client = None
        self.handler = None
        
    def connect_redis(self):
        """Connect to Redis with connection pooling"""
        try:
            # Use connection pool for better performance
            pool = redis.ConnectionPool(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                max_connections=10
            )
            self.redis_client = redis.Redis(connection_pool=pool)
            
            # Test connection
            self.redis_client.ping()
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False
    
    def run(self):
        """Main service entry point"""
        logger.info("Starting Coinbase WebSocket Service")
        
        # Connect to Redis
        if not self.connect_redis():
            logger.error("Cannot start without Redis connection")
            sys.exit(1)
        
        # Set up signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            logger.info("Shutdown signal received")
            if self.handler:
                self.handler.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize and run WebSocket handler
        self.handler = CoinbaseWebSocketHandlerAdvanced(
            product_ids=service_state.products,
            redis_client=self.redis_client
        )
        service_state.handler = self.handler
        
        service_state.running = True
        self.handler.start()
    
    def stop(self):
        """Stop the service"""
        logger.info("Stopping WebSocket service")
        if self.handler:
            self.handler.stop()
        
        if self.redis_client:
            try:
                self.redis_client.close()
            except:
                pass


def start_http_server(server_holder: dict):
    server_address = ("0.0.0.0", WEBSOCKET_HEALTH_PORT)
    httpd = HTTPServer(server_address, HealthHandler)
    httpd.daemon_threads = True
    httpd.timeout = 1
    httpd.allow_reuse_address = True
    server_holder["httpd"] = httpd
    logger.info("Control server listening on port %s", WEBSOCKET_HEALTH_PORT)
    try:
        httpd.serve_forever(poll_interval=1)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    server_holder = {}
    http_thread = Thread(
        target=start_http_server, args=(server_holder,), daemon=True
    )
    http_thread.start()

    service = CoinbaseWebSocketService()
    try:
        service.run()
    finally:
        httpd = server_holder.get("httpd")
        if httpd is not None:
            httpd.shutdown()