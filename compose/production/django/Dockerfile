FROM python:3.13-trixie

ENV PYTHONUNBUFFERED 1

RUN apt-get update \
  # dependencies for building Python packages
  && apt-get install -y build-essential \
  # psycopg dependencies
  && apt-get install -y libpq-dev \
  # Translations dependencies
  && apt-get install -y gettext \
  && apt-get install -y htop \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

RUN addgroup --system django \
    && adduser --system --ingroup django django

# Requirements are installed here to ensure they will be cached.
COPY ./requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

# copy certificates
COPY ./compose/production/django/entrypoint /entrypoint

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint
RUN chown django /entrypoint

COPY ./compose/production/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start
RUN chown django /start

COPY ./compose/production/django/celery/worker_default/start /start-default-celeryworker
RUN sed -i 's/\r$//g' /start-default-celeryworker
RUN chmod +x /start-default-celeryworker
RUN chown django /start-default-celeryworker

COPY ./compose/production/django/celery/worker_high/start /start-high-celeryworker
RUN sed -i 's/\r$//g' /start-high-celeryworker
RUN chmod +x /start-high-celeryworker
RUN chown django /start-high-celeryworker

COPY ./compose/production/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r$//g' /start-celerybeat
RUN chmod +x /start-celerybeat
RUN chown django /start-celerybeat

COPY ./compose/production/django/celery/flower/start /start-flower
RUN sed -i 's/\r$//g' /start-flower
RUN chmod +x /start-flower

RUN mkdir /rbzk

RUN mkdir /rbzk/logs 
RUN touch /rbzk/logs/access.log
RUN touch /rbzk/logs/error.log


RUN mkdir -p /rbzk/staticfiles \
    && mkdir -p /rbzk/mediafiles \
    && chown -R django:django /rbzk \
    && chmod -R 775 /rbzk/staticfiles \
    && chmod -R 775 /rbzk/mediafiles \
    && chmod -R 775 /rbzk/home \
    && chmod g+s /rbzk/staticfiles \
    && chmod g+s /rbzk/mediafiles \
    && chmod g+s /rbzk/home \

WORKDIR /rbzk

# copy project code
COPY . .

USER django

ENTRYPOINT ["/entrypoint"]