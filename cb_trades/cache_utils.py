import logging
from django.core.cache import cache
from rbzk.settings import CACHE_TRADES_BIN_NAME, TRADES_CACHE_TIMEOUT, \
    CACHE_BIN_TIMEOUT, CACHE_BIN_STORAGE_KEYS, CACHE_BIN_KEYS
from cb_mark.models import TradingPair, Trade


logger = logging.getLogger(__name__)


def cache_get_last_trade(ticker_symbol):
    if ticker_symbol is not None:
        last_trades = cache.get(CACHE_TRADES_BIN_NAME)
        if type(last_trades) == dict:
            if ticker_symbol in last_trades.keys():
                return last_trades[ticker_symbol]["last_trade"]
        logger.error("Failed to get last trades object %s for ticekr symbol: %s",
                    last_trades, ticker_symbol
                )
        return False
    return False


#  [2026-05-07 17:36:50,478: ERROR/ForkPoolWorker-1] Task low_priority:strategy_s1[de12194a-e82c-49e5-8d02-c9c64f7b4b37] raised unexpected: TypeError("'NoneType' object does not support item assignment")
# celery_worker_default-1  | Traceback (most recent call last):
# celery_worker_default-1  |   File "/usr/local/lib/python3.13/site-packages/celery/app/trace.py", line 585, in trace_task
# celery_worker_default-1  |     R = retval = fun(*args, **kwargs)
# celery_worker_default-1  |                  ~~~^^^^^^^^^^^^^^^^^
# celery_worker_default-1  |   File "/usr/local/lib/python3.13/site-packages/celery/app/trace.py", line 858, in __protected_call__
# celery_worker_default-1  |     return self.run(*args, **kwargs)
# celery_worker_default-1  |            ~~~~~~~~^^^^^^^^^^^^^^^^^
# celery_worker_default-1  |   File "/rbzk/cb_trades/tasks.py", line 257, in strategy_s1
# celery_worker_default-1  |     cache_update_last_trades(last_trade, product_id)
# celery_worker_default-1  |     ~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^
# celery_worker_default-1  |   File "/rbzk/cb_trades/cache_utils.py", line 27, in cache_update_last_trades
# celery_worker_default-1  |     last_trades[ticker_symbol] = {"last_trade": last_trade}
# celery_worker_default-1  |     ~~~~~~~~~~~^^^^^^^^^^^^^^^
# celery_worker_default-1  | TypeError: 'NoneType' object does not support item assignment

def cache_update_last_trades(last_trade, ticker_symbol):
    if last_trade is not None and ticker_symbol is not None:
        last_trades = cache.get(CACHE_TRADES_BIN_NAME)
        if last_trades is not None:
            last_trades[ticker_symbol] = {"last_trade": last_trade}
        else:
            last_trades = {}
            last_trades[ticker_symbol] = {"last_trade": last_trade}
        cache.set(CACHE_TRADES_BIN_NAME, last_trades,  TRADES_CACHE_TIMEOUT)
    else:
        logger.error("Failed to update last trades with current trade %s", last_trade)



def cache_set_last_trades():
    pairs = TradingPair.objects.all()
    last_trades = {}
    if len(pairs) > 0:
        for p in pairs:
            last_trade = Trade.objects.filter(
                ticker_symbol=p.ticker_symbol
                ).order_by("created_at").last()
            last_trades[p.ticker_symbol] = {"last_trade": last_trade}
        cache.set(CACHE_TRADES_BIN_NAME, last_trades)
        return True
    return False

def set_cache_bins():
    if not cache.has_key('bin1'):
        cache.set('bin1', True, CACHE_BIN_TIMEOUT)

    if not cache.has_key('bin2'):
        cache.set('bin2', False, CACHE_BIN_TIMEOUT)

    if not cache.has_key('bin1_STORAGE') and not cache.has_key('bin2_STORAGE'):
        storages = {storage:list() for storage in CACHE_BIN_STORAGE_KEYS}
        cache.set_many(storages, CACHE_BIN_TIMEOUT)


def flip_bins():
    bin_in_use_name = None
    bin_state = cache.get_many(CACHE_BIN_KEYS)
    for key in bin_state.keys():
        if bin_state[key]:
            bin_in_use_name = key
        if not bin_state[key]:
            cache.set(key, True, CACHE_BIN_TIMEOUT)
    if bin_in_use_name is not None:
        cache.set(bin_in_use_name, False, CACHE_BIN_TIMEOUT)
        return bin_in_use_name
    return False