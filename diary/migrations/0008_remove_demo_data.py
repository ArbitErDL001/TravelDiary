from django.conf import settings
from django.db import migrations


def remove_demo_data(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Travel = apps.get_model("diary", "Travel")
    TravelPhoto = apps.get_model("diary", "TravelPhoto")
    Place = apps.get_model("diary", "Place")
    Country = apps.get_model("diary", "Country")
    Region = apps.get_model("diary", "Region")

    demo_travels = Travel.objects.filter(
        title__in=("A week in Japan", "Dolomites, Italy"),
    )
    TravelPhoto.objects.filter(
        caption__in=(
            "The quiet side of Kyoto",
            "The kind of quiet you can hear",
            "Leave room for the unexpected",
        ),
    ).delete()
    demo_travels.delete()
    Place.objects.filter(name__in=("Kyoto", "The Dolomites")).delete()
    Region.objects.filter(name__in=("Kyoto", "Dolomites")).delete()
    Country.objects.filter(code__in=("JPN", "ITA")).delete()
    User.objects.filter(username__in=("alex", "maya", "leo", "maya.demo")).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0007_notification"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(remove_demo_data, migrations.RunPython.noop),
    ]
