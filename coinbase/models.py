import math
from django.db import models
from django.db.models.signals import pre_save
from django.contrib.postgres.fields import ArrayField

# Create your models here.


class TradeState(models.IntegerChoices):
    CLOSED  = 0
    OPEN    = 1


class TradeType(models.IntegerChoices):
    SHORT   = 3
    LONG    = 5


class TrendPeriod(models.IntegerChoices):
    STOP_LOSS   = -1
    TEN         = 10
    TWENTY      = 20
    FIFTYFIVE   = 55

class SignalType(models.IntegerChoices):
    BYU     = 9
    SELL    = 12

class WebSocketTask(models.Model):
    task_id         = models.CharField(max_length=256, blank=False, null=True)
    name            = models.CharField(max_length=1024, blank=False, null=True)
    stop_requested  = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class TradingPair(models.Model):
    ticker_symbol   = models.CharField(max_length=256, blank=False, null=True)
    name            = models.CharField(max_length=1024, blank=False, null=True)
    is_active       = models.BooleanField(default=False, blank=False, null=False)
    running_task    = models.ForeignKey(WebSocketTask,on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        state = 'OFF'
        if self.is_active:
            state = 'ON'
        return f"{self.ticker_symbol} -- {state}"
    

class DayPriceLog(models.Model):
    coinbase_date   = models.DateField(max_length=1024, null=True, blank=True)
    ticker_symbol   = models.CharField(max_length=1024, blank=True, null=True)
    price_history   = ArrayField(
        models.CharField(max_length=1024, blank=True, null=True),
        default=list,
        null=True,
        blank=False,
        )
    open_price      = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    high_price      = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    low_price       = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    last_price      = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True, help_text="Close price")
    created_at      = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True, auto_now_add=False)
    n_atr           = models.CharField(max_length=1024, blank=True, null=True, help_text='N as Average True Range')

    def __str__(self):
        return f"{self.ticker_symbol} - ticker messages: {len(self.price_history)}"


class Strategy(models.Model):
    name        = models.CharField(max_length=256, null=False, blank=False)
    is_active   = models.BooleanField(default=False)
    

class BreakOutSignal(models.Model):
    signal_type     = models.IntegerField(choices=SignalType, default=TrendPeriod.STOP_LOSS) #Remove a defalut later
    trading_pair    = models.ForeignKey(TradingPair, on_delete=models.SET_NULL, null=True, blank=False)
    ticker_symbol   = models.CharField(max_length=1024, blank=True, null=True)
    break_out_price = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    trend_direction = models.IntegerField(choices=TradeType.choices)
    trend_period    = models.IntegerField(choices=TrendPeriod.choices)
    created_at      = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True, auto_now_add=False)


class Trade(models.Model):
    trading_pair    = models.ForeignKey(TradingPair, on_delete=models.SET_NULL, null=True, blank=False)
    ticker_symbol   = models.CharField(max_length=1024, blank=True, null=True)
    buy_signal      = models.ForeignKey(BreakOutSignal, on_delete=models.SET_NULL, null=True, blank=False, related_name="open_trades")
    sell_signal     = models.ForeignKey(BreakOutSignal, on_delete=models.SET_NULL, null=True, blank=False, related_name="closed_trades")
    state           = models.IntegerField(choices=TradeState.choices)
    type            = models.IntegerField(choices=TradeType.choices)
    enter_price     = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=False)
    stop_loss_price = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=False)
    exit_price      = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    profit_loss     = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    dollar_amount   = models.DecimalField(max_digits=24, decimal_places=2, null=True, blank=True)
    num_shares      = models.DecimalField(max_digits=24, decimal_places=2, null=True, blank=True, help_text="Shares purchased at enter price")
    created_at      = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True, auto_now_add=False)

    def __str__(self):
        return f"{self.state} - {self.type}"

def assign_trading_pair(sender, instance, *args, **kwargs):
    if instance.trading_pair == None:
        pair = TradingPair.objects.get(ticker_symbol=instance.ticker_symbol)
        instance.trading_pair = pair
pre_save.connect(assign_trading_pair, sender=Trade)

# TODO


# ❌ include compression header for websocket connection
# ❌ autorestart the websocket on error
# wsClient = cbpro.WebsocketClient(url="wss://ws-feed.pro.coinbase.com",
#                                 products=["BTC-USD", "ETH-USD"],
#                                 channels=["ticker"])
# wsClient.start()
# while true:
#         if wsClient.error:
#                 wsClient.close()
#                 wsClient.error = None
#                 wsClient.start()
#         time.sleep(1)


#  Celery have 3 Queus by priority.
#   1-high=websocket messages
#   2-medium = trading strategies
#   3 the rest.

# Error 104 :Connection closed by peer Solution





# ❌ historical data 55 days from coin base.
# clean up migrations




