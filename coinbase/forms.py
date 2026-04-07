from django import forms
from .models import TradingPair


class TradingPairForm(forms.Form):
    # This will hold our custom choices
    trading_pairs = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "form-check-input"}
        ),
        required=False,
    )
    action = forms.CharField(widget=forms.HiddenInput())
    
    def __init__(self, *args, is_active, **kwargs):
        super().__init__(*args, **kwargs)

        self.is_active = is_active
        if self.is_active is not None:
            if self.is_active:
                self.set_active()
            else:
                self.set_inactive()
        else:
            all_choices =  TradingPair.objects.all()
            self.set_choices(all_choices)
    
    def set_active(self, *args, **kwargs):
        self.fields["trading_pairs"].widget.attrs["checked"] = True
        self.fields["trading_pairs"].widget.attrs["disabled"] = True
        active_pairs = TradingPair.objects.filter(is_active=True)

        self.set_choices(active_pairs)
    
    def set_inactive(self, *args, **kwargs):

        inactive_pairs = TradingPair.objects.filter(is_active=False)

        self.set_choices(inactive_pairs)

    def set_choices(self, pairs):
        choices = [(pair.pk, f"{pair.ticker_symbol}") for pair in pairs]
        self.fields['trading_pairs'].choices = choices
        self.fields['action'].choices = '1'