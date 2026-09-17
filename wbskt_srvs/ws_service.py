#!/usr/bin/env python3
"""
Standalone WebSocket service for Coinbase price streaming.

This service:
  * connects to Coinbase's public ticker feed,
  * runs `strategy_s1` and `redis_store_price` in-process for every tick,
  * publishes the raw tick to Redis for downstream consumers (SSE, Channels).

Processing model
----------------
A single asyncio task reads from the Coinbase websocket. Each ticker message
is dispatched to a bounded per-product queue, drained by a small thread pool.
This keeps the asyncio loop responsive (no DB/cache work inline) while
preserving per-product ordering for the strategy.

The `web` container must NOT run strategy_s1 / redis_store_price — it should
only consume the Redis channel and fan out to SSE/WebSocket clients. See
redis_pubsub.py in the web container.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Full, Queue
from threading import Thread
from typing import Dict, List, Optional
from urllib.parse import urlparse

import django
import redis
from websockets.extensions import permessage_deflate

from config import (
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    PRODUCT_IDS,
    WEBSOCKET_HEALTH_PORT,
)


# --------------------------------------------------------------------------- #
# Django bootstrap
# --------------------------------------------------------------------------- #
# strategy_s1 / redis_store_price depend on Django models and cache. We must
# call django.setup() before importing them. DJANGO_SETTINGS_MODULE should be
# set in the container env (e.g. rbzk.settings).

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rbzk.settings")
try:
    django.setup()
except Exception:  # pragma: no cover
    # If Django isn't importable in this image, the service can still stream
    # to Redis, but strategy/store will be disabled.
    logging.getLogger(__name__).exception(
        "Django setup failed; strategy_s1 / redis_store_price will be disabled"
    )


# --------------------------------------------------------------------------- #
# Strategy / store integration
# --------------------------------------------------------------------------- #
# These imports pull in Django models. If django.setup() failed above, this
# will raise; we catch and disable rather than crash the service.

try:
    from cb_trades.tasks import strategy_s1, redis_store_price
    _STRATEGY_AVAILABLE = True
except Exception as e:  # pragma: no cover
    print(e)
    print("-----------------------NOT available---------------")
    strategy_s1 = None          # type: ignore[assignment]
    redis_store_price = None    # type: ignore[assignment]
    _STRATEGY_AVAILABLE = False


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Tunables
# --------------------------------------------------------------------------- #
# Bounded work queue for the per-product processor. If the producers outrun
# the consumer, oldest ticks are dropped (the next tick supersedes them for
# the strategy, and the cache bin keeps a bounded window anyway).
WORK_QUEUE_MAXSIZE = 2000

# Number of worker threads that run strategy_s1 + redis_store_price.
WORKER_THREADS = 3

# How often the worker loop wakes if there is no work.
WORKER_IDLE_SLEEP = 0.005


# --------------------------------------------------------------------------- #
# Service state
# --------------------------------------------------------------------------- #
class ServiceState:
    """Thread-safe service state. Persists across HTTP requests."""

    _lock = threading.RLock()

    def __init__(self):
        self._running = False
        self._products = set(PRODUCT_IDS)
        self._ws_status = "stopped"
        self._handler = None
        # Lives on the state object, not the per-request HealthHandler.
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

    def update_products(self, new_products) -> bool:
        with self._lock:
            old_products = set(self._products)
            new_set = set(new_products)
            if new_set != old_products:
                self._products = new_set
                return True
            return False

    def try_begin_resubscribe(self) -> bool:
        with self._lock:
            if self._resub_inflight.is_set():
                return False
            self._resub_inflight.set()
            return True

    def end_resubscribe(self) -> None:
        with self._lock:
            self._resub_inflight.clear()


service_state = ServiceState()


# --------------------------------------------------------------------------- #
# Per-product work processor
# --------------------------------------------------------------------------- #
class TickProcessor:
    """
    Bounded, per-product FIFO processor.

    - One queue per product_id, so ordering is preserved per product.
    - A fixed pool of worker threads drains the queues round-robin so no
      single product starves the others.
    - Bounded: if a product's queue is full, oldest tick is dropped.
    """

    def __init__(self, num_workers: int = WORKER_THREADS,
                 maxsize: int = WORK_QUEUE_MAXSIZE):
        self._maxsize = maxsize
        self._queues: Dict[str, Queue] = {}
        self._queues_lock = threading.Lock()
        self._num_workers = num_workers
        self._workers: List[Thread] = []
        self._stop = threading.Event()
        self._enabled = _STRATEGY_AVAILABLE

    def start(self) -> None:
        if self._workers:
            return
        if not self._enabled:
            logger.warning(
                "TickProcessor disabled: strategy_s1 / redis_store_price "
                "not importable"
            )
            return
        self._stop.clear()  
        for i in range(self._num_workers):
            t = Thread(
                target=self._worker_loop,
                name=f"tick-worker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)
        logger.info("TickProcessor started with %d workers", self._num_workers)

    def stop(self) -> None:
        self._stop.set()
        for q in list(self._queues.values()):
            try:
                q.put_nowait(None)
            except Full:
                pass
        for t in self._workers:
            t.join(timeout=2)
        self._workers.clear()

    def submit(self, product_id: str, ticker_data: dict) -> None:
        if not self._enabled:
            return
        with self._queues_lock:
            q = self._queues.get(product_id)
            if q is None:
                q = Queue(maxsize=self._maxsize)
                self._queues[product_id] = q
        try:
            q.put_nowait(ticker_data)
        except Full:
            # Drop oldest, retry once.
            try:
                q.get_nowait()
            except Empty:
                pass
            try:
                q.put_nowait(ticker_data)
            except Full:
                logger.warning("Tick queue full for %s; dropping tick", product_id)

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            with self._queues_lock:
                queues = list(self._queues.items())
            did_work = False
            for _, q in queues:
                try:
                    item = q.get_nowait()
                except Empty:
                    continue
                if item is None:
                    return
                did_work = True
                self._process(item)
            if not did_work:
                time.sleep(WORKER_IDLE_SLEEP)

    @staticmethod
    def _process(ticker_data: dict) -> None:
        try:
            strategy_s1(ticker_data)  
        except Exception:
            logger.exception("strategy_s1 failed")
        try:
            redis_store_price(ticker_data)  
        except Exception:
            logger.exception("redis_store_price failed")


_tick_processor = TickProcessor()


# --------------------------------------------------------------------------- #
# HTTP control / health
# --------------------------------------------------------------------------- #
class HealthHandler(BaseHTTPRequestHandler):
    """
    HTTP handler for health checks and control endpoints.

    Do NOT override __init__: a new HealthHandler instance is created by
    socketserver for every request; per-request state belongs on ServiceState.
    """

    def _send_json_response(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _validate_product_ids(self, products: List[str]) -> bool:
        pattern = re.compile(r"^[A-Z]{2,6}-[A-Z]{2,6}$")
        return all(pattern.match(p) for p in products)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json_response(200, {
                "status": "running" if service_state.running else "stopped",
                "products": service_state.products,
                "connections": service_state.ws_status,
                "strategy_enabled": _STRATEGY_AVAILABLE,
                "timestamp": int(time.time()),
            })
        else:
            self._send_json_response(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json_response(400, {"error": "Invalid JSON"})
            return

        if path == "/start":
            self._handle_start(data)
        elif path == "/stop":
            self._handle_stop()
        elif path == "/resubscribe":
            self._handle_resubscribe(data)
        else:
            self._send_json_response(404, {"error": "Not found"})

    def _handle_start(self, data: dict):
        if service_state.running:
            self._send_json_response(200, {
                "status": "already_running",
                "products": service_state.products,
                "message": "Service is already running",
            })
            return

        products = data.get("products")
        if products:
            if not self._validate_product_ids(products):
                self._send_json_response(400, {
                    "error": "Invalid product IDs format. Use format like BTC-USD, ETH-USD",
                })
                return
            service_state.products = products

        def start_service():
            try:
                service = CoinbaseWebSocketService()
                service_state.handler = service
                service.run()
            except Exception:
                logger.exception("WebSocket service crashed")
            finally:
                service_state.running = False
                service_state.ws_status = "stopped"

        Thread(target=start_service, daemon=True).start()
        time.sleep(1)  # grace period; caller can poll /health

        self._send_json_response(200, {
            "status": "starting",
            "products": service_state.products,
            "message": "WebSocket service starting",
        })

    def _handle_stop(self):
        if not service_state.running:
            self._send_json_response(200, {
                "status": "already_stopped",
                "message": "Service is already stopped",
            })
            return

        handler = service_state.handler
        if handler:
            try:
                handler.stop()
            except Exception:
                logger.exception("Error stopping handler")
            service_state.handler = None

        service_state.running = False
        service_state.ws_status = "stopped"

        self._send_json_response(200, {
            "status": "stopped",
            "message": "WebSocket service stopped successfully",
        })

    def _handle_resubscribe(self, data: dict):
        products = data.get("products")

        if not products:
            self._send_json_response(400, {"error": "Products list required"})
            return

        if not self._validate_product_ids(products):
            self._send_json_response(400, {
                "error": "Invalid product IDs format. Use format like BTC-USD, ETH-USD",
            })
            return

        if not service_state.running or not service_state.handler:
            service_state.products = products
            self._send_json_response(200, {
                "status": "products_updated",
                "products": products,
                "message": "Products updated, start service to apply",
            })
            return

        changed = service_state.update_products(products)
        if not changed:
            self._send_json_response(200, {
                "status": "no_change",
                "products": products,
                "message": "Products already subscribed",
            })
            return

        if not service_state.try_begin_resubscribe():
            self._send_json_response(202, {"status": "in_progress"})
            return

        handler = service_state.handler

        def do_resubscribe():
            try:
                loop = getattr(handler, "_loop", None)
                if loop is not None and loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        handler.resubscribe(products), loop
                    )
                else:
                    tmp_loop = asyncio.new_event_loop()
                    try:
                        asyncio.set_event_loop(tmp_loop)
                        tmp_loop.run_until_complete(handler.resubscribe(products))
                    finally:
                        tmp_loop.close()
            except Exception:
                logger.exception("Resubscribe failed")
            finally:
                service_state.end_resubscribe()

        Thread(target=do_resubscribe, daemon=True).start()

        self._send_json_response(200, {
            "status": "resubscribing",
            "products": products,
            "message": "Resubscribing to new products",
        })

    def log_message(self, format, *args):
        pass  # suppress HTTP server access logs


# --------------------------------------------------------------------------- #
# Coinbase WebSocket handler
# --------------------------------------------------------------------------- #
class CoinbaseWebSocketHandlerAdvanced:
    """
    WebSocket client for Coinbase's ticker feed.

    For each ticker message:
      1. dispatch to the TickProcessor (runs strategy_s1 / redis_store_price),
      2. publish the raw tick to Redis channel `coinbase:updates:all` so the
         web container can fan out to SSE/WebSocket clients.
    """

    def __init__(self, product_ids: Optional[List[str]] = None, redis_client=None):
        self.product_ids = set(product_ids or PRODUCT_IDS)
        self._current_subscription = set(self.product_ids)
        self.running = False
        self.websocket = None
        self.heartbeat_interval = 30
        self.reconnect_delay = 1
        self.redis_client = redis_client
        self.last_prices: Dict[str, dict] = {}
        self._resubscribe_requested = False
        self._new_products: Optional[set] = None
        self._lock = threading.RLock()
        self._connection_attempts = 0
        self._max_connection_attempts = 10
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # -------------------------------------------------------------- #
    # Connection
    # -------------------------------------------------------------- #
    async def connect(self) -> bool:
        import websockets

        uri = "wss://ws-feed.exchange.coinbase.com"

        compression_extensions = [
            permessage_deflate.ClientPerMessageDeflateFactory(
                client_max_window_bits=15,
                compress_settings={"memLevel": 5, "level": 3},
            )
        ]
        extra_headers = {
            "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits=15",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "CoinbaseWebSocketClient/1.0",
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
                max_size=2 ** 23,
                max_queue=32,
            )
            self._loop = asyncio.get_running_loop()
            logger.info("Connected to Coinbase with compression enabled")
            self._connection_attempts = 0
            await self._send_subscription()
            return True
        except Exception as e:
            logger.error("Failed to connect to Coinbase: %s", e)
            self.websocket = None
            self._loop = None
            self._connection_attempts += 1
            if self._connection_attempts >= self._max_connection_attempts:
                logger.critical(
                    "Max connection attempts (%d) reached; giving up",
                    self._max_connection_attempts,
                )
                self.running = False
                return False
            return False

    async def _send_subscription(self) -> None:
        if not self.websocket:
            return
        products = list(self.product_ids)
        if not products:
            logger.warning("No products to subscribe to")
            return
        try:
            subscribe_message = {
                "type": "subscribe",
                "channels": [{"name": "ticker", "product_ids": products}],
            }
            await self.websocket.send(json.dumps(subscribe_message))
            logger.info("Subscribed to %s", products)
            self._current_subscription = set(products)
        except Exception as e:
            logger.error("Failed to send subscription: %s", e)
            raise

    async def resubscribe(self, new_products: List[str]) -> None:
        with self._lock:
            new_set = set(new_products)
            if new_set == self.product_ids:
                logger.info("Products unchanged, skipping resubscribe")
                return
            self.product_ids = new_set
            self._resubscribe_requested = True
            self._new_products = new_set
            # Force reconnection; the run loop will see the flag and reconnect.
            if self.websocket:
                try:
                    await self._shutdown_async()
                except Exception:
                    logger.exception("Error closing websocket for resubscribe")
                self.websocket = None
                self._loop = None

    async def _shutdown_async(self) -> None:
        """Close the websocket from within its own loop."""
        ws = self.websocket
        if ws is None:
            return
        try:
            await ws.close(code=1000, reason="Normal closure")
        except Exception:
            logger.exception("Error closing websocket")

    # -------------------------------------------------------------- #
    # Publishing
    # -------------------------------------------------------------- #
    def publish_price(self, product_id: str, price_data: dict) -> None:
        if not self.redis_client:
            return
        try:
            with self.redis_client.pipeline() as pipe:
                pipe.publish(
                    "coinbase:updates:all",
                    json.dumps({
                        "product_id": product_id,
                        "price_data": price_data,
                    }),
                )
                pipe.execute()
            # Bounded by number of products.
            self.last_prices[product_id] = price_data
        except Exception as e:
            logger.error("Failed to publish to Redis: %s", e)

    # -------------------------------------------------------------- #
    # Run loop
    # -------------------------------------------------------------- #
    async def run(self) -> None:
        import websockets

        while self.running:
            try:
                if self._resubscribe_requested:
                    self._resubscribe_requested = False
                    if self.websocket:
                        try:
                            await self.websocket.close()
                        except Exception:
                            pass
                        self.websocket = None
                        self._loop = None
                    await asyncio.sleep(1)

                if not self.websocket:
                    logger.info("Connecting to WebSocket...")
                    if not await self.connect():
                        logger.warning("Failed to connect, retrying...")
                        await asyncio.sleep(self.reconnect_delay)
                        continue

                if not self.websocket:
                    await asyncio.sleep(self.reconnect_delay)
                    continue

                async for message in self.websocket:
                    try:
                        data = json.loads(message)
                        if data.get("type") == "pong":
                            continue
                    except (TypeError, ValueError):
                        pass

                    await self.process_message(message)

                    if self._resubscribe_requested:
                        logger.info("Resubscribe requested, breaking message loop")
                        break

            except websockets.ConnectionClosed as e:
                logger.warning("Connection closed: %s. Reconnecting...", e)
                self.websocket = None
                self._loop = None
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
            except Exception as e:
                logger.error("WebSocket error: %s", e)
                self.websocket = None
                self._loop = None
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)

    async def process_message(self, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            logger.error("JSON decode error: %s", e)
            return

        msg_type = data.get("type")
        if msg_type == "ticker":
            product_id = data.get("product_id")
            if not product_id:
                return
            price_data = {
                "time_received": str(datetime.now()),
                **data,
            }
            # 1) Dispatch to strategy + store workers.
            _tick_processor.submit(product_id, price_data)
            # 2) Fan out raw tick to Redis for downstream consumers.
            self.publish_price(product_id, price_data)
        elif data.get("channel") == "heartbeats":
            logger.debug("Heartbeat received")
        elif data.get("channel") == "subscriptions":
            logger.info("Subscription confirmed: %s", data)

    # -------------------------------------------------------------- #
    # Lifecycle
    # -------------------------------------------------------------- #
    def start(self) -> None:
        """Start the WebSocket connection. Blocks on the current thread."""
        self.running = True
        service_state.running = True
        service_state.ws_status = "connected"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run())
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            loop.close()

    def stop(self) -> None:
        """Stop cleanly; close the websocket on its own loop."""
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


# --------------------------------------------------------------------------- #
# Top-level service
# --------------------------------------------------------------------------- #
class CoinbaseWebSocketService:
    """Owns the Redis client, the handler, and the tick processor lifecycle."""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.handler: Optional[CoinbaseWebSocketHandlerAdvanced] = None

    def connect_redis(self) -> bool:
        try:
            pool = redis.ConnectionPool(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                max_connections=10,
            )
            self.redis_client = redis.Redis(connection_pool=pool)
            self.redis_client.ping()
            logger.info("Connected to Redis at %s:%s", REDIS_HOST, REDIS_PORT)
            return True
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            return False

    def run(self) -> None:
        logger.info("Starting Coinbase WebSocket Service")
        if not self.connect_redis():
            logger.error("Cannot start without Redis connection")
            sys.exit(1)

        # Start the strategy/store workers.
        _tick_processor.start()

        def signal_handler(sig, frame):
            logger.info("Shutdown signal received")
            try:
                if self.handler:
                    self.handler.stop()
            finally:
                _tick_processor.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self.handler = CoinbaseWebSocketHandlerAdvanced(
            product_ids=service_state.products,
            redis_client=self.redis_client,
        )
        service_state.handler = self.handler
        service_state.running = True
        self.handler.start()

    def stop(self) -> None:
        logger.info("Stopping WebSocket service")
        if self.handler:
            self.handler.stop()
        _tick_processor.stop()
        if self.redis_client:
            try:
                self.redis_client.close()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# HTTP server
# --------------------------------------------------------------------------- #
def start_http_server(server_holder: dict) -> None:
    httpd = ThreadingHTTPServer(("0.0.0.0", WEBSOCKET_HEALTH_PORT), HealthHandler)
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
    server_holder: Dict[str, object] = {}
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
            try:
                httpd.shutdown()
            except Exception:
                pass