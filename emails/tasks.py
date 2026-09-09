import os
import logging

from datetime import datetime, date
from celery import shared_task
from django.core.mail import send_mail, get_connection
from django.template.loader import render_to_string
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.core.cache import cache
from cb_mark.models import TradeType, TrendPeriod, TradeState, Trade
from cb_trades.cache_utils import cache_get_last_trade

logger = logging.getLogger(__name__)


@shared_task(name='low_priority:open_trade_email')
def trade_opened_email(trade_uid, trading_pair, *args, **kwargs):
    trade = Trade.objects.filter(
        uid=trade_uid, 
        ticker_symbol=trading_pair,
        ).order_by('created_at').last()
    context = {}
    if not trade:
        logger.error("Can't send new trade email. Missing trade")
        return False
    
    context["currency"] = trade.ticker_symbol

    if trade.type == TradeType.SHORT:
        context["trade_type"] = "SHORT"
        context["stop_loss_amount"] = '{0:.2f}'.format(
            abs(trade.dollar_amount - (trade.num_shares * trade.stop_loss_price))
        )
    if trade.type == TradeType.LONG:
        context["trade_type"] = "LONG"
        context["stop_loss_amount"] = '{0:.2f}'.format(
            abs((trade.num_shares * trade.stop_loss_price) - trade.dollar_amount)
        )
    # '{0:.2f}$'.format(income_after_tax)
    context["enter_price"] = '{0:.2f}'.format(trade.enter_price)
    context["stop_loss_price"] = '{0:.2f}'.format(trade.stop_loss_price)
    context["dollar_amount"] = '{0:.2f}'.format(trade.dollar_amount)
    context["num_shares"] = '{0:.5f}'.format(trade.num_shares)

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
    if trade.buy_signal.trend_period == TrendPeriod.TEN:
        if trade.type == TradeType.SHORT:
            context["trend_period"] = "10 day LOW"
        if trade.type == TradeType.LONG:
            context["trend_period"] = "10 day HIGH"
    if trade.buy_signal.trend_period == TrendPeriod.STOP_LOSS:
        context["trend_period"] = "STOP LOSS"
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


@shared_task(name='low_priority:close_trade_email')
def trade_closed_email(trade_uid, trading_pair, *args, **kwargs):
    trade = Trade.objects.filter(
        uid=trade_uid, 
        ticker_symbol=trading_pair,
        ).order_by('created_at').last()
    context = {}
    if not trade:
        logger.error("Can't send closed trade email. Trade is missing.")
        return False

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
    if trade.buy_signal.trend_period == TrendPeriod.TEN:
        if trade.type == TradeType.SHORT:
            context["trend_period"] = "10 day LOW"
        if trade.type == TradeType.LONG:
            context["trend_period"] = "10 day HIGH"
    if trade.buy_signal.trend_period == TrendPeriod.STOP_LOSS:
        context["trend_period"] = "STOP LOSS"
    
    context["currency"] = trade.ticker_symbol
    context["result"] = '{0:.2f}'.format(trade.profit_loss)
    context["opened_on"] = trade.created_at
    context["closed_on"] = trade.updated_at
    context["days_active"] = trade.updated_at - trade.created_at
    context["exit_price"] = '{0:.2f}'.format(trade.exit_price)

    if trade.type == TradeType.SHORT:
        context["trade_type"] = "SHORT"
        context["stop_loss_amount"] = trade.dollar_amount - (trade.num_shares * trade.stop_loss_price)
    if trade.type == TradeType.LONG:
        context["trade_type"] = "LONG"
        context["stop_loss_amount"] = (trade.num_shares * trade.stop_loss_price) - trade.dollar_amount

    context["enter_price"] = trade.enter_price
    context["stop_loss_price"] = trade.stop_loss_price
    context["dollar_amount"] = trade.dollar_amount
    context["num_shares"] = '{0:.5f}'.format(trade.num_shares)

    
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
        os.path.join(settings.BASE_DIR, 'emails/templates/close_trade_email.html'), 
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

from .models import PriceBreakEmail, BreakPeriod
@shared_task(name="low_priority:ten_day_event_email")
def ten_day_event_email(product_id, current_price, which_10_day):

    last_email = PriceBreakEmail.objects.filter(
        period=10, 
        product_id=product_id
    ).order_by('created_at').last()

    today = date.today()

    if not isinstance(last_email, PriceBreakEmail):
        last_email = PriceBreakEmail.objects.create(
            period = BreakPeriod.TEN,
            product_id=product_id, 
        )
        last_email.save()

    if last_email.sent_on == today:
        return False

    context = {}
    context["product_id"] = product_id
    context["which_10_day"] = which_10_day
    context["current_price"] = current_price
    html_template = render_to_string(
        os.path.join(settings.BASE_DIR, 'emails/templates/ten_day_event_email.html'), 
        context
    )
    subject = f'{product_id} 10 Day Price Break'
    plain_message = f"{product_id} price borke 10 day {which_10_day} at {current_price}$"
    html_message = html_template
    from_email = "info@webvision.ltd"
    recipient_list = ['info@webvision.ltd',]

    error = False
    try:
        send_mail(
            subject,
            plain_message,
            from_email,
            recipient_list,
            html_message=html_message,
        )
        last_email.sent_on = today
        last_email.save()
    except Exception as e:
        logger.error("Sending email about deletion failed: %s", e)
        last_email.sent_on = None
        last_email.save()
        error = True
    finally:
        logger.info("Email operation Completed")
        if not error:
            last_email.sent_on = today
            last_email.save()
