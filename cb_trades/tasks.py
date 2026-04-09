import json
import logging

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from celery import shared_task
from coinbase.models import DayPriceLog
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from rbzk.settings import CACHE_BIN_KEYS, BIN_TIMEOUT

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


def get_full_bin():
    """
        Returns the full bin, from redis cache,
        with array storage, which is used by websocket to write ticker data.
        Returned bin marked as disabled
        Previously disabled bin, one with empty array, is marked enabled.
    """
    cached_bins = [cache.get(bin) for bin in CACHE_BIN_KEYS]
    full_bin = None
    if None in cached_bins:
        return False
    for b in cached_bins:
        b['inuse'] = not b['inuse']
    for b in cached_bins:
        key = {
            'name':b['name'],
            'inuse': b['inuse'],
            'storage': cache.get(b['name'])['storage']
        }
        cache.set(b['name'], key, BIN_TIMEOUT)
        if not key['inuse']:
            full_bin = key['name']
    return full_bin



@shared_task
def redis_store_price(data):
    ticker_data = json.loads(data)
    if ticker_data.get('type') == 'ticker':
        now = datetime.now(timezone.utc)
        ticker_data['time_received'] = now.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
        bins = [cache.get(bin) for bin in CACHE_BIN_KEYS]
        if None in bins:
            set_cache_bins()
            bins = [cache.get(bin) for bin in CACHE_BIN_KEYS]
        bin_to_use_name = None
        bin_to_use = None
        for b in bins:
            if b['inuse']:
                bin_to_use_name = b['name']
        
        if bin_to_use_name is not None:
            bin_to_use = cache.get(bin_to_use_name)
        
        bin_to_use["storage"].append(ticker_data)
        cache.set(bin_to_use_name, bin_to_use, BIN_TIMEOUT)
        return True


@shared_task
def db_record_price():
    bin_name = get_full_bin()
    full_bin = None
    if bin_name:
        full_bin = cache.get(bin_name)
    if full_bin is None:
        return "Full Bin was not found"
    db_data = {}
    for message in full_bin["storage"]:
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
                    ticker_symbol=key
                )
                if yestarday_dpl is not None:
                    one = abs(price_log.high_price - price_log.low_price)
                    two = abs(yestarday_dpl.last_price  - price_log.high_price)
                    three = abs(yestarday_dpl.last_price - price_log.low_price)
                    price_log.n_atr = max([one, two, three])

            except ObjectDoesNotExist as e:
                print(e)

            price_log.last_price = current_price

            price_log.save()

            logger.debug(f"Price update: price_data")

            full_bin["storage"] = []
            cache.set(bin_name, full_bin, BIN_TIMEOUT)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")




# S1    
#   - 20 days breakout - entrance
#   - 10 days breakout in opposite direction - exit  
#
# Filters:
#   if the trade before a current four-week breakout 
#       was a 2N (N=volatility) loss (regardless of direction) => execute new trade
#   else: 
#       Watch for S2
#  
# S2
#   - 55 days breakout - entrance
#   - 20 days breakout in the opposite direction - exit




@shared_task
def turtle_strategy_s1(data):
    ticker_data     = json.loads(data)
    # s1 = Strategy.objects.get(name='Turtle_s1')
    # s2 = Strategy.objects.get(name='Turtle_s2')
    # last_trade = Trade.objects.filter(ticker_symbol=ticker_data.get('priduct_id')).order_by('created').last()
    day_logs = DayPriceLog.objects.filter(ticker_symbol=ticker_data.get('product_id')).order_by('created')
    last_trade = {}
    s1 = {}
    s2 = {}
    if s1.is_active:
        current_price   = Decimal(ticker_data.get('price'))
        ten_day_highs   = []
        ten_day_lows    = []
        twenty_d_highs  = []
        twenty_d_lows   = []
        idx = 1 
        for dl in day_logs[0:20]: # check for precision
            if idx > 9:
                ten_day_highs.append(dl.high_price)
                ten_day_lows.append(dl.low_price)
            
            twenty_d_highs.append(dl.high_price)
            twenty_d_lows.append(dl.low_price)
            idx += 1
        
        highest_20day   = max(twenty_d_highs)
        lowest_20day    = min(twenty_d_lows)
        highest_10day   = max(ten_day_highs)
        lowest_10day    = max(ten_day_lows)

        if last_trade.state == 'open':
            if last_trade.type == 'short_sell':
                # close the trade if price breaks the 10 day in the opposite direction of entry
                if current_price > highest_10day:
                    # sell the asset
                    last_trade.state = 'closed'
                    last_trade.profit_loss = last_trade.enter_price - current_price
                    last_trade.save()
            if last_trade.type == 'long_buy':
                if current_price < lowest_10day:
                    # sell the asset
                    last_trade.state = 'closed'
                    last_trade.profit_loss = current_price = last_trade.enter_price
                    last_trade.save()

        if last_trade.profit_loss < 0  and last_trade.state == 'closed':
            if current_price > highest_20day:
                # Breakout signal buy long
                # Create a new Trade
                pass
            if current_price < lowest_20day:
                # Breakout signal buy short
                # Create a new Trade
                pass
        
        if last_trade.profit_loss > 0  and last_trade.state == 'closed':
            pass
            # Watch for S2 now
            # s1.is_active = False
            # s2.is_active = True
            
    else:
        # do we even need this?
        # s1.is_active = False
        # s2.is_active = True
        # watch for s2
        pass


@shared_task
def turtle_strategy_s2(data):
    ticker_data     = json.loads(data)
    # s1 = Strategy.objects.get(name='Turtle_s1')
    # s2 = Strategy.objects.get(name='Turtle_s2')
    # last_trade = Trade.objects.filter(ticker_symbol=ticker_data.get('priduct_id')).order_by('created').last()
    # last_trade = s2.trades.objects.filter(ticker_symbol=ticker_data.get('priduct_id')).order_by('created').last()
    day_logs = DayPriceLog.objects.filter(ticker_symbol=ticker_data.get('product_id')).order_by('created')
    last_trade = {}
    s1 = {}
    s2 = {}
    if s2.is_active:
        current_price   = Decimal(ticker_data.get('price'))
        high_prices     = []
        low_prices      = []
        for dl in day_logs[0:55]:
            high_prices.append(dl.high_price)
            low_prices.append(dl.low_price)
        
        highest_55day   = max(high_prices)
        lowest_55day    = min(low_prices)
        if last_trade.state == 'closed':
            if current_price > highest_55day:
                # Breakout signal buy long
                # Create new Trade
                pass
            if current_price < lowest_55day:
                # Breakout signal buy short
                # Create new Trade
                pass
        else:
            if last_trade.type == 'short_sell':
                # exit if current_price is highrer than 20 days high
                pass
            
            if last_trade.type == 'long_buy':
                # exit if current_price is lower then a 20 days low
                pass


    

