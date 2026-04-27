import os
import logging
from datetime import datetime, timedelta
from celery import shared_task
from django.core.mail import send_mail, get_connection
from django.template.loader import render_to_string
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.core.cache import cache
from coinbase.models import TradeType, TrendPeriod, TradeState
logger = logging.getLogger(__name__)



@shared_task()
def trade_opened_email(*args, **kwargs):
    trade = cache.get("last_trade") 
    context = {}
    if trade is None:
        print("NO trade found")
        return False
    
    context["currency"] = trade.ticker_symbol

    if trade.type == TradeType.SHORT:
        context["trade_type"] = "SHORT"
        context["stop_loss_amount"] = abs(trade.dollar_amount - (trade.num_shares * trade.stop_loss_price))
    if trade.type == TradeType.LONG:
        context["trade_type"] = "LONG"
        context["stop_loss_amount"] = abs((trade.num_shares * trade.stop_loss_price) - trade.dollar_amount)

    context["enter_price"] = trade.enter_price
    context["stop_loss_price"] = trade.stop_loss_price
    context["dollar_amount"] = trade.dollar_amount
    context["num_shares"] = trade.num_shares

    if trade.buy_signal.trend_period == TrendPeriod.FIFTYFIVE:
        if trade.type == TradeType.SHORT:
            context["trend_period"] = "55 day LOW"
        if trade.type == TradeType.LONG:
            context["trend_period"] = "55 day HIGH"
    if trade.buy_signal.trend_period == TrendPeriod.TWENTY:
        if trade.type == TradeType.SHORT:
            context["trend_period"] = "20 day LOW"
        if trade.type == TradeType.LONG:
            context["trend_period"] = "20 day HIGH"
    context["trade_id"] = trade.pk
    html_template = render_to_string(
        os.path.join(settings.BASE_DIR, 'emails/templates/open_trade_email.html'), 
        context
    )
    subject = 'OPENED a New Trade'
    plain_message = "OPENED a New Trade"
    html_message = html_template
    from_email = "info@webvision.ltd"
    recipient_list = ['info@webvision.ltd',]

    try:
        send_mail(
            subject,
            plain_message,
            from_email,
            recipient_list,
            html_message=html_message,
        )
    except Exception as e:
        logger.error("Sending email about deletion failed: %s", e)



@shared_task()
def trade_closed_email(*args, **kwargs):
    trade = cache.get("last_trade") 
    context = {}
    if trade is None:
        print("NO trade found")
        return False
    
    context["currency"] = trade.ticker_symbol
    context["result"] = trade.profit_loss
    context["opened_on"] = trade.created_at
    context["closed_on"] = trade.updated_at
    context["days_active"] = trade.updated_at - trade.created_ats
    context["exit_price"] = trade.exit_price

    if trade.type == TradeType.SHORT:
        context["trade_type"] = "SHORT"
        context["stop_loss_amount"] = trade.dollar_amount - (trade.num_shares * trade.stop_loss_price)
    if trade.type == TradeType.LONG:
        context["trade_type"] = "LONG"
        context["stop_loss_amount"] = (trade.num_shares * trade.stop_loss_price) - trade.dollar_amount

    context["enter_price"] = trade.enter_price
    context["stop_loss_price"] = trade.stop_loss_price
    context["dollar_amount"] = trade.dollar_amount
    context["num_shares"] = trade.num_shares

    
    if trade.sell_signal.trend_period == TrendPeriod.TWENTY:
        if trade.type == TradeType.SHORT:
            context["trend_period"] = "20 day LOW"
        if trade.type == TradeType.LONG:
            context["trend_period"] = "20 day HIGH"
    if trade.sell_signal.trend_period == TrendPeriod.TEN:
        if trade.type == TradeType.SHORT:
            context["trend_period"] = "10 day LOW"
        if trade.type == TradeType.LONG:
            context["trend_period"] = "10 day HIGH"

    context["trade_id"] = trade.pk
    html_template = render_to_string(
        os.path.join(settings.BASE_DIR, 'emails/templates/open_trade_email.html'), 
        context
    )
    subject = 'CLOSED a Trade'
    plain_message = "CLOSED a Trade"
    html_message = html_template
    from_email = "info@webvision.ltd"
    recipient_list = ['info@webvision.ltd',]

    try:
        send_mail(
            subject,
            plain_message,
            from_email,
            recipient_list,
            html_message=html_message,
        )
    except Exception as e:
        logger.error("Sending email about deletion failed: %s", e)