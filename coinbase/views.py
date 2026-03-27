from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rbzk.settings import GLOBAL_WS_TASK_NAME
from .tasks import run_coinbase_websocket, stop_coinbase_websocket
from .models import *
from .forms import TradingPairForm


@csrf_exempt
def trading_options(request):
    """API endpoint to start the price watcher"""
    context = {}
    if request.user.is_authenticated & request.user.is_staff:
        context["active_pairs_form"] = TradingPairForm({'action': '0'}, is_active=True)
        context["inactive_pairs_form"] = TradingPairForm({'action': '1'}, is_active=False)

        if request.method == "POST":
            pairs_form = TradingPairForm(request.POST, is_active=None)
            if pairs_form.is_valid():
                pair_ids = pairs_form.cleaned_data.get('trading_pairs')
                action = pairs_form.cleaned_data.get('action')
                if len(pair_ids) > 0:
                    for p_id in pair_ids:
                        if action == '1':
                            run_coinbase_websocket.delay(p_id)
                        if action == '0':
                            stop_coinbase_websocket.delay(p_id)
 
            else:
                print(pairs_form.errors) 
        return render(request, 'trader.html', context)
    return redirect("home_page")

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