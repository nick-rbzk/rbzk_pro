# Generated by Django 4.2.13 on 2025-01-21 02:15

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0004_formsubmission_created'),
    ]

    operations = [
        migrations.AlterField(
            model_name='formsubmission',
            name='created',
            field=models.DateTimeField(default=datetime.datetime(2025, 1, 21, 2, 15, 9, 700359, tzinfo=datetime.timezone.utc)),
        ),
    ]
