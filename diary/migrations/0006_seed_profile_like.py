from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0005_add_photo_author"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = []
