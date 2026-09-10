import json, logging

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from celery import shared_task
from cb_mark.models import *
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from rbzk.settings import CACHE_BIN_KEYS, CACHE_BIN_TIMEOUT, \
    USD_PER_TRADE, CACHE_STORAGE_PREFIX, TRADES_CACHE_TIMEOUT
from emails.tasks import trade_opened_email, trade_closed_email, ten_day_event_email
from .cache_utils import cache_get_last_trade, cache_update_last_trades,\
    cache_set_last_trades, set_cache_bins, flip_bins, create_trade_draft

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


# @shared_task(name='low_priority:redis_store_price', reject_on_worker_lost=False)
def redis_store_price(ticker_data):
    # ticker_data = json.loads(data)
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


@shared_task(name='low_priority:db_record_price', reject_on_worker_lost=True)
def db_store_price():
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
                    "open_24h": message["open_24h"],
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
                price_log.high_price = Decimal(db_data[key]['high_price'])
                price_log.low_price = Decimal(db_data[key]['low_price'])
                price_log.open_price = Decimal(db_data[key]['open_24h'])
                set_highs_and_lows.delay()
            message_store = db_data[key]["message_q"] 
            for message in message_store:
                price_data = {}
                for field in TARGET_DB_PRICE_HISTORY_FIELDS:
                        if field in message:
                            price_data[field] = message[field]

                price_data = json.dumps(price_data)
                # TODO 
                # save price history in to a file, upload to aws
                # price_log.price_history.append(price_data) 

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
            del price_log
            del yestarday_dpl
            del message_store
            logger.info(f"Price log update SUCCESS")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return False
    cache.set(bin_to_process_name + CACHE_STORAGE_PREFIX, [], CACHE_BIN_TIMEOUT)
    return True


@shared_task(name='low_priority:cache_set_last_trades')
def task_cache_set_last_trades():
    try:
        return cache_set_last_trades()
    except Exception as e:
        logger.error("Failed to set last Trades in cache. Error %s", e)


@shared_task(name='high_priority:open_new_trade')
def open_trade(ticker_data, new_last_trade):
    db_trade = None
    trading_pair = ticker_data.get("product_id")
    price_log = DayPriceLog.objects.get(coinbase_date=datetime.now(), ticker_symbol=trading_pair)
    break_out_signal = BreakOutSignal.objects.create(
        ticker_symbol = trading_pair,
        break_out_price = Decimal(ticker_data.get('price')),
        trend_direction = new_last_trade.get('type'),
        trend_period = new_last_trade.get('buy_signal').get('trend_period'),
    )
    if new_last_trade.get('type') == TradeType.LONG:
        db_trade = Trade.objects.create(
            uid = new_last_trade.get('uid'),
            ticker_symbol=trading_pair,
            buy_signal=break_out_signal,
            state=TradeState.OPEN,
            type=new_last_trade.get('type'),
            enter_price=Decimal(ticker_data.get("price")) ,
            stop_loss_price=Decimal(ticker_data.get("price")) - (2 * Decimal(price_log.n_atr)),
            dollar_amount = Decimal(USD_PER_TRADE),
            num_shares=Decimal(USD_PER_TRADE) / Decimal(ticker_data.get("price"))
        )

    if new_last_trade.get('type') == TradeType.SHORT:
        db_trade = Trade.objects.create(
            uid = new_last_trade.get('uid'),
            ticker_symbol=trading_pair,
            buy_signal=break_out_signal,
            state=TradeState.OPEN,
            type=new_last_trade.get('type'),
            enter_price=Decimal(ticker_data.get("price")) ,
            stop_loss_price=Decimal(ticker_data.get("price")) + (2 * Decimal(price_log.n_atr)),
            dollar_amount = Decimal(USD_PER_TRADE),
            num_shares=Decimal(USD_PER_TRADE) / Decimal(ticker_data.get("price"))
        )
    if isinstance(db_trade, Trade):
        new_last_trade.update({
            "stop_loss_price": db_trade.stop_loss_price,
            "profit_loss": db_trade.profit_loss
        })
        cache_update_last_trades(new_last_trade, trading_pair)
        trade_opened_email.delay(db_trade.uid, trading_pair)



@shared_task(name='high_priority:close_trade')
def close_trade(trade, current_price, product_id, trend_period):
    db_trade = Trade.objects.filter(
        uid=trade.get('uid'), 
        ticker_symbol=product_id,
        state=TradeState.OPEN
    ).order_by('created_at').last()

    break_out_signal = BreakOutSignal.objects.create(
        ticker_symbol = product_id,
        break_out_price = Decimal(current_price),
        trend_direction = trade.get('type'),
        trend_period = trend_period,
    )
    db_trade.state = TradeState.CLOSED
    if db_trade.dollar_amount and db_trade.num_shares and current_price:
        if db_trade.type == TradeType.SHORT:
            db_trade.profit_loss = db_trade.dollar_amount - (db_trade.num_shares * current_price)
        
        if db_trade.type == TradeType.LONG:
            db_trade.profit_loss = (db_trade.num_shares * current_price) - db_trade.dollar_amount
    db_trade.sell_signal = break_out_signal
    db_trade.exit_price = Decimal(current_price)
    db_trade.save()

    trade.update({
        'state': TradeState.CLOSED,
        "profit_loss": db_trade.profit_loss,
    })
    cache_update_last_trades(trade, product_id)
    trade_closed_email.delay(db_trade.uid, product_id)




def lock_aquired(commit_action, trading_pair ,trade_id, lock_for_hours=1) -> bool:
    key = f"{commit_action}:trade_commit_lock:{trade_id}"
    now = datetime.now()
    one_hour_later = now + timedelta(hours=lock_for_hours)
    ttl_seconds = (one_hour_later - now).total_seconds()

    lock_acquired = cache.add(
        key, 
        trading_pair,
        timeout=ttl_seconds  # Expires in 1 hour
    )

    return lock_acquired




