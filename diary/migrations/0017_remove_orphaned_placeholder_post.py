from django.db import migrations


def remove_orphaned_placeholder_post(apps, schema_editor):
    Travel = apps.get_model("diary", "Travel")
    TravelPhoto = apps.get_model("diary", "TravelPhoto")

    placeholders = Travel.objects.filter(
        owner__isnull=True,
        title="Shared journey",
        description="",
    )
    for travel in placeholders.iterator():
        photos = TravelPhoto.objects.filter(travel_id=travel.pk)
        if photos.exists() and not photos.exclude(
            author__isnull=True,
            caption="Friend post",
            image="",
        ).exists():
            travel.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0016_remove_seeded_demo_content"),
    ]

    operations = [
        migrations.RunPython(remove_orphaned_placeholder_post, migrations.RunPython.noop),
    ]
