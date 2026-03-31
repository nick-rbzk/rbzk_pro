import json
import logging

from decimal import Decimal
from datetime import datetime, timezone
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

                if field == 'time':
                    price_data['coinbase_time'] = json_data.get(field)
                else:
                    price_data[field] = json_data.get(field)

            now = datetime.now(timezone.utc)
            price_data['my_machine_time'] = now.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            price_data = json.dumps(price_data)
            price_log.price_history.append(price_data)
            price_log.last_price = Decimal(json_data.get('price'))
            price_log.save()
            
                # {
                #     "product_id": "XLM-USD", 
                #     "price": "0.168092", 
                #     "open_24h": "0.164013", 
                #     "volume_24h": "36051443.08864261", 
                #     "low_24h": "0.161126", 
                #     "high_24h": "0.173816", 
                #     "volume_30d": "1034575394.27383714", 
                #     "best_bid": "0.168056", 
                #     "best_bid_size": "1631.02895460", 
                #     "best_ask": "0.168122", 
                #     "best_ask_size": "1462.50000000", 
                #     "side": "sell", 
                #     "coinbase_time":   "2026-03-30T20:00:00.232992Z", 
                #     "my_machine_time": "2026-03-30T20:00:00.608966+0000",
                #     "last_size": "501.1846", 
                # }


            # TODO
            # setup email for webvision ltd
            # what other channles are there in websocket connection?

            logger.debug(f"Price update: price_data")
            
    except Exception as e:
        logger.error(f"Error processing message: {e}")
