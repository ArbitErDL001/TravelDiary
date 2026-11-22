from django.db import migrations, models


COMMONS_MARKER = "; Wikimedia Commons: "


def move_commons_credits(apps, schema_editor):
    TravelPhoto = apps.get_model("diary", "TravelPhoto")
    database = schema_editor.connection.alias
    photos = TravelPhoto.objects.using(database).filter(caption__contains=COMMONS_MARKER)

    for photo in photos.iterator():
        title, separator, credit_text = photo.caption.rpartition(" - ")
        if not separator:
            continue

        marker_index = credit_text.rfind(COMMONS_MARKER)
        if marker_index < 0:
            continue

        credit_url = credit_text[marker_index + len(COMMONS_MARKER):].strip()
        if not credit_url.startswith("https://commons.wikimedia.org/"):
            continue

        photo.caption = title.strip()
        photo.credit_text = credit_text.strip()
        photo.credit_url = credit_url
        photo.save(update_fields=["caption", "credit_text", "credit_url"])


def restore_commons_credits(apps, schema_editor):
    TravelPhoto = apps.get_model("diary", "TravelPhoto")
    database = schema_editor.connection.alias
    photos = TravelPhoto.objects.using(database).exclude(credit_text="")

    for photo in photos.iterator():
        photo.caption = f"{photo.caption} - {photo.credit_text}"
        photo.save(update_fields=["caption"])


class Migration(migrations.Migration):

    dependencies = [
        ("diary", "0018_journalentry_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="travelphoto",
            name="credit_text",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="travelphoto",
            name="credit_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.RunPython(move_commons_credits, restore_commons_credits),
    ]
