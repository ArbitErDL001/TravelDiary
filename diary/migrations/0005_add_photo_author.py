from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_demo_author(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    TravelPhoto = apps.get_model("diary", "TravelPhoto")
    alex = User.objects.filter(username="alex").first()
    if alex:
        TravelPhoto.objects.filter(author__isnull=True).update(author=alex)


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0004_seed_test_accounts"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="travelphoto",
            name="author",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="travel_memories",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_demo_author, migrations.RunPython.noop),
    ]
