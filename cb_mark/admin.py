from datetime import datetime
from django.contrib import admin
from django.core.cache import cache
from .models import *

# Register your models here.
admin.site.register(TradingPair)
admin.site.register(WebSocketTask)


@admin.register(DayPriceLog)
class DayPriceLogAdmin(admin.ModelAdmin):
    list_display = ('ticker_symbol', "high_price", "low_price", "spread",'last_price', 'n_atr', 'coinbase_date', "num_messages","updated_at")
    exclude = ('price_history',)
    search_fields = ('ticker_symbol', "created_at",) 
    # list_filter = ("created_at",)

    def num_messages(self, obj):
        return len(obj.price_history)
    
    def spread(self, obj):
        if obj.high_price and obj.low_price:
            return obj.high_price - obj.low_price
        return ""


@admin.register(BreakOutSignal)
class BreakOutSignalAdmin(admin.ModelAdmin):
    list_display = ("trading_pair", "break_out_price", "trend_period", "trend_direction", "created_at") 


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    last_price = None
    currency = ""
    list_display = ("trade_pair", "state", "type", 
                    "enter_price", "stop_loss_price", 
                    "current_price", "if_sold", "exit_price", "profit_loss", "created_at")
    search_fields = ["pk", "ticker_symbol", "state", "type"]
    def trade_pair(self, obj):
        self.currency = obj.trading_pair.ticker_symbol
        return self.currency
    
    def current_price(self, obj):
        d_log = DayPriceLog.objects.get(
            coinbase_date = datetime.now(),
            ticker_symbol=self.currency
        )
        self.last_price = d_log.last_price
        return d_log.last_price
    
    def if_sold(self, obj):
        if obj.num_shares is not None and self.last_price is not None and obj.dollar_amount is not None:
            if obj.type == TradeType.SHORT:
                return '{0:.2f}'.format(obj.dollar_amount - (obj.num_shares * self.last_price))
            if obj.type == TradeType.LONG:
                return '{0:.2f}'.format((obj.num_shares * self.last_price) - obj.dollar_amount)
    if_sold.short_description = "if sold @ current price"
    
