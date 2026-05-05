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
    num_shares      = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True, help_text="Shares purchased at enter price")
    created_at      = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True, auto_now_add=False)

    def __str__(self):
        return f"{self.state} - {self.type}"

def assign_trading_pair(sender, instance, *args, **kwargs):
    if instance.trading_pair == None:
        pair = TradingPair.objects.get(ticker_symbol=instance.ticker_symbol)
        instance.trading_pair = pair
pre_save.connect(assign_trading_pair, sender=Trade)
