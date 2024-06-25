from django import forms
from .models import Lot

class LotForm(forms.ModelForm):
    class Meta:
        model = Lot
        fields = ['title', 'description', 'seller', 'location', 'start_time', 'end_time', 'images', 'document_type']
