from django import forms 
  
# creating a form  
class JobForm(forms.Form): 
    job_start_date = forms.DateTimeField(widget=forms.TextInput(attrs={
        'required': True,
        'placeholder': 'Start Date', 
        'style': 'width: 100%;',
        'class': 'form-control',
        'autocomplete': "off",
    })) 
    job_start_time = forms.DateTimeField(widget=forms.TextInput(attrs={
        'required': True,
        'placeholder': 'Start Time', 
        'style': 'width: 100%;',
        'class': 'form-control',
        'autocomplete': "off",
    })) 
    job_end_date = forms.DateTimeField(widget=forms.DateTimeInput(attrs={
        'required': True,
        'placeholder': 'End Date', 
        'style': 'width: 100%; margin-bottom: 20px', 
        'class': 'form-control',
        
        'autocomplete': "off",
    })) 
    job_end_time = forms.DateTimeField(widget=forms.DateTimeInput(attrs={
        'required': True,
        'placeholder': 'End Time', 
        'style': 'width: 100%; margin-bottom: 20px', 
        'class': 'form-control',
        'autocomplete': "off",
    }))
    confirmation = forms.CharField(required=True, widget=forms.TextInput(attrs={
        'required': True,
        'placeholder': "Confirmation#",
        'style': 'width: 100%; margin-bottom: 20px', 
        'class': 'form-control',
        'autocomplete': "off",
    }))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={
        'placeholder': "Notes",
        'style': 'width: 100%; margin-bottom: 20px', 
        'class': 'form-control'
    }))