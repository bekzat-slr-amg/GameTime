import io
import os
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User
from apps.equipment.models import Equipment, Zone


def image_bytes(fmt="PNG", size=(32, 32)):
    image = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def upload(name="photo.png", fmt="PNG", content_type="image/png", size=(32, 32)):
    return SimpleUploadedFile(name, image_bytes(fmt, size), content_type=content_type)


def media_files():
    return [p for p in Path(settings.MEDIA_ROOT).rglob("*") if p.is_file()]


class MediaTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._tmp)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._tmp, ignore_errors=True)
        super().tearDownClass()

    def tearDown(self):
        for path in media_files():
            path.unlink()


class UploadTests(MediaTestCase):
    def setUp(self):
        self.zone = Zone.objects.create(name="Alpha")
        self.item = Equipment.objects.create(zone=self.zone, name="Photo Box", type="pc", hourly_rate=Decimal("200"))
        self.admin = User.objects.create_user(email="boss@example.com", password="x", role=User.Role.CLUB_ADMIN)
        self.client_user = User.objects.create_user(email="client@example.com", password="x")
        self.client.force_login(self.admin)
        self.url = reverse("club:equipment_edit", args=[self.item.pk])

    def data(self, **extra):
        data = {"zone": self.zone.pk, "name": "Photo Box", "type": "pc", "specs": "", "hourly_rate": "200",
                "image": "", "is_active": "on"}
        data.update(extra)
        return data

    def post(self, **extra):
        return self.client.post(self.url, self.data(**extra))

    def refreshed(self):
        self.item.refresh_from_db()
        return self.item

    def test_png_is_saved_with_random_name_and_shown_in_catalog(self):
        response = self.post(photo=upload(name="../../evil.php.png"))
        self.assertEqual(response.status_code, 302)
        item = self.refreshed()
        self.assertTrue(item.photo.name.startswith("equipment/"))
        self.assertTrue(item.photo.name.endswith(".png"))
        self.assertNotIn("evil", item.photo.name)
        self.assertTrue((Path(settings.MEDIA_ROOT) / item.photo.name).is_file())
        catalog = self.client.get(reverse("equipment:list"))
        self.assertContains(catalog, item.photo.url)
        self.assertContains(self.client.get(reverse("equipment:detail", args=[item.pk])), item.photo.url)

    def test_extension_follows_real_format_not_filename(self):
        for fmt, ext in (("JPEG", ".jpg"), ("WEBP", ".webp"), ("PNG", ".png")):
            with self.subTest(fmt=fmt):
                self.post(photo=upload(name="x.png", fmt=fmt))
                self.assertTrue(self.refreshed().photo.name.endswith(ext))

    def test_fake_image_is_rejected(self):
        fake = SimpleUploadedFile("fake.png", b"<?php echo 1; ?>", content_type="image/png")
        self.assertEqual(self.post(photo=fake).status_code, 200)
        self.assertFalse(self.refreshed().photo)
        self.assertEqual(media_files(), [])

    def test_disallowed_formats_are_rejected(self):
        for fmt, ctype in (("GIF", "image/gif"), ("BMP", "image/bmp")):
            with self.subTest(fmt=fmt):
                response = self.post(photo=upload(name=f"x.{fmt.lower()}", fmt=fmt, content_type=ctype))
                self.assertContains(response, "только изображения JPG, PNG и WebP")
        self.assertFalse(self.refreshed().photo)
        self.assertEqual(media_files(), [])

    def test_too_big_file_is_rejected(self):
        with mock.patch("apps.club.forms.MAX_PHOTO_BYTES", 1000):
            response = self.post(photo=upload(size=(64, 64)))
        self.assertContains(response, "слишком большой")
        self.assertFalse(self.refreshed().photo)

    def test_too_many_pixels_are_rejected(self):
        with mock.patch("apps.club.forms.MAX_PHOTO_PIXELS", 100):
            response = self.post(photo=upload(size=(64, 64)))
        self.assertContains(response, "мегапикселей")
        self.assertFalse(self.refreshed().photo)

    def test_invalid_form_saves_no_file(self):
        response = self.post(photo=upload(), hourly_rate="0")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.refreshed().photo)
        self.assertEqual(media_files(), [])

    def test_replacing_photo_deletes_the_old_file(self):
        self.post(photo=upload())
        old = self.refreshed().photo.name
        self.post(photo=upload(fmt="JPEG", content_type="image/jpeg"))
        new = self.refreshed().photo.name
        self.assertNotEqual(old, new)
        self.assertFalse((Path(settings.MEDIA_ROOT) / old).exists())
        self.assertTrue((Path(settings.MEDIA_ROOT) / new).is_file())
        self.assertEqual(len(media_files()), 1)

    def test_clear_checkbox_removes_photo_and_file(self):
        self.post(photo=upload())
        name = self.refreshed().photo.name
        self.post(**{"photo-clear": "on"})
        self.assertFalse(self.refreshed().photo)
        self.assertFalse((Path(settings.MEDIA_ROOT) / name).exists())

    def test_saving_without_new_file_keeps_the_photo(self):
        self.post(photo=upload())
        name = self.refreshed().photo.name
        self.post(hourly_rate="300")
        item = self.refreshed()
        self.assertEqual(item.photo.name, name)
        self.assertEqual(item.hourly_rate, Decimal("300.00"))
        self.assertTrue((Path(settings.MEDIA_ROOT) / name).is_file())

    def test_edit_page_shows_current_photo_and_remove_option(self):
        self.post(photo=upload())
        response = self.client.get(self.url)
        self.assertContains(response, self.refreshed().photo.url)
        self.assertContains(response, "photo-clear")
        self.assertContains(response, "multipart/form-data")

    def test_create_with_photo(self):
        data = self.data(name="Brand New Box", photo=upload())
        response = self.client.post(reverse("club:equipment_create"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Equipment.objects.get(name="Brand New Box").photo.name.endswith(".png"))

    def test_client_cannot_upload(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.post(photo=upload()).status_code, 403)
        self.assertEqual(self.client.post(reverse("club:equipment_create"), self.data(name="Hack", photo=upload())).status_code, 403)
        self.assertEqual(media_files(), [])
        self.assertFalse(Equipment.objects.filter(name="Hack").exists())


class ImageUrlTests(MediaTestCase):
    def test_priority_photo_then_static_then_empty(self):
        self.assertEqual(Equipment(photo="equipment/a.png", image="images/e-1.png").image_url, "/media/equipment/a.png")
        self.assertEqual(Equipment(image="images/e-1.png").image_url, "/static/images/e-1.png")
        self.assertEqual(Equipment().image_url, "")
