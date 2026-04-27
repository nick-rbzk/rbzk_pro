from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from rbzk.settings import GLOBAL_WS_TASK_NAME
from cb_trades.tasks import set_cache_bins
from emails.tasks import trade_opened_email
from .tasks import run_coinbase_websocket, stop_coinbase_websocket
from .models import *
from .forms import TradingPairForm



@csrf_exempt
def trading_options(request):   
    set_cache_bins()
    print(cache.get('bin1'))
    print(cache.get('bin2'))
    print(cache.get("highs_lows"))
    print(cache.get("bin1_STORAGE"))
    print(cache.get("bin2_STORAGE"))

    context = {}
    if request.user.is_authenticated & request.user.is_staff:
        if request.method == "GET":
            context["active_pairs_form"] = TradingPairForm({'action': '0'}, is_active=True)
            context["inactive_pairs_form"] = TradingPairForm({'action': '1'}, is_active=False)
            trade_opened_email.delay()
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
    return redirect("home")
