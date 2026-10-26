import re
import uuid

from django import forms
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q

from apps.equipment.models import Equipment, Zone

IMAGE_RE = re.compile(r"^images/[\w\-./]+\.(png|jpe?g|webp)$", re.IGNORECASE)
INPUT = "input"

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 25_000_000
PHOTO_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ("zone", "name", "type", "specs", "hourly_rate", "photo", "image", "is_active", "is_featured")
        widgets = {"specs": forms.Textarea(attrs={"rows": 4, "class": f"{INPUT} py-2"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("zone", "name", "type", "hourly_rate", "image"):
            self.fields[name].widget.attrs["class"] = INPUT
        zones = Zone.objects.filter(is_active=True)
        if self.instance.pk:
            zones = Zone.objects.filter(Q(is_active=True) | Q(pk=self.instance.zone_id))
        self.fields["zone"].queryset = zones
        # Имя файла до изменений: после проверки формы instance уже содержит новое значение.
        self._old_photo = self.instance.photo.name if self.instance.pk and self.instance.photo else ""

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if not isinstance(photo, UploadedFile):
            return photo  # файл не менялся или его удаляют
        if photo.size > MAX_PHOTO_BYTES:
            raise forms.ValidationError("Файл слишком большой: максимум 5 МБ.")
        image = photo.image  # ImageField уже проверил, что это настоящая картинка
        extension = PHOTO_EXTENSIONS.get(image.format)
        if extension is None:
            raise forms.ValidationError("Допустимы только изображения JPG, PNG и WebP.")
        if image.width * image.height > MAX_PHOTO_PIXELS:
            raise forms.ValidationError("Изображение слишком большое: максимум 25 мегапикселей.")
        photo.name = f"{uuid.uuid4().hex}{extension}"
        return photo

    def clean_image(self):
        value = (self.cleaned_data.get("image") or "").strip()
        if not value:
            return ""
        if ".." in value or not IMAGE_RE.match(value):
            raise forms.ValidationError("Укажите путь вида images/pc-pro-01.jpg (png, jpg или webp в папке static/images).")
        if not finders.find(value):
            raise forms.ValidationError("Файл не найден в static/. Сначала положите его в static/images/.")
        return value

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit and self._old_photo and self._old_photo != instance.photo.name:
            instance.photo.storage.delete(self._old_photo)  # заменили или удалили: старый файл не копим
        return instance
