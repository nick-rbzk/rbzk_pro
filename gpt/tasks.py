from celery import shared_task
import requests


@shared_task()
def hello_world():
    print("Hello World. I'm a working task.")
    requests.post("https://httpbin.org/delay/5")
    return [99, 80]