# @shared_task(name='high_priority:strategy_s1', reject_on_worker_lost=False)
def strategy_s1(ticker_data, *args, **kwargs):

    # For testing purposes only
    # ticker_data = {'time_received': '2026-08-29 21:56:03.229677', 
    #  'type': 'ticker', 
    #  'sequence': 135235997477, 
    #  'product_id': 'BTC-USD', 
    #  'price': '78179.21', 
    #  'open_24h': '77365.49', 
    #  'volume_24h': '2995.59996413', 
    #  'low_24h': '77339.31', 
    #  'high_24h': '78334.44', 
    #  'volume_30d': '210131.54961702', 
    #  'best_bid': '78179.21', 
    #  'best_bid_size': '0.00024884', 
    #  'best_ask': '78179.22', 
    #  'best_ask_size': '0.06838580', 
    #  'side': 'sell', 
    #  'time': '2026-08-29T21:56:03.156336Z', 
    #  'trade_id': 1085931770, 
    #  'last_size': '0.00000022'}


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
    if not isinstance(last_trade, dict) or last_trade is None:
        # most def needs to be redone
        last_trade = Trade.objects.filter(ticker_symbol=product_id).order_by("created_at").last()
        cache_update_last_trades(last_trade, product_id)
        
    highest_20day   = highs_lows[product_id]["highest_20day"]
    lowest_20day    = highs_lows[product_id]["lowest_20day"]
    highest_10day   = highs_lows[product_id]["highest_10day"]
    lowest_10day    = highs_lows[product_id]["lowest_10day"]
    highest_55day   = highs_lows[product_id]["highest_55day"]
    lowest_55day    = highs_lows[product_id]["lowest_55day"]

    # My own preferance
    if current_price > highest_10day:
        if not lock_aquired('HIGH_BREAK', product_id, 'EMAIL', lock_for_hours=1):
            logger.info(f"EmailAlert with id:{last_trade.get("uid")} has already been sent")
        else:
            ten_day_event_email.delay(product_id, current_price, 'HIGH')
    if current_price < lowest_10day:
        if not lock_aquired('LOW_BREAK', product_id, 'EMAIL', lock_for_hours=1):
            logger.info(f"EmailAlert with id:{last_trade.get("uid")} has already been sent")
        else:
            ten_day_event_email.delay(product_id, current_price, 'LOW')

    if last_trade.get('state') == TradeState.OPEN:

        # stop Loss mitigation
        if isinstance(last_trade.get('stop_loss_price'), Decimal):
            logger.info("--------------STOP LOSS---------------")
            if last_trade.get('type') == TradeType.SHORT:
                if current_price >= last_trade.get('stop_loss_price'):
                    if not lock_aquired('STOP_LOSS_SHORT_CLOSE', product_id, last_trade.get('uid'), lock_for_hours=1):
                        logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                        return f"Trade id {last_trade.get('uid')} is already closed."
                    else:
                        close_trade.delay(last_trade, current_price, product_id, TrendPeriod.STOP_LOSS)
                        last_trade.update({'state': TradeState.CLOSED})
                        cache_update_last_trades(last_trade, product_id)

            if last_trade.get('type') == TradeType.LONG:
                if current_price <= last_trade.get('stop_loss_price'):
                    if not lock_aquired('STOP_LOSS_LONG_CLOSE', product_id, last_trade.get('uid'), lock_for_hours=1):
                        logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                        return f"Trade id {last_trade.get('uid')} is already closed."
                    else:
                        close_trade.delay(last_trade, current_price, product_id, TrendPeriod.STOP_LOSS)
                        last_trade.update({'state': TradeState.CLOSED})
                        cache_update_last_trades(last_trade, product_id)


        # Turtle Strategy
        if last_trade.get('buy_signal').get('trend_period') == TrendPeriod.TWENTY:
            # close the trade if price breaks the 10 day in the opposite direction of entry
            if last_trade.get('type') == TradeType.SHORT:
                if current_price > highest_10day:
                    # sell the asset
                    if not lock_aquired('10_DAY_HIGH_SHORT_CLOSE', product_id, last_trade.get('uid'), lock_for_hours=1):
                        logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                        return f"Trade id {last_trade.get('uid')} is already closed."
                    else:
                        logger.info("Price broke 10 day HIGH. CLOSING SHORT.")
                        close_trade.delay(last_trade, current_price, product_id, TrendPeriod.TEN)
                        last_trade.update({'state': TradeState.CLOSED})
                        cache_update_last_trades(last_trade, product_id)

                        highs_lows[product_id]["highest_10day"] = current_price
                        cache.set("highs_lows", highs_lows, TRADES_CACHE_TIMEOUT)

            if last_trade.get('type') == TradeType.LONG:
                if current_price < lowest_10day:
                    # sell the asset
                    if not lock_aquired('10_DAY_LOW_LONG_CLOSE', product_id, last_trade.get('uid'), lock_for_hours=1):
                        logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                        return f"Trade id {last_trade.get('uid')} is already closed."
                    else:
                        logger.info("Price broke 10 day LOW. CLOSING LONG.")
                        close_trade.delay(last_trade, current_price, product_id, TrendPeriod.TEN)
                        last_trade.update({'state': TradeState.CLOSED})
                        cache_update_last_trades(last_trade, product_id)

                        highs_lows[product_id]["lowest_10day"] = current_price
                        cache.set("highs_lows", highs_lows, TRADES_CACHE_TIMEOUT)

  
        if last_trade.get('buy_signal').get('trend_period') == TrendPeriod.FIFTYFIVE:
            # close the trade if price breaks the 20 day in the opposite direction of entry
            if last_trade.get('type') == TradeType.SHORT:
                if current_price > highest_20day:
                    # sell the asset
                    if not lock_aquired('20_DAY_HIGH_SHORT_CLOSE', product_id, last_trade.get('uid'), lock_for_hours=1):
                        logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                        return f"Trade id {last_trade.get('uid')} is already closed."
                    else:
                        logger.info("Price broke 20 day HIGH. CLOSING SHORT.")
                        close_trade.delay(last_trade, current_price, product_id, TrendPeriod.TWENTY)
                        last_trade.update({'state': TradeState.CLOSED})
                        cache_update_last_trades(last_trade, product_id)

                        highs_lows[product_id]["highest_20day"] = current_price
                        cache.set("highs_lows", highs_lows, TRADES_CACHE_TIMEOUT)
                
            if last_trade.get('type') == TradeType.LONG:
                if current_price < lowest_20day:
                    # sell the asset
                    if not lock_aquired('20_DAY_LOW_LONG_CLOSE', product_id, last_trade.get('uid'), lock_for_hours=1):
                        logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                        return f"Trade id {last_trade.get('uid')} is already closed."
                    else:
                        logger.info("Price broke 20 day LOW. CLOSING LONG.")
                        close_trade.delay(last_trade, current_price, product_id, TrendPeriod.TWENTY)
                        last_trade.update({'state': TradeState.CLOSED})
                        cache_update_last_trades(last_trade, product_id)

                        highs_lows[product_id]["lowest_20day"] = current_price
                        cache.set("highs_lows", highs_lows, TRADES_CACHE_TIMEOUT)

        
    if last_trade.get('state') == TradeState.CLOSED and isinstance(last_trade.get('profit_loss'), Decimal):
        if last_trade.get('profit_loss') < 0:
            # Open trade if the price braks out 20 day high or 20 day low
            if current_price > highest_20day:
                if not lock_aquired('20_DAY_HIGH_LONG_OPEN', product_id, last_trade.get('uid'), lock_for_hours=1):
                    logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                    return f"Trade id {last_trade.get('uid')} is already closed."
                else:
                    logger.info("Price broke 20 day HIGH. Opening a LONG Trade for %s", product_id)
                    # Breakout signal buy long
                    new_last_trade = create_trade_draft(
                        TradeState.OPEN, 
                        TradeType.LONG, 
                        TrendPeriod.TWENTY
                    ) 
                    open_trade.delay(ticker_data, new_last_trade)
                    cache_update_last_trades(new_last_trade, product_id)

                    highs_lows[product_id]["highest_20day"] = current_price
                    cache.set("highs_lows", highs_lows, TRADES_CACHE_TIMEOUT)
            
            if current_price < lowest_20day:
                # Breakout signal buy short
                if not lock_aquired('20_DAY_LOW_SHORT_OPEN', product_id, last_trade.get('uid'), lock_for_hours=1):
                    logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                    return f"Trade id {last_trade.get('uid')} is already closed."
                else:
                    logger.info("Price broke 20 day LOW. Opening a SHORT Trade for %s", product_id)
                    new_last_trade = create_trade_draft(
                        TradeState.OPEN, 
                        TradeType.SHORT, 
                        TrendPeriod.TWENTY
                    )
                    open_trade.delay(ticker_data, new_last_trade)
                    cache_update_last_trades(new_last_trade, product_id)

                    highs_lows[product_id]["lowest_20day"] = current_price
                    cache.set("highs_lows", highs_lows, TRADES_CACHE_TIMEOUT)

    
        if last_trade.get('profit_loss') > 0:
            # Watch for S2 now
            if current_price > highest_55day:
                # Breakout signal buy long
                if not lock_aquired('55_DAY_HIGH_LONG_OPEN', product_id, last_trade.get('uid'), lock_for_hours=1):
                    logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                    return f"Trade id {last_trade.get('uid')} is already closed."
                else:
                    logger.info("Price broke 55 day HIGH. Opening a LONG Trade")
                    new_last_trade = create_trade_draft(
                        TradeState.OPEN, 
                        TradeType.LONG, 
                        TrendPeriod.FIFTYFIVE
                    )
                    open_trade.delay(ticker_data, new_last_trade)
                    cache_update_last_trades(new_last_trade, product_id)

                    highs_lows[product_id]["highest_55day"] = current_price
                    cache.set("highs_lows", highs_lows, TRADES_CACHE_TIMEOUT)
            
            if current_price < lowest_55day:
                # Breakout signal buy short
                if not lock_aquired('55_DAY_LOW_SHORT_OPEN', product_id, last_trade.get('uid'), lock_for_hours=1):
                    logger.info(f"Trade id {last_trade.get('uid')} is already closed.")
                    return f"Trade id {last_trade.get('uid')} is already closed."
                else:
                    logger.info("Price broke 55 day LOW. Opening a SHORT Trade")
                    new_last_trade = create_trade_draft(
                        TradeState.OPEN, 
                        TradeType.SHORT, 
                        TrendPeriod.FIFTYFIVE
                    )
                    open_trade.delay(ticker_data, new_last_trade)
                    cache_update_last_trades(new_last_trade, product_id)

                    highs_lows[product_id]["lowest_55day"] = current_price
                    cache.set("highs_lows", highs_lows, TRADES_CACHE_TIMEOUT)

    
    # TODO upadate highs and lowsin chache
    # with curent comparison

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
        pair.highest_20day  = highest_20day
        pair.lowest_20day   = lowest_20day
        pair.highest_10day  = highest_10day
        pair.lowest_10day   = lowest_10day
        pair.highest_55day  = highest_55day
        pair.lowest_55day   = lowest_55day
        pair.save()
    cache.set("highs_lows", cache_data, TRADES_CACHE_TIMEOUT)
    return True
