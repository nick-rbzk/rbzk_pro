import json
import logging

from datetime import datetime
from celery import shared_task
from coinbase.models import DayPriceLog


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
    ]


@shared_task
def record_price(pair_id, data):
    try:
        json_data = json.loads(data)
        if json_data.get('type') == 'ticker':
            date = datetime.strptime(json_data.get('time'), "%Y-%m-%dT%H:%M:%S.%f%z")
            
            price_log, created = DayPriceLog.objects.get_or_create(
                coinbase_date=date,
                ticker_symbol=json_data.get('product_id'),
            )

            if created:
                print("New Object")

            price_data = {}
            for field in desired_db_price_history_fields:
                # TODO 
                # include the timestamp of my machine time.
                # this way we can tell when the trade happened on coinbase side
                # vs how long it took for us to receice a message about it.

                price_data[field] = json_data.get(field)

            price_data = json.dumps(price_data)
            price_log.price_history.append(price_data)
            price_log.save()
            

            # TODO:
            # setup email for webvision ltd
            # Turtle trading
            # what other channles are there in websocket connection?

            logger.debug(f"Price update: price_data")
            
    except Exception as e:
        logger.error(f"Error processing message: {e}")
