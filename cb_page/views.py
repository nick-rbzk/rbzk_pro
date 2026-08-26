"""
Django views for real-time price updates using Redis pub/sub.
Supports Server-Sent Events (SSE) and WebSocket streaming.
"""

import json
import time
import logging
import asyncio
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from asgiref.sync import sync_to_async

from .redis_pubsub import get_price_subscriber, RedisPriceSubscriber
from .websocket_client import price_client

logger = logging.getLogger(__name__)


def get_latest_price(request, product_id):
    """Get latest price from Redis cache (published by WebSocket service)"""
    price_data = price_client.get_latest_price(product_id)
    
    if price_data:
        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'price': price_data.get('price'),
            'timestamp': price_data.get('timestamp')
        })
    else:
        return JsonResponse({
            'success': False,
            'error': f'No price data for {product_id}'
        }, status=404)


def get_all_prices(request):
    """Get all latest prices"""
    prices = price_client.get_all_prices()
    return JsonResponse({
        'success': True,
        'prices': prices,
        'timestamp': int(time.time())
    })


@csrf_exempt
async def subscribe_to_updates(request, product_id=None):
    """
    SSE endpoint with proper async iterator for ASGI.
    """
    
    async def event_stream():
        subscriber = await sync_to_async(
            lambda: RedisPriceSubscriber(product_id).connect().subscribe()
        )()
        
        messages = []
        
        def callback(data):
            messages.append(data)
        
        subscriber.add_callback(callback)
        await sync_to_async(subscriber.start)(background=True)
        
        try:
            # Connection confirmation
            yield f"event: connected\ndata: {json.dumps({'type': 'connected'})}\n\n"
            
            # Initial prices
            if product_id:
                latest = await sync_to_async(price_client.get_latest_price)(product_id)
                if latest:
                    yield f"data: {json.dumps({'type': 'initial', 'data': latest})}\n\n"
            else:
                all_prices = await sync_to_async(price_client.get_all_prices)()
                if all_prices:
                    yield f"data: {json.dumps({'type': 'initial', 'data': all_prices})}\n\n"
            
            # Stream with async sleep
            last_heartbeat = time.time()
            while True:
                # Heartbeat
                if time.time() - last_heartbeat > 15:
                    yield f"event: heartbeat\ndata: {json.dumps({'type': 'heartbeat'})}\n\n"
                    last_heartbeat = time.time()
                
                # Messages
                if messages:
                    msg = messages.pop(0)
                    yield f"data: {json.dumps({'type': 'update', 'data': msg})}\n\n"
                
                await asyncio.sleep(0.1)
                
        except GeneratorExit:
            await sync_to_async(subscriber.stop)()
            logger.info("SSE client disconnected")
        except Exception as e:
            logger.error(f"SSE error: {e}")
            await sync_to_async(subscriber.stop)()
            raise
    
    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    response['Connection'] = 'keep-alive'
    return response

def websocket_service_status(request):
    """Check if WebSocket service is healthy"""
    import requests
    import os
    
    service_url = os.environ.get('WEBSOCKET_SERVICE_URL', 'http://websocket-service:8080')
    
    try:
        response = requests.get(f"{service_url}/health", timeout=5)
        if response.status_code == 200:
            return JsonResponse({"status": True})
        else:
            return JsonResponse({'status': 'unhealthy'}, status=500)
    except requests.exceptions.ConnectionError:
        return JsonResponse({'status': 'unreachable'}, status=503)





from django.shortcuts import render

def price_dashboard(request):
    """Render the price dashboard template"""
    return render(request, 'price_dashboard.html')