import json
import logging

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from celery import shared_task
from cb_mark.models import *
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from rbzk.settings import CACHE_BIN_KEYS, CACHE_BIN_TIMEOUT, \
    USD_PER_TRADE, CACHE_STORAGE_PREFIX, CACHE_BIN_STORAGE_KEYS, \
    CACHE_TRADES_BIN_NAME
from emails.tasks import trade_opened_email, trade_closed_email
from .cache_utils import cache_get_last_trade, cache_update_last_trades,\
    cache_set_last_trades, set_cache_bins, flip_bins

logger = logging.getLogger(__name__)

TARGET_DB_PRICE_HISTORY_FIELDS = [
    'product_id','sequence','price','open_24h','volume_24h','low_24h','high_24h',
    'volume_30d','best_bid','best_bid_size','best_ask','best_ask_size','side',
    'time','last_size','time_received','trade_id',
]

VALID_FIELDS = [
    'type', 'sequence', 'product_id', 'price', 'open_24h', 'volume_24h', 'low_24h', 
    'high_24h', 'volume_30d', 'best_bid', 'best_bid_size', 'best_ask', 'best_ask_size',
    'side', 'time', 'trade_id', 'last_size', 'time_received'
]


def get_full_bin():
    bin_to_use_name = flip_bins()
    if bin_to_use_name:
        return cache.get(bin_to_use_name + CACHE_STORAGE_PREFIX)
    return False


@shared_task(name='high_priority:redis_store_price')
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
                bin_to_use_name = b + CACHE_STORAGE_PREFIX
                break
        
        if CACHE_STORAGE_PREFIX in bin_to_use_name:
            bin_to_use = cache.get(bin_to_use_name)
            if bin_to_use != None and bin_to_use_name != None:
                bin_to_use.append(ticker_data)
                cache.set(bin_to_use_name, bin_to_use, CACHE_BIN_TIMEOUT)
                return True
        else:
            logger.error("Storage Bin was not Found", bins)
            print("All bins", bins)
            logger.error("Missing bin to use for precessing", bin_to_use)
            return False

def valid_message(message):
    if message:
        for key in message.keys():
            if key not in VALID_FIELDS:
                logger.error("Message is missing a Key : %s", key)
                return False
        return True
    logger.error("Invalid Message: %s", key)
    return False


@shared_task(name='low_priority:db_record_price')
def db_record_price():
    bin_to_process_name = flip_bins()
    if not bin_to_process_name:
        logger.error("No Bin Name! :: %s", bin_to_process_name)
        return False
    full_bin = cache.get(bin_to_process_name + CACHE_STORAGE_PREFIX)
    if full_bin is None:
        logger.error("Full bin is not found. %s", full_bin)
        return False
    db_data = {}
    for message in full_bin:
        if not valid_message(message):
            logger.error("Message is incomplete : %s", message)
        else: 
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
            print("Coin base date", date)
            print("Price Log", price_log)
            print("Is Created", created)
            if created:
                print("New Object")
                price_log.high_price = Decimal(db_data[key]['high_price'])
                price_log.low_price = Decimal(db_data[key]['low_price'])

            message_store = db_data[key]["message_q"] 
            for message in message_store:
                price_data = {}
                for field in TARGET_DB_PRICE_HISTORY_FIELDS:
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
                logger.error(f"Error Updating Price Log with ATR: {e}")
                return False

            price_log.last_price = current_price
            price_log.save()
            logger.info(f"Price log update SUCCESS")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return False

    cache.set(bin_to_process_name + CACHE_STORAGE_PREFIX, [], CACHE_BIN_TIMEOUT)
    return True


@shared_task(name='low_priority:cache_set_last_trades')
def task_cache_set_last_trades():
    cache_set_last_trades()


def open_trade(ticker_data, trade_type, trend_period):
    trading_pair = ticker_data.get("product_id")
    price_log = DayPriceLog.objects.get(coinbase_date=datetime.now(), ticker_symbol=trading_pair)
    break_out_signal = BreakOutSignal.objects.create(
        ticker_symbol = trading_pair,
        break_out_price = Decimal(ticker_data.get('price')),
        trend_direction = trade_type,
        trend_period = trend_period,
    )

    if trade_type == TradeType.LONG:
        trade = Trade.objects.create(
            ticker_symbol=trading_pair,
            buy_signal=break_out_signal,
            state=TradeState.OPEN,
            type=trade_type,
            enter_price=Decimal(ticker_data.get("price")) ,
            stop_loss_price=Decimal(ticker_data.get("price")) - (2 * Decimal(price_log.n_atr)),
            dollar_amount = Decimal(USD_PER_TRADE),
            num_shares=Decimal(USD_PER_TRADE) / Decimal(ticker_data.get("price"))
        )

    if trade_type == TradeType.SHORT:
        trade = Trade.objects.create(
            ticker_symbol=trading_pair,
            buy_signal=break_out_signal,
            state=TradeState.OPEN,
            type=trade_type,
            enter_price=Decimal(ticker_data.get("price")) ,
            stop_loss_price=Decimal(ticker_data.get("price")) + (2 * Decimal(price_log.n_atr)),
            dollar_amount = Decimal(USD_PER_TRADE),
            num_shares=Decimal(USD_PER_TRADE) / Decimal(ticker_data.get("price"))
        )

    cache_update_last_trades(trade, trading_pair)
    trade_opened_email.delay(trading_pair)

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
    cache_update_last_trades(trade, trade.ticker_symbol)
    trade_closed_email.delay(trade.ticker_symbol)


