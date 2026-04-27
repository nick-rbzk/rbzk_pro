import json
import logging

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from celery import shared_task
from coinbase.models import *
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from rbzk.settings import CACHE_BIN_KEYS, BIN_TIMEOUT, \
    USD_PER_TRADE, STORAGE_PREFIX, BIN_STORAGE_KEYS
from emails.tasks import trade_opened_email, trade_closed_email

logger = logging.getLogger(__name__)


desired_db_price_history_fields = [
        'product_id',
        'price',
        'open_24h',
        'volume_24h',
        'low_24h',
        'high_24h',
        'volume_30d',
        'best_bid',
        'best_bid_size',
        'best_ask',
        'best_ask_size',
        'side',
        'time',
        'last_size',
        'time_received',
    ]



def set_cache_bins():
    if not cache.has_key('bin1'):
        cache.set('bin1', True, BIN_TIMEOUT)

    if not cache.has_key('bin2'):
        cache.set('bin2', False, BIN_TIMEOUT)

    if not cache.has_key('bin1_STORAGE') and not cache.has_key('bin2_STORAGE'):
        storages = {storage:list() for storage in BIN_STORAGE_KEYS}
        cache.set_many(storages, BIN_TIMEOUT)

    if not cache.has_key("highs_lows"):
        set_highs_and_lows.delay()


def flip_bins():
    bin_in_use_name = None
    bin_state = cache.get_many(CACHE_BIN_KEYS)
    for key in bin_state.keys():
        if bin_state[key]:
            bin_in_use_name = key
        if not bin_state[key]:
            cache.set(key, True, BIN_TIMEOUT)
    if bin_in_use_name is not None:
        cache.set(bin_in_use_name, False, BIN_TIMEOUT)
        return bin_in_use_name
    return False

def get_full_bin():
    bin_to_use_name = flip_bins()
    if bin_to_use_name:
        return cache.get(bin_to_use_name + STORAGE_PREFIX)
    return False


@shared_task
def redis_store_price(data):
    ticker_data = json.loads(data)
    if ticker_data.get('type') == 'ticker':
        now = datetime.now(timezone.utc)
        ticker_data['time_received'] = now.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
        bins = cache.get_many(CACHE_BIN_KEYS)
        if not 'bin1' in bins.keys() or not 'bin2' in bins.keys():
            set_cache_bins()
            bins = cache.get_many(CACHE_BIN_KEYS)
        bin_to_use_name = None
        bin_to_use = None
        for b in CACHE_BIN_KEYS:
            if bins[b]:
                bin_to_use_name = b + STORAGE_PREFIX
                break
        
        if STORAGE_PREFIX in bin_to_use_name:
            bin_to_use = cache.get(bin_to_use_name)
            if bin_to_use != None and bin_to_use_name != None:
                bin_to_use.append(ticker_data)
                cache.set(bin_to_use_name, bin_to_use, BIN_TIMEOUT)
                return True
        else:
            print("ALL BINS----------------------")
            print(bins)
            print("BIN TO USE-----------------------")
            print(bin_to_use)
            print("BIN TO USE NAME------------------")
            print(bin_to_use_name)
            return False



@shared_task
def db_record_price():
    bin_to_process = flip_bins()
    if not bin_to_process:
        return "Full Bin was not found"
    full_bin = cache.get(bin_to_process + STORAGE_PREFIX)
    db_data = {}
    for message in full_bin:
        if not message["product_id"] in db_data.keys():

            db_data[message["product_id"]] = {
                "coinbase_date": message["time"],
                "low_price" : message["low_24h"],
                "high_price": message["high_24h"],
                "last_price": message["price"],
                "message_q": [message]
            }
        else:
            db_data[message["product_id"]]["coinbase_date"] = message['time']

            current_price = Decimal(message["price"])
            low_price = Decimal(db_data[message["product_id"]]["low_price"])
            high_price = Decimal(db_data[message["product_id"]]["high_price"])
            if current_price > high_price :
                db_data[message["product_id"]]["high_price"] = message["price"]
            if current_price < low_price:
                db_data[message["product_id"]]["low_price"] = message["price"]

            db_data[message["product_id"]]["last_price"] = message['price']
            db_data[message["product_id"]]["message_q"].append(message)

    for key in db_data.keys():
        try:

            date = datetime.strptime(db_data[key]["coinbase_date"], "%Y-%m-%dT%H:%M:%S.%f%z")

            price_log, created = DayPriceLog.objects.get_or_create(
                coinbase_date=date,
                ticker_symbol=key,
            )
            
            if created:
                print("New Object")
                price_log.high_price = Decimal(db_data[key]['high_price'])
                price_log.low_price = Decimal(db_data[key]['low_price'])

            message_store = db_data[key]["message_q"] 
            for message in message_store:
                price_data = {}
                for field in desired_db_price_history_fields:
                        if field in message:
                            price_data[field] = message[field]

                price_data = json.dumps(price_data)
                price_log.price_history.append(price_data)

            current_price = Decimal(db_data[key]['last_price'])
            if current_price > price_log.high_price :
                price_log.high_price = current_price
            if current_price < price_log.low_price:
                price_log.low_price = current_price

            yestarday = date - timedelta(days=1) 
            try:
                yestarday_dpl = DayPriceLog.objects.get(
                    coinbase_date=yestarday, 
                    ticker_symbol=key,
                )
                if yestarday_dpl is not None:
                    one = abs(price_log.high_price - price_log.low_price)
                    two = abs(yestarday_dpl.last_price  - price_log.high_price)
                    three = abs(yestarday_dpl.last_price - price_log.low_price)
                    price_log.n_atr = max([one, two, three])

            except ObjectDoesNotExist as e:
                print(e)
                logger.error(f"Error processing message: {e}")
                return False

            price_log.last_price = current_price
            price_log.save()
            logger.info(f"Price log update SUCCESS")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return False

    cache.set(bin_to_process + STORAGE_PREFIX, [], BIN_TIMEOUT)
    return True


