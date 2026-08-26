#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

# python manage.py collectstatic --noinput
# python manage.py makemigrations
# python manage.py migrate
# python manage.py runserver 0.0.0.0:8000



gunicorn rbzk.asgi:application --bind 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker

# TODO
# try daphne fo better debuging.