@shared_task(name='low_priority:strategy_s1')
def strategy_s1(data, *args, **kwargs):
    ticker_data     = json.loads(data)

    if ticker_data is None or not ticker_data.get('type') == 'ticker':
        logger.error("Incorrect data %s", ticker_data)
        return False
    
    highs_lows = cache.get("highs_lows")
    if highs_lows is None:
        set_highs_and_lows.delay()
        logger.error("Highs and Lows where NOT set")
        return False
    
    
    current_price   = Decimal(ticker_data.get('price'))
    product_id      = ticker_data.get('product_id')
    last_trade      = cache_get_last_trade(product_id)
    if not last_trade:
        last_trade = Trade.objects.filter(ticker_symbol=product_id).order_by("created_at").last()
        cache_update_last_trades(last_trade, product_id)
        
    highest_20day   = highs_lows[product_id]["highest_20day"]
    lowest_20day    = highs_lows[product_id]["lowest_20day"]
    highest_10day   = highs_lows[product_id]["highest_10day"]
    lowest_10day    = highs_lows[product_id]["lowest_10day"]
    highest_55day   = highs_lows[product_id]["highest_55day"]
    lowest_55day    = highs_lows[product_id]["lowest_55day"]


    if last_trade.state == TradeState.OPEN:
        # stop Loss mitigation
        if current_price == last_trade.stop_loss_price:
            close_trade(last_trade, current_price, TrendPeriod.STOP_LOSS)
            cache_update_last_trades(last_trade, product_id)
            logger.info("Stop loss prevention, trade id: %s", last_trade.id)
            return True
        
        # Turtle Strategy
        if last_trade.buy_signal.trend_period == TrendPeriod.TWENTY:
            # close the trade if price breaks the 10 day in the opposite direction of entry
            logger.info("close the trade if price breaks the 10 day in the opposite direction of entry")
            if last_trade.type == TradeType.SHORT:
                if current_price > highest_10day:
                    # sell the asset
                    close_trade(last_trade, current_price, TrendPeriod.TEN)
            if last_trade.type == TradeType.LONG:
                if current_price < lowest_10day:
                    # sell the asset
                    close_trade(last_trade, current_price, TrendPeriod.TEN)
            cache_update_last_trades(last_trade, product_id)
            return False
        
        if last_trade.buy_signal.trend_period == TrendPeriod.FIFTYFIVE:
            # close the trade if price breaks the 20 day in the opposite direction of entry
            logger.info("Closing a trade if condition matches")
            if last_trade.type == TradeType.SHORT:
                if current_price > highest_20day:
                    # sell the asset
                    close_trade(last_trade, current_price, TrendPeriod.TWENTY)
            if last_trade.type == TradeType.LONG:
                if current_price < lowest_20day:
                    # sell the asset
                    close_trade(last_trade, current_price, TrendPeriod.TWENTY)
            cache_update_last_trades(last_trade, product_id)
            return False
        
    if last_trade.profit_loss < 0  and last_trade.state == TradeState.CLOSED:
        # Open trade if the price braks out 20 day high or 20 day low
        logger.info("Will open trade if price break out of 20 days")
        if current_price > highest_20day:
            # Breakout signal buy long
            open_trade(ticker_data, TradeType.LONG, TrendPeriod.TWENTY)
        if current_price < lowest_20day:
            # Breakout signal buy short
            open_trade(ticker_data, TradeType.SHORT, TrendPeriod.TWENTY)
        return True
    
    if last_trade.profit_loss > 0  and last_trade.state == TradeState.CLOSED:
        # Watch for S2 now
        logger.info("Watching for S2. 55 day breakout.")
        if current_price > highest_55day:
            # Breakout signal buy long
            open_trade(ticker_data, TradeType.LONG, TrendPeriod.FIFTYFIVE)
        if current_price < lowest_55day:
            # Breakout signal buy short
            open_trade(ticker_data, TradeType.SHORT, TrendPeriod.FIFTYFIVE)
        return True


@shared_task(name='low_priority:set_highs_and_lows')
def set_highs_and_lows():
    now = datetime.now()
    days_from_now = 55
    delta_55 = now - timedelta(days=days_from_now)
    yestarday = now - timedelta(days=1)
    trading_pairs = TradingPair.objects.all()
    cache_data = {}
    if len(trading_pairs) < 1:
        logger.error("No Trading Pairs provided")
        return False
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
        if len(day_logs) > 0:
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
    return True
