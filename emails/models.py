from django.db import models

# Create your models here.
class BreakPeriod(models.IntegerChoices):
    TEN         = 10, '10 days'
    TWENTY      = 20, '20 days'
    FIFTYFIVE   = 55, '55 days'

class PriceBreakEmail(models.Model):
    sent_on     = models.DateField(null=True)
    period      = models.CharField(
        blank=False, 
        null=True,
        choices=BreakPeriod.choices,
        max_length=10
    )
    product_id  = models.CharField(
        blank=False, 
        null=True,
        max_length=64
    )
    created_at  = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True, auto_now_add=False)