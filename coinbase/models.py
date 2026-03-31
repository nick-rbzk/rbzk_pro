import math

from django.db import models
from django.contrib.postgres.fields import ArrayField

# Create your models here.

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
    running_task    = models.OneToOneField(WebSocketTask, on_delete=models.SET_NULL, null=True, blank=True)

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
    last_price      = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    created_at      = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True, auto_now_add=False)
    n_atr   = models.CharField(max_length=1024, blank=True, null=True, help_text='N as Average True Range')

    def __str__(self):
        return f"{self.ticker_symbol}"

    

# class BreakOutSignal(models.Model):
#     break_out_price = models.CharField(max_length=256, null=False, blank=False)
#     # direction = ['short_sell', 'long_buy']
#     # event = ['e.g','20daylow', '20dayhigh', '55dayhigh', '55daylow]
#     # result = ['winner', 'looser']
#     # trade = models.ForeignKey(Trade)
#     created_at      = models.DateTimeField(auto_now=False, auto_now_add=True)
#     updated_at      = models.DateTimeField(auto_now=True, auto_now_add=False)


# class Trade(models.Model):
#     # state = ['open', 'closed']
#     # type = ['short_sell', 'long_buy']
#     # enter_price = models.DecimalField(max_length=128, null=False, blank=False)
#     # stop_loss_price = models.DecimalField(max_length=128, null=False, blank=False)
#     # exit_price = models.DecimalField(max_length=128, null=True, blank=True)
#     # profit_loss = models.DecimalField(max_lenght=128, null=True, blank=True)
#     # signal = models.ForeignKey(BreakOutSignal)
#     created_at      = models.DateTimeField(auto_now=False, auto_now_add=True)
#     updated_at      = models.DateTimeField(auto_now=True, auto_now_add=False)






# Error 104 :Connection closed by peer Solution
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
    


                                
                                
                                
                                
                                
                                
                                
                                





