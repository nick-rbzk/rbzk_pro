from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .tasks import run_coinbase_websocket, stop_coinbase_websocket
from .models import *


GLOBAL_WS_TASK_NAME = 'websocket'


@csrf_exempt
def start_price_watcher(request):
    """API endpoint to start the price watcher"""
    if request.method == 'GET':
        # data = json.loads(request.body)
        product_ids = ["BTC-USD", "ETH-USD"]
        
        # Start the long-running task
        task = run_coinbase_websocket.delay(product_ids)

        # TODO
        # Store active task id in db
        # ActiveTask.objects.crate(task_id=task.id, name=GLOBAL_WS_TASK_NAME)
        # turn get views for separate pages

        return JsonResponse({
            'status': 'started',
            'task_id': task.id,
            'product_ids': product_ids
        })
        

@csrf_exempt
def stop_price_watcher(request):
    """API endpoint to stop the price watcher"""
    if request.method == 'GET':
        pass
        # active_tasks = ActiveTask.object.all()
        # for at in active_tasks:
        #     if at.task_id is not None:
        #         result = stop_coinbase_websocket.delay(at.task_id)
    return JsonResponse({'status': 'stopping', 'task_id': "task_id"})

def get_latest_price(request):
    """Get the latest cached price for a product"""
    cache_eth_key = "coinbase_price_ETH"
    cache_btc_key = "coinbase_price_BTC"

    # eth_data = cache.get(cache_eth_key)
    # btc_data = cache.get(cache_btc_key)
    # print(eth_data)     
    # print(btc_data)

    # if togather:
        # return JsonResponse(togather)
    return JsonResponse({'error': 'Price not available'}, status=404)