# ✅setup email for webvision ltd
# ✅ S1 Strategie with a model
# ✅ S2 strategie with a model
# ✅ BUG :After a long websocket job with a lot of messages only 1 gets added to db
# ✅one websocket connection never multiple
# ✅Mark Trading pairs  outside of celery task
# ✅struckture websocket messages
# ✅write ws messages in to redis
# ✅every minute empty redis cache
# ✅two redis entries to hold messages one by one.
# ✅when the celery tasks runs too empty one redis array
# ✅the other one is being prepopulated
# ✅flip the flag
# ✅empty redis array is being prepopulted
# ✅run the query against the full one.









# BTC

# {"product_id": "BTC-USD", 
#  "price": "72396", 
#  "open_24h": "71387.32", 
#  "volume_24h": "9972.91584321", 
#  "low_24h": "70468.74", 
#  "high_24h": "72568.12", 
#  "volume_30d": "246791.85356055", 
#  "best_bid": "72396.00", 
#  "best_bid_size": "0.02101902", 
#  "best_ask": "72396.01", 
#  "best_ask_size": "0.10796979", 
#  "side": "sell", "time": 
#  "2026-04-09T20:58:30.565959Z", 
#  "last_size": "0.00000013", 
#  "time_received": "2026-04-09T20:58:30.291124+0000"
#  }


# ETH
# {"product_id": "ETH-USD", 
#  "price": "2212.77", 
#  "open_24h": "2210.1", 
#  "volume_24h": "170827.46370036", 
#  "low_24h": "2156.8", 
#  "high_24h": "2229.99", 
#  "volume_30d": "4375438.10060484", 
#  "best_bid": "2212.74", 
#  "best_bid_size": "5.48670503", 
#  "best_ask": "2212.80", 
#  "best_ask_size": "0.79800000", 
#  "side": "buy", 
#  "time": "2026-04-09T20:58:27.862620Z", 
#  "last_size": "0.67793019", 
#  "time_received": "2026-04-09T20:58:30.299992+0000"
#  }



#XLM
# {"product_id": "XLM-USD", 
#  "price": "0.157038", 
#  "open_24h": "0.15829", 
#  "volume_24h": "50487761.91398750", 
#  "low_24h": "0.152301", 
#  "high_24h": "0.15929", 
#  "volume_30d": "960992494.38355363", 
#  "best_bid": "0.156998", 
#  "best_bid_size": "418.12226300", 
#  "best_ask": "0.157038", 
#  "best_ask_size": "453.47059730", 
#  "side": "buy", 
#  "time": "2026-04-09T20:58:29.755525Z", 
#  "last_size": "61.4660146", 
#  "time_received": "2026-04-09T20:58:30.307268+0000"}






















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



#            N daily volatility or average true range or ATR calculation
# 
#   1.The distance from today’s high to today’s low 
#   2.The distance from yesterday’s close to today’s high 
#   3.The distance from yesterday’s close to today’s low 

#   price_logs = DayPriceLog.objects.all().filter('-created')
#   today = price_logs.last()
#   yestarday = price_logs.last(2)
#   one = abs(today.high - today.low)
#   two = abs(yestarday.last_price - today.high)
#   three = abs(yestarday.last_price - today.low)
#   N = max([one, two, three])



#                       N as Risk Management
# 
#   portfolio_size = 100_000
#   portfolio_risk_percentage  = 2  # Store in settings
#   account_risk = portfolio_risk_percentage / 100
#   risk_multiplier = 2  # Store in settings
#   risk = N * current_btc_price
#   contract_risk =  risk * risk_multiplier
#   num_contracts_to_purchase = math.floor((portfolio_size * account_risk) / contract_risk)

# def manage_risk(portfolio_size, risk_percentage, N_atr, risk_multiplier, current_comod_price):
# 	account_risk = (risk_percentage / 100) * portfolio_size

# 	# N_atr or N is called volatility here
# 	# In this case it volatility * current_stock_price
# 	risk = N_atr * current_comod_price 

# 	# Risk Management contract_risk can also be called N dollar value
# 	contract_risk = risk * risk_multiplier

# 	num_of_contract_to_purchase = math.floor(account_risk / contract_risk)
# 	print("Account Risk :", account_risk)
# 	print("Risk percentage :", risk)
# 	print("Contract Risk :", contract_risk)
# 	print("Num contracts to buy :", num_of_contract_to_purchase)




# print("_______________Swiss Frank Example_______________")
# manage_risk(150_000, 1.5, 4, 2, 100)

# print("_________Mini Corn Example______________________")
# manage_risk(25_000, 2, 7, 3, 10)

# print("_______________________________")
# manage_risk(100_000, 2, 7, 2, 50)

# print("_________________Live Cattle example________________________")
# manage_risk(50_000, 2, 0.80, 2, 400)
# 400 is a price of contract
# 74 is a price of stock
# kinda like price of bitcoin is e.g. 68,750
# price of short or long futures is 347.00





#                       Stop Loss calculation
#   N meaning daily volatility 
#   stop_loss_or_exit_price_for_long = entry_price - (2 * N)
#   stop_loss_or_exit_price_for_short = entry_price + (2 * N)
    


                                
                                


