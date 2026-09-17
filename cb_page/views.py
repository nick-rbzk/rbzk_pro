"""
Django views for real-time price updates using Redis pub/sub.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Optional

import requests
from asgiref.sync import sync_to_async
from django.db.models import Q
from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from cb_mark.models import Trade, TradeState, TradingPair
from .redis_pubsub import get_price_subscriber
from .websocket_client import price_client


logger = logging.getLogger(__name__)

DOMAIN = os.environ.get("DOMAIN")

SSE_QUEUE_MAXSIZE = 1000
SSE_POLL_INTERVAL = 0.05
SSE_HEARTBEAT_INTERVAL = 15


@csrf_exempt
async def subscribe_to_updates(request, product_id: Optional[str] = None):
    """
    SSE endpoint. Uses the shared subscriber; filters by product_id in the
    callback. Bounded queue protects against a slow client.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=SSE_QUEUE_MAXSIZE)

    # Same subscriber for everyone.
    subscriber = await sync_to_async(get_price_subscriber)()

    def _enqueue(data: dict) -> None:
        # Filter at the callback layer, since the subscriber sends all products.
        if product_id:
            ticker = data.get("price_data") or {}
            if ticker.get("product_id") != product_id:
                return
        try:
            loop.call_soon_threadsafe(_put_nowait_drop_oldest, queue, data)
        except RuntimeError:
            # Loop closed — SSE connection is gone.
            pass

    def _put_nowait_drop_oldest(q: asyncio.Queue, item):
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass

    subscriber.add_callback(_enqueue)

    async def event_stream():
        try:
            yield f"event: connected\ndata: {json.dumps({'type': 'connected'})}\n\n"

            if product_id:
                latest = await sync_to_async(price_client.get_latest_price)(product_id)
                if latest:
                    yield f"data: {json.dumps({'type': 'initial', 'data': latest})}\n\n"
            else:
                all_prices = await sync_to_async(price_client.get_all_prices)()
                if all_prices:
                    yield f"data: {json.dumps({'type': 'initial', 'data': all_prices})}\n\n"

            last_heartbeat = time.monotonic()
            while True:
                drained = 0
                while drained < 100:
                    try:
                        msg = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    yield f"data: {json.dumps({'type': 'update', 'data': msg})}\n\n"
                    drained += 1

                now = time.monotonic()
                if now - last_heartbeat > SSE_HEARTBEAT_INTERVAL:
                    yield f"event: heartbeat\ndata: {json.dumps({'type': 'heartbeat'})}\n\n"
                    last_heartbeat = now

                await asyncio.sleep(SSE_POLL_INTERVAL)

        except asyncio.CancelledError:
            logger.info("SSE client disconnected (cancelled)")
            raise
        except GeneratorExit:
            logger.info("SSE client disconnected (generator closed)")
            raise
        except Exception:
            logger.exception("SSE stream error")
            raise
        finally:
            try:
                subscriber.remove_callback(_enqueue)
            except Exception:
                logger.exception("Failed to remove SSE callback")

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Connection"] = "keep-alive"
    return response


def websocket_service_status(request):
    service_url = os.environ.get(
        "WEBSOCKET_SERVICE_URL", "http://websocket-service:8080"
    )
    try:
        response = requests.get(f"{service_url}/health", timeout=5)
        if response.status_code == 200:
            return JsonResponse({"status": True})
        return JsonResponse({"status": "unhealthy"}, status=500)
    except requests.exceptions.ConnectionError:
        return JsonResponse({"status": "unreachable"}, status=503)


