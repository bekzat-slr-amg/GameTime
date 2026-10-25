import re

from django import forms
from django.contrib.staticfiles import finders
from django.db.models import Q

from apps.equipment.models import Equipment, Zone

IMAGE_RE = re.compile(r"^images/[\w\-./]+\.(png|jpe?g|webp)$", re.IGNORECASE)
INPUT = "input"


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ("zone", "name", "type", "specs", "hourly_rate", "image", "is_active", "is_featured")
        widgets = {"specs": forms.Textarea(attrs={"rows": 4, "class": f"{INPUT} py-2"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("zone", "name", "type", "hourly_rate", "image"):
            self.fields[name].widget.attrs["class"] = INPUT
        zones = Zone.objects.filter(is_active=True)
        if self.instance.pk:
            zones = Zone.objects.filter(Q(is_active=True) | Q(pk=self.instance.zone_id))
        self.fields["zone"].queryset = zones

    def clean_image(self):
        value = (self.cleaned_data.get("image") or "").strip()
        if not value:
            return ""
        if ".." in value or not IMAGE_RE.match(value):
            raise forms.ValidationError("Укажите путь вида images/pc-pro-01.jpg (png, jpg или webp в папке static/images).")
        if not finders.find(value):
            raise forms.ValidationError("Файл не найден в static/. Сначала положите его в static/images/.")
        return value
