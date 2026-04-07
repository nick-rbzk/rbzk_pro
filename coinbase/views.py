from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rbzk.settings import GLOBAL_WS_TASK_NAME
from .tasks import run_coinbase_websocket, stop_coinbase_websocket
from .models import *
from .forms import TradingPairForm


from django.core.cache import cache


def set_cache_bins():
    bin1 = {
        'name': 'bin1',
        'inuse': True,
        'storage': []
    }
    bin2 = {
        'name': 'bin2',
        'inuse': False,
        'storage': []
    }
    if not cache.has_key('bin1'):
        cache.set('bin1', bin1, 300)

    if not cache.has_key('bin2'):
        cache.set('bin2', bin2, 300)

@csrf_exempt
def trading_options(request):
    # Access the underlying Redis client
    # client = cache.client.get_client()

    # # Get detailed info dictionary
    # info = client.info()

    # print(f"Used Memory: {info['used_memory_human']}")
    # print(f"Connected Clients: {info['connected_clients']}")
    # print(f"Redis Version: {info['redis_version']}")i
    # print(info)

    
    set_cache_bins()
    print(cache.get('bin1'))
    print(cache.get('bin2'))
    context = {}
    if request.user.is_authenticated & request.user.is_staff:
        if request.method == "GET":
            context["active_pairs_form"] = TradingPairForm({'action': '0'}, is_active=True)
            context["inactive_pairs_form"] = TradingPairForm({'action': '1'}, is_active=False)

        if request.method == "POST":
            pairs_form = TradingPairForm(request.POST, is_active=None)
            if pairs_form.is_valid():
                pair_ids = pairs_form.cleaned_data.get('trading_pairs')
                action = pairs_form.cleaned_data.get('action')
                if action == '1':
                    if len(pair_ids) > 0:
                        task = run_coinbase_websocket.delay(pair_ids)
                        active_task = WebSocketTask.objects.create(
                            task_id=task.id,
                            name=f"{GLOBAL_WS_TASK_NAME}:{pair_ids}",
                        )
                        pairs_q = TradingPair.objects.filter(pk__in=pair_ids)
                        for pair in pairs_q:
                            pair.is_active = True
                            pair.running_task = active_task
                            pair.save()
                
                if action == '0':
                    stop_coinbase_websocket.delay()
                    return redirect("admin:index")
            else:
                print(pairs_form.errors) 
            context["active_pairs_form"] = TradingPairForm({'action': '0'}, is_active=True)
            context["inactive_pairs_form"] = TradingPairForm({'action': '1'}, is_active=False)
        return render(request, 'trader.html', context)

@csrf_exempt
def stop_price_watcher(request, task_id=None):
    """API endpoint to stop the price watcher"""
    if request.method == 'GET':
        pass
        if task_id is not None:
            pass
            at = WebSocketTask.objects.get(taks_id=task_id)
            result = stop_coinbase_websocket.delay(at.task_id)
        else:
            active_tasks = WebSocketTask.objects.all()
            task_ids = []
            for at in active_tasks:
                if at.task_id is not None:
                    task_ids.append(at.task_id)
                    result = stop_coinbase_websocket.delay(at.task_id)
            
            for at in active_tasks:
                at.delete()
            return JsonResponse({'status': 'stopping', 'ids': f"{task_ids}"})
    return JsonResponse({'status': 'stopping', 'task_id': task_id})


def get_latest_price(request):
    return JsonResponse({'result': 'Price not available'}, status=404)