class TradingDashboardView(TemplateView):
    template_name = "price_dash.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["trading_pairs"] = TradingPair.objects.filter(is_active=True)
        context["open_trades"] = Trade.objects.filter(state=TradeState.OPEN)

        closed_trades = Trade.objects.filter(state=TradeState.CLOSED).exclude(
            Q(buy_signal=None) & Q(sell_signal=None)
        )
        formatted = []
        for trade in closed_trades:
            formatted.append({
                "ticker_symbol": trade.ticker_symbol,
                "type": trade.type,
                "enter_price": round(trade.enter_price, trade.trading_pair.decimal_places) if trade.stop_loss_price else 0,
                "stop_loss_price": round(trade.stop_loss_price, trade.trading_pair.decimal_places) if trade.stop_loss_price else 0,
                "exit_price": round(trade.exit_price, trade.trading_pair.decimal_places) if trade.stop_loss_price else 0,
                "profit_loss": round(trade.profit_loss, trade.trading_pair.decimal_places) if trade.stop_loss_price else 0,
                "created_at": trade.created_at,
            })
        context["closed_trades"] = formatted
        context["domain"] = DOMAIN
        return context


class TradingPairsAPIView(View):
    def get(self, request):
        try:
            pairs = TradingPair.objects.all().order_by("ticker_symbol")
            trades = Trade.objects.filter(state=TradeState.OPEN)
            data = {
                "trading_pairs": [
                    {
                        "id": pair.id,
                        "ticker_symbol": pair.ticker_symbol,
                        "name": pair.name,
                        "is_active": pair.is_active,
                        "highest_10day": str(round(pair.highest_10day, pair.decimal_places)) if pair.highest_10day else None,
                        "highest_20day": str(round(pair.highest_20day, pair.decimal_places)) if pair.highest_20day else None,
                        "highest_55day": str(round(pair.highest_55day, pair.decimal_places)) if pair.highest_55day else None,
                        "lowest_10day": str(round(pair.lowest_10day, pair.decimal_places)) if pair.lowest_10day else None,
                        "lowest_20day": str(round(pair.lowest_20day, pair.decimal_places)) if pair.lowest_20day else None,
                        "lowest_55day": str(round(pair.lowest_55day, pair.decimal_places)) if pair.lowest_55day else None,
                    }
                    for pair in pairs
                ],
                "trades": [
                    {
                        "id": trade.id,
                        "ticker_symbol": trade.ticker_symbol,
                        "state": trade.state,
                        "type": trade.type,
                        "enter_price": str(round(trade.enter_price, trade.trading_pair.decimal_places)),
                        "stop_loss_price": str(round(trade.stop_loss_price, trade.trading_pair.decimal_places)),
                        "exit_price": str(round(trade.exit_price, trade.trading_pair.decimal_places)) if trade.exit_price else None,
                        "profit_loss": str(round(trade.profit_loss, trade.trading_pair.decimal_places)) if trade.profit_loss else None,
                        "dollar_amount": str(trade.dollar_amount) if trade.dollar_amount else None,
                        "num_shares": str(trade.num_shares) if trade.num_shares else None,
                        "created_at": trade.created_at.isoformat(),
                        "updated_at": trade.updated_at.isoformat(),
                    }
                    for trade in trades
                ],
            }
            return JsonResponse(data, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class UpdateTradingPairsAPIView(View):
    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        try:
            data = json.loads(request.body)
            selected_pairs = data.get("trading_pairs", [])
            if not isinstance(selected_pairs, list):
                return JsonResponse({
                    "success": False,
                    "message": "Invalid data format. Expected list of trading pairs.",
                }, status=400)

            all_pairs = TradingPair.objects.all()
            for pair in all_pairs:
                pair.is_active = pair.ticker_symbol in selected_pairs
                pair.save()

            self._send_to_websocket_service(selected_pairs)
            return JsonResponse({
                "success": True,
                "message": f"Successfully updated {len(selected_pairs)} trading pairs.",
                "active_pairs": selected_pairs,
            }, status=200)

        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": "Invalid JSON data."}, status=400)
        except Exception as e:
            return JsonResponse({
                "success": False,
                "message": f"Error updating trading pairs: {e}",
            }, status=500)

    def _send_to_websocket_service(self, trading_pairs):
        try:
            response = requests.post(
                "http://websocket-service:8080/resubscribe",
                json={"action": "update_pairs", "products": trading_pairs},
                timeout=5,
            )
            if response.status_code != 200:
                logger.error("WS service resubscribe failed: %s", response.status_code)
        except Exception as e:
            logger.error("Error sending to WS service: %s", e)