def cache_update_last_trade(last_trade):
    if last_trade is not None:
        cache.set("last_trade", last_trade,  432000)


def open_trade(ticker_data, trade_type, trend_period):
    price_log = DayPriceLog.objects.get(coinbase_date=datetime.now(), ticker_symbol=ticker_data.get("product_id"))

    break_out_signal = BreakOutSignal.objects.create(
        ticker_symbol = ticker_data.get("product_id"),
        break_out_price = Decimal(ticker_data.get('price')),
        trend_direction = trade_type,
        trend_period = trend_period,
    )

    if trade_type == TradeType.LONG:
        trade = Trade.objects.create(
            ticker_symbol=ticker_data.get("product_id"),
            signal=break_out_signal,
            state=TradeState.OPEN,
            type=trade_type,
            enter_price=Decimal(ticker_data.get("price")) ,
            stop_loss_price=Decimal(ticker_data.get("price")) - (2 * Decimal(price_log.n_atr)),
            dollar_amount = Decimal(USD_PER_TRADE),
            num_shares=Decimal(USD_PER_TRADE) / Decimal(ticker_data.get("price"))
        )

    if trade_type == TradeType.SHORT:
        trade = Trade.objects.create(
            ticker_symbol=ticker_data.get("product_id"),
            signal=break_out_signal,
            state=TradeState.OPEN,
            type=trade_type,
            enter_price=Decimal(ticker_data.get("price")) ,
            stop_loss_price=Decimal(ticker_data.get("price")) + (2 * Decimal(price_log.n_atr)),
            dollar_amount = Decimal(USD_PER_TRADE),
            num_shares=Decimal(USD_PER_TRADE) / Decimal(ticker_data.get("price"))
        )

    cache_update_last_trade(trade)
    trade_opened_email.delay()

def close_trade(trade, current_price, trend_period):
    break_out_signal = BreakOutSignal.objects.create(
        ticker_symbol = trade.ticker_symbol,
        break_out_price = Decimal(current_price),
        trend_direction = trade.type,
        trend_period = trend_period,
    )
    trade.state = TradeState.CLOSED
    if trade.dollar_amount and trade.num_shares and current_price:
        if trade.type == TradeType.SHORT:
            trade.profit_loss = trade.dollar_amount - (trade.num_shares * current_price)
        
        if trade.type == TradeType.LONG:
            trade.profit_loss = (trade.num_shares * current_price) - trade.dollar_amount
    trade.sell_signal = break_out_signal
    trade.save()
    cache_update_last_trade(trade)
    trade_closed_email.delay()

