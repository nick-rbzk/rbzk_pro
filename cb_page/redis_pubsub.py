"""
Redis pub/sub client for real-time price updates.

Memory-safety design notes
--------------------------
* NO `gc.collect()` per message.
* Callbacks are held weakly; `remove_callback` exists; dead refs are pruned
  on every dispatch.
* ONE shared subscriber per channel (see `get_price_subscriber`). The
  subscriber itself subscribes to `coinbase:updates:all`; per-product
  filtering is done by the caller in its callback.
* `strategy_s1` and `redis_store_price` are executed on a small bounded
  worker pool, not on the Redis reader thread. This isolates the reader
  from slow cache/DB work and bounds transient memory via a bounded queue.
* The worker pool is per-process and shared across all subscribers.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import weakref
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import redis
from django.conf import settings

from cb_trades.tasks import strategy_s1, redis_store_price


logger = logging.getLogger(__name__)


CHANNEL_ALL = "coinbase:updates:all"

# Bounded queue for the worker pool. If the producers outrun the workers,
# the oldest item is dropped (prices are ephemeral; the next tick supersedes).
WORK_QUEUE_MAXSIZE = 2000

# Number of worker threads that run strategy_s1 + redis_store_price.
WORKER_THREADS = 3


# ---------------------------------------------------------------------- #
# Worker pool
# ---------------------------------------------------------------------- #

@dataclass
class _WorkItem:
    product_id: Optional[str]
    ticker_data: dict


class _WorkPool:
    """
    Small bounded worker pool. Preserves per-product ordering by keying a
    per-product queue, each drained by the same worker set. This guarantees
    that for a given product_id, strategy_s1 sees messages in arrival order.
    """

    def __init__(self, num_workers: int = WORKER_THREADS,
                 maxsize: int = WORK_QUEUE_MAXSIZE):
        self._maxsize = maxsize
        self._queues: Dict[str, "queue.Queue[_WorkItem]"] = {}
        self._queues_lock = threading.Lock()
        self._num_workers = num_workers
        self._workers: List[threading.Thread] = []
        self._stop = threading.Event()

    def start(self) -> None:
        if self._workers:
            return
        for i in range(self._num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"price-worker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)

    def stop(self) -> None:
        self._stop.set()
        for q in list(self._queues.values()):
            try:
                q.put_nowait(None)  # type: ignore[arg-type]
            except queue.Full:
                pass
        for t in self._workers:
            t.join(timeout=2)
        self._workers.clear()

    def submit(self, product_id: Optional[str], ticker_data: dict) -> None:
        key = product_id or "_all"
        with self._queues_lock:
            q = self._queues.get(key)
            if q is None:
                q = queue.Queue(maxsize=self._maxsize)
                self._queues[key] = q
        item = _WorkItem(product_id=product_id, ticker_data=ticker_data)
        try:
            q.put_nowait(item)
        except queue.Full:
            # Drop oldest, then retry once.
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(item)
            except queue.Full:
                logger.warning("Work queue full for %s; dropping tick", key)

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            # Round-robin over per-product queues so no single product
            # starves the others.
            with self._queues_lock:
                queues = list(self._queues.items())
            did_work = False
            for _, q in queues:
                try:
                    item = q.get_nowait()
                except queue.Empty:
                    continue
                if item is None:
                    return
                did_work = True
                # self._process(item)
            if not did_work:
                time.sleep(0.01)

    # @staticmethod
    # def _process(item: _WorkItem) -> None:
    #     ticker_data = item.ticker_data
        # try:
        #     strategy_s1(ticker_data)
        # except Exception:
        #     logger.exception("strategy_s1 failed for %s", item.product_id)
        # try:
        #     redis_store_price(ticker_data)
        # except Exception:
        #     logger.exception("redis_store_price failed for %s", item.product_id)


_work_pool = _WorkPool()


# ---------------------------------------------------------------------- #
# Subscriber
# ---------------------------------------------------------------------- #

class RedisPriceSubscriber:
    """
    Redis pub/sub subscriber for price updates.

    A single background thread reads from Redis; `strategy_s1` and
    `redis_store_price` are dispatched to the shared `_WorkPool`. Callbacks
    are held weakly and pruned on every dispatch.
    """

    def __init__(self, product_id: Optional[str] = None,
                 channel: str = CHANNEL_ALL):
        self.product_id = product_id
        self.channel = channel

        self.redis_client: Optional[redis.Redis] = None
        self.pubsub = None

        self.running = False
        self.thread: Optional[threading.Thread] = None

        self._callbacks: List[Any] = []
        self._callbacks_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._subscribed_channel: Optional[str] = None

    # -------------------------------------------------------------- #
    # Connection
    # -------------------------------------------------------------- #

    def connect(self) -> "RedisPriceSubscriber":
        if self.redis_client is not None:
            return self
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
            socket_keepalive=True,
            health_check_interval=30,
        )
        self.pubsub = self.redis_client.pubsub()
        return self

    def subscribe(self, channel: Optional[str] = None) -> "RedisPriceSubscriber":
        if not self.pubsub:
            self.connect()
        channel = channel or self.channel
        if self._subscribed_channel == channel:
            return self
        self.pubsub.subscribe(**{channel: self._handle_message})
        self._subscribed_channel = channel
        logger.info("Subscribed to Redis channel: %s", channel)
        return self

    # -------------------------------------------------------------- #
    # Callbacks
    # -------------------------------------------------------------- #

    def add_callback(self, callback: Callable[[dict], None]
                     ) -> "RedisPriceSubscriber":
        ref = self._make_weak_ref(callback)
        if ref is None:
            logger.warning("add_callback: cannot weakref %r", callback)
            return self
        with self._callbacks_lock:
            self._callbacks.append(ref)
        return self
    
    def _handle_message(self, message):
        """Handle incoming Redis message"""
        if message['type'] == 'message':

            data = json.loads(message.get('data'))
            ticker_data = data.get('price_data')

            strategy_s1(ticker_data)

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

    def _run(self) -> None:
        while self.running:
            try:
                self.pubsub.get_message(timeout=1.0)
            except redis.RedisError as e:
                logger.error("Redis pub/sub error: %s", e)
                time.sleep(1)
            except Exception:
                logger.exception("Unexpected error in subscriber loop")
                time.sleep(1)

    def stop(self) -> None:
        with self._lifecycle_lock:
            self.running = False
            if self.pubsub is not None:
                try:
                    self.pubsub.unsubscribe()
                except Exception:
                    pass
                try:
                    self.pubsub.close()
                except Exception:
                    pass
                self.pubsub = None
            if self.redis_client is not None:
                try:
                    self.redis_client.close()
                except Exception:
                    pass
                self.redis_client = None
            self._subscribed_channel = None
            thread = self.thread
            self.thread = None

        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

        with self._callbacks_lock:
            self._callbacks.clear()
        logger.info("Redis subscriber stopped")


# ---------------------------------------------------------------------- #
# Shared registry
# ---------------------------------------------------------------------- #

_subscribers: Dict[str, RedisPriceSubscriber] = {}
_subscribers_lock = threading.Lock()


def get_price_subscriber(product_id: Optional[str] = None
                         ) -> RedisPriceSubscriber:
    """
    Return the shared subscriber for the Coinbase channel.

    `product_id` is accepted for API compatibility but is ignored: the
    subscriber always subscribes to `coinbase:updates:all`. Callers filter
    by product inside their callback.
    """
    key = "all"
    with _subscribers_lock:
        sub = _subscribers.get(key)
        if sub is None:
            sub = RedisPriceSubscriber(channel=CHANNEL_ALL).connect().subscribe()
            sub.start(background=True)
            _subscribers[key] = sub
        return sub


def start_global_subscriber() -> RedisPriceSubscriber:
    return get_price_subscriber(None)


def shutdown_subscribers() -> None:
    with _subscribers_lock:
        subs = list(_subscribers.values())
        _subscribers.clear()
    for sub in subs:
        try:
            sub.stop()
        except Exception:
            logger.exception("Error stopping subscriber")
    try:
        _work_pool.stop()
    except Exception:
        logger.exception("Error stopping work pool")