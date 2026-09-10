"""
Django views for real-time price updates using Redis pub/sub.
Supports Server-Sent Events (SSE) and WebSocket streaming.
"""

import json, time, logging, asyncio, requests
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import sync_to_async
from cb_mark.models import TradingPair
from django.views import View
from django.views.generic import TemplateView
from django.utils.decorators import method_decorator
from django.db.models import Q
from cb_mark.models import TradingPair, Trade, TradeState
from .redis_pubsub import RedisPriceSubscriber
from .websocket_client import price_client

logger = logging.getLogger(__name__)


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




class TradingDashboardView(TemplateView):
    """Main dashboard view"""
    template_name = 'price_dash.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['trading_pairs'] = TradingPair.objects.filter(is_active=True)
        context['open_trades'] = Trade.objects.filter(state=TradeState.OPEN)

        closed_trades = Trade.objects.filter(state=TradeState.CLOSED).exclude(
            Q(buy_signal=None) & Q(sell_signal=None)
        )
        formated_closed_trades = []
        for trade in closed_trades:
            formated_trade = {
                'ticker_symbol': trade.ticker_symbol,
                'type': trade.type,
                'enter_price': round(trade.enter_price, trade.trading_pair.decimal_places) if trade.stop_loss_price else 0,
                'stop_loss_price': round(trade.stop_loss_price, trade.trading_pair.decimal_places) if trade.stop_loss_price else 0,
                'exit_price': round(trade.exit_price, trade.trading_pair.decimal_places) if trade.stop_loss_price else 0,
                'profit_loss': round(trade.profit_loss, trade.trading_pair.decimal_places) if trade.stop_loss_price else 0,
                'created_at': trade.created_at,
            }
            formated_closed_trades.append(formated_trade)
        context['closed_trades'] = formated_closed_trades
        return context


class TradingPairsAPIView(View):
    """API view for trading pairs data"""
    
    def get(self, request):
        """Get all trading pairs with current prices"""
        try:
            pairs = TradingPair.objects.all().order_by('ticker_symbol')
            trades = Trade.objects.filter(state=TradeState.OPEN) # Open trades only
            
            
            data = {
                'trading_pairs': [
                    {
                        'id': pair.id,
                        'ticker_symbol': pair.ticker_symbol,
                        'name': pair.name,
                        'is_active': pair.is_active,
                        'highest_10day': str(round(pair.highest_10day, pair.decimal_places)) if pair.highest_10day else None,
                        'highest_20day': str(round(pair.highest_20day, pair.decimal_places)) if pair.highest_20day else None,
                        'highest_55day': str(round(pair.highest_55day, pair.decimal_places)) if pair.highest_55day else None,
                        'lowest_10day': str(round(pair.lowest_10day, pair.decimal_places)) if pair.lowest_10day else None,
                        'lowest_20day': str(round(pair.lowest_20day, pair.decimal_places)) if pair.lowest_20day else None,
                        'lowest_55day': str(round(pair.lowest_55day, pair.decimal_places)) if pair.lowest_55day else None,
                    }
                    for pair in pairs
                ],
                'trades': [
                    {
                        'id': trade.id,
                        'ticker_symbol': trade.ticker_symbol,
                        'state': trade.state,
                        'type': trade.type,
                        'enter_price': str(round(trade.enter_price, trade.trading_pair.decimal_places)),
                        'stop_loss_price': str(round(trade.stop_loss_price, trade.trading_pair.decimal_places)),
                        'exit_price': str(round(trade.exit_price, trade.trading_pair.decimal_places)) if trade.exit_price else None,
                        'profit_loss': str(round(trade.profit_loss, trade.trading_pair.decimal_places)) if trade.profit_loss else None,
                        'dollar_amount': str(trade.dollar_amount) if trade.dollar_amount else None,
                        'num_shares': str(trade.num_shares) if trade.num_shares else None,
                        'created_at': trade.created_at.isoformat(),
                        'updated_at': trade.updated_at.isoformat(),
                    }
                    for trade in trades
                ],
            }
            
            return JsonResponse(data, status=200)
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    



class UpdateTradingPairsAPIView(View):
    """API view to update active trading pairs"""
    
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request):
        """Update active trading pairs based on selection"""
        try:
            data = json.loads(request.body)
            selected_pairs = data.get('trading_pairs', [])
            
            if not isinstance(selected_pairs, list):
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid data format. Expected list of trading pairs.'
                }, status=400)
            
            # Update active status for all pairs
            all_pairs = TradingPair.objects.all()
            
            for pair in all_pairs:
                if pair.ticker_symbol in selected_pairs:
                    pair.is_active = True
                else:
                    pair.is_active = False
                pair.save()
            
            # Send updated pairs to WebSocket service
            self._send_to_websocket_service(selected_pairs)
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully updated {len(selected_pairs)} trading pairs.',
                'active_pairs': selected_pairs
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data.'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error updating trading pairs: {str(e)}'
            }, status=500)
    
    def _send_to_websocket_service(self, trading_pairs):
        """Send updated trading pairs to WebSocket service"""
        try:
            payload = {
                'action': 'update_pairs',
                'products': trading_pairs
            }
            # Send to WebSocket service
            response = requests.post(
                'http://websocket-service:8080/resubscribe',
                json=payload,
                timeout=5
            )
            
            if response.status_code != 200:
                print(f"Error sending to WebSocket service: {response.status_code}")
                
        except Exception as e:
            print(f"Error sending to WebSocket service: {e}")
            # Continue execution even if WebSocket service fails















