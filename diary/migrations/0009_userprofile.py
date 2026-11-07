from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0008_remove_demo_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("avatar", models.ImageField(blank=True, upload_to="profile_avatars/")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="travel_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
