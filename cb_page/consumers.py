"""
Django Channels WebSocket consumer for real-time price updates.

Uses the shared RedisPriceSubscriber (see redis_pubsub.py). Each connection
registers a bounded asyncio.Queue-backed callback and removes it on
disconnect, so no per-connection Redis client, thread, or socket is leaked.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from channels.generic.websocket import AsyncWebsocketConsumer

from .redis_pubsub import get_price_subscriber


logger = logging.getLogger(__name__)

# Per-connection queue cap. If the client can't keep up, we drop the oldest.
WS_QUEUE_MAXSIZE = 500

# How often the consumer task wakes to drain the queue.
WS_POLL_INTERVAL = 0.05


class PriceConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that forwards Redis price updates to the client.

    Implementation note: we do NOT open our own Redis connection per
    connection. The shared subscriber fans out to all consumers, and each
    consumer filters + enqueues into a bounded asyncio.Queue.
    """

    async def connect(self):
        self.product_id: Optional[str] = (
            self.scope["url_route"]["kwargs"].get("product_id")
        )
        self.room_group_name = (
            f"price_{self.product_id}" if self.product_id else "price_all"
        )

        await self.channel_layer.group_add(
            self.room_group_name, self.channel_name
        )
        await self.accept()

        loop = asyncio.get_running_loop()
        self._loop = loop
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=WS_QUEUE_MAXSIZE)
        self._closed = False

        subscriber = await asyncio.get_running_loop().run_in_executor(
            None, get_price_subscriber
        )

        def _on_message(data: dict) -> None:
            if self._closed:
                return
            if self.product_id:
                ticker = data.get("price_data") or {}
                if ticker.get("product_id") != self.product_id:
                    return
            try:
                loop.call_soon_threadsafe(self._put_nowait_drop_oldest, data)
            except RuntimeError:
                pass

        self._on_message = _on_message
        subscriber.add_callback(_on_message)
        self._subscriber = subscriber

        self._drain_task = asyncio.create_task(self._drain_loop())

    def _put_nowait_drop_oldest(self, item) -> None:
        q = self._queue
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass

    async def _drain_loop(self) -> None:
        try:
            while not self._closed:
                drained = 0
                while drained < 50:
                    try:
                        msg = self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    try:
                        await self.send(text_data=json.dumps({
                            "type": "update",
                            "data": msg,
                        }))
                    except Exception:
                        # Client probably gone; let disconnect handle cleanup.
                        return
                    drained += 1
                await asyncio.sleep(WS_POLL_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("WS drain loop error")

    async def disconnect(self, close_code):
        self._closed = True

        # Remove callback first so no new messages are enqueued.
        try:
            self._subscriber.remove_callback(self._on_message)
        except Exception:
            logger.exception("Failed to remove WS callback")

        # Cancel the drain task if still running.
        task = getattr(self, "_drain_task", None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        await self.channel_layer.group_discard(
            self.room_group_name, self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"error": "Invalid JSON"}))
            return

        if data.get("command") == "subscribe":
            product_id = data.get("product_id")
            if product_id:
                new_group = f"price_{product_id}"
                await self.channel_layer.group_add(new_group, self.channel_name)
                await self.send(text_data=json.dumps({
                    "type": "subscribed",
                    "product_id": product_id,
                }))

    async def price_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "update",
            "data": json.loads(event["data"]),
        }))