from django.conf import settings
from django.db import migrations


def add_profile_like(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    TravelPhoto = apps.get_model("diary", "TravelPhoto")
    alex = User.objects.filter(username="alex").first()
    photo = TravelPhoto.objects.order_by("id").first()
    if alex and photo:
        photo.likes.add(alex)


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0005_add_photo_author"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(add_profile_like, migrations.RunPython.noop),
    ]
