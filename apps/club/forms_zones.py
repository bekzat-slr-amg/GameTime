from django import forms

from apps.bookings.models import ClubSettings
from apps.equipment.models import Zone

INPUT = "input"


class ZoneForm(forms.ModelForm):
    class Meta:
        model = Zone
        fields = ("name", "description", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "description": forms.TextInput(attrs={"class": INPUT}),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class ClubSettingsForm(forms.ModelForm):
    class Meta:
        model = ClubSettings
        fields = ("opening_time", "closing_time", "timezone")
        widgets = {
            "opening_time": forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": INPUT}),
            "closing_time": forms.TimeInput(format="%H:%M", attrs={"type": "time", "class": INPUT}),
            "timezone": forms.TextInput(attrs={"class": INPUT}),
        }
