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
    # price_history string format "price:coinbase_time:my_machine_time"
    created_at      = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True, auto_now_add=False)
    # average difference in milisecs between coinbase timestamp 
    # for each price ticker and the time we get websocket message

    def __str__(self):
        return f"{self.ticker_symbol}"