@shared_task
def turtle_strategy(data, *args, **kwargs):

    highs_lows = cache.get("highs_lows")
    if highs_lows is None:
        set_highs_and_lows.delay()
        return False
    
    encoded_json    = json.dumps(data) 
    ticker_data     = json.loads(encoded_json)
    current_price   = Decimal(ticker_data.get('price'))

    last_trade = cache.get("last_trade")
    if last_trade is None:
        last_trade = Trade.objects.filter(ticker_symbol=ticker_data.get('product_id')).order_by("created_at").last()
        cache_update_last_trade(last_trade)
        
    highest_20day   = highs_lows[ticker_data.get("product_id")]["highest_20day"]
    lowest_20day    = highs_lows[ticker_data.get("product_id")]["lowest_20day"]
    highest_10day   = highs_lows[ticker_data.get("product_id")]["highest_10day"]
    lowest_10day    = highs_lows[ticker_data.get("product_id")]["lowest_10day"]
    highest_55day   = highs_lows[ticker_data.get("product_id")]["highest_55day"]
    lowest_55day    = highs_lows[ticker_data.get("product_id")]["lowest_55day"]


    if last_trade.state == TradeState.OPEN:
        # stop Loss mitigation
        if current_price == last_trade.stop_loss_price:
            close_trade(last_trade, current_price, TrendPeriod.STOP_LOSS)
            cache_update_last_trade(last_trade)
            return True
        
        # Turtle Strategy
        if last_trade.buy_signal.trend_period == TrendPeriod.TWENTY:
            # close the trade if price breaks the 10 day in the opposite direction of entry
            if last_trade.type == TradeType.SHORT:
                if current_price > highest_10day:
                    # sell the asset
                    close_trade(last_trade, current_price, TrendPeriod.TEN)
            if last_trade.type == TradeType.LONG:
                if current_price < lowest_10day:
                    # sell the asset
                    close_trade(last_trade, current_price, TrendPeriod.TEN)
            cache_update_last_trade(last_trade)
            return False
        
        if last_trade.buy_signal.trend_period == TrendPeriod.FIFTYFIVE:
            # close the trade if price breaks the 20 day in the opposite direction of entry
            if last_trade.type == TradeType.SHORT:
                if current_price > highest_20day:
                    # sell the asset
                    close_trade(last_trade, current_price, TrendPeriod.TWENTY)
            if last_trade.type == TradeType.LONG:
                if current_price < lowest_20day:
                    # sell the asset
                    close_trade(last_trade, current_price, TrendPeriod.TWENTY)
            cache_update_last_trade(last_trade)
            return False
        
    if last_trade.profit_loss < 0  and last_trade.state == TradeState.CLOSED:
        # Open trade if the price braks out 20 day high or 20 day low
        if current_price > highest_20day:
            # Breakout signal buy long
            open_trade(ticker_data, TradeType.LONG, TrendPeriod.TWENTY)
        if current_price < lowest_20day:
            # Breakout signal buy short
            open_trade(ticker_data, TradeType.SHORT, TrendPeriod.TWENTY)
        return True
    
    if last_trade.profit_loss > 0  and last_trade.state == TradeState.CLOSED:
        # Watch for S2 now
        if current_price > highest_55day:
            # Breakout signal buy long
            open_trade(ticker_data, TradeType.LONG, TrendPeriod.FIFTYFIVE)
        if current_price < lowest_55day:
            # Breakout signal buy short
            open_trade(ticker_data, TradeType.SHORT, TrendPeriod.FIFTYFIVE)
        return True


@shared_task
def set_highs_and_lows():
    now = datetime.now()
    days_from_now = 55
    delta_55 = now - timedelta(days=days_from_now)
    yestarday = now - timedelta(days=1)
    trading_pairs = TradingPair.objects.all()
    cache_data = {}
    for pair in trading_pairs:
        day_logs = DayPriceLog.objects.filter(
            ticker_symbol=pair.ticker_symbol,
            coinbase_date__lte=yestarday,
            coinbase_date__gte=delta_55,
            ).order_by('-coinbase_date')
        
        days_10_highs   = []
        days_10_lows    = []
        days_20_highs   = []
        days_20_lows    = []
        days_55_highs   = []
        days_55_lows    = []
        idx = 0 
        for dl in day_logs: # check for precision
            if idx < 10:
                days_10_highs.append(dl.high_price)
                days_10_lows.append(dl.low_price)
            if idx < 20: 
                days_20_highs.append(dl.high_price)
                days_20_lows.append(dl.low_price)
            days_55_highs.append(dl.high_price)
            days_55_lows.append(dl.low_price)
            idx += 1
        
        highest_20day   = max(days_20_highs)
        lowest_20day    = min(days_20_lows)
        highest_10day   = max(days_10_highs)
        lowest_10day    = min(days_10_lows)
        highest_55day   = max(days_55_highs)
        lowest_55day    = min(days_55_lows)

        cache_data[pair.ticker_symbol] = {
            "highest_20day": highest_20day,
            "lowest_20day": lowest_20day,
            "highest_10day": highest_10day,
            "lowest_10day": lowest_10day,
            "highest_55day": highest_55day,
            "lowest_55day": lowest_55day,
        }
    cache.set("highs_lows", cache_data, 172800)
