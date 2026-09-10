import logging, secrets
from django.core.cache import cache
from rbzk.settings import CACHE_TRADES_BIN_NAME, TRADES_CACHE_TIMEOUT, \
    CACHE_BIN_TIMEOUT, CACHE_BIN_STORAGE_KEYS, CACHE_BIN_KEYS
from cb_mark.models import TradingPair, Trade, TrendPeriod

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

def create_trade_draft(trade_state=None, 
            trade_type=None, trend_period=None) -> dict:
    
    new_last_trade = {
        "uid": str(secrets.randbelow(9999999999999999999999999)),
        "state": trade_state,
        "type": trade_type,
        "stop_loss_price": None,
        "profit_loss": None,
        "buy_signal": {
            "trend_period": trend_period,
        }
    }
    return dict(new_last_trade)

def cache_set_last_trades():
    pairs = TradingPair.objects.all()
    last_trades = {}
    if len(pairs) > 0:
        for p in pairs:
            last_db_trade = Trade.objects.filter(
                ticker_symbol=p.ticker_symbol
                ).order_by("created_at").last()
            if last_db_trade.buy_signal is not None and hasattr(last_db_trade.buy_signal, 'trend_period'):
                last_trade = create_trade_draft(
                    last_db_trade.state, 
                    last_db_trade.type,
                    last_db_trade.buy_signal.trend_period
                )
            else:
                last_trade = create_trade_draft(
                    last_db_trade.state, 
                    last_db_trade.type,
                    TrendPeriod.STOP_LOSS
                )
            last_trade.update({
                'uid': last_db_trade.uid,
                'stop_loss_price': last_db_trade.stop_loss_price,
                'profit_loss': last_db_trade.profit_loss
                })
            last_trades[p.ticker_symbol] = {"last_trade": last_trade}
        cache.set(CACHE_TRADES_BIN_NAME, last_trades, TRADES_CACHE_TIMEOUT)
        return True
    return False



def cache_update_last_trades(last_trade, ticker_symbol):
    print("Trade to update", last_trade)
    print("TickerSymbol", ticker_symbol)
    if isinstance(last_trade, dict) and ticker_symbol is not None:
        last_trades = cache.get(CACHE_TRADES_BIN_NAME)
        if last_trades is not None:
            last_trades[ticker_symbol] = {"last_trade": last_trade}
            cache.set(CACHE_TRADES_BIN_NAME, last_trades,  TRADES_CACHE_TIMEOUT)
        else:
            cache_set_last_trades()
    else:
        try:
            cache_set_last_trades()
        except Exception as e:
            logger.error("Failed to update last trades %s", e)





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

def cache_update_highs_lows(highs_lows, product_id, period, new_price):
    if highs_lows is None:
        highs_lows = cache.get("highs_lows")



