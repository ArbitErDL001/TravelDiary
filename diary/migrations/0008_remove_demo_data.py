from django.db import migrations


def remove_demo_data(apps, schema_editor):
    Travel = apps.get_model("diary", "Travel")
    TravelPhoto = apps.get_model("diary", "TravelPhoto")

    demo_travels = Travel.objects.filter(
        title__in=("A week in Japan", "Dolomites, Italy"),
    )
    TravelPhoto.objects.filter(
        travel_id__in=demo_travels.values("pk"),
        caption__in=(
            "The quiet side of Kyoto",
            "The kind of quiet you can hear",
            "Leave room for the unexpected",
        ),
    ).delete()
    demo_travels.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0007_notification"),
    ]

    operations = [
        migrations.RunPython(remove_demo_data, migrations.RunPython.noop),
    ]
