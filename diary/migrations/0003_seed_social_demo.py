from datetime import date, datetime

from django.conf import settings
from django.db import migrations
from django.utils import timezone


def aware_date(value):
    return timezone.make_aware(datetime.combine(value, datetime.min.time()))


def create_demo_social_data(apps, schema_editor):
    Travel = apps.get_model("diary", "Travel")
    Country = apps.get_model("diary", "Country")
    Region = apps.get_model("diary", "Region")
    Place = apps.get_model("diary", "Place")
    TravelPhoto = apps.get_model("diary", "TravelPhoto")
    PhotoComment = apps.get_model("diary", "PhotoComment")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    if TravelPhoto.objects.exists():
        return

    japan, _ = Country.objects.get_or_create(name="Japan", code="JPN")
    italy, _ = Country.objects.get_or_create(name="Italy", code="ITA")
    kyoto_region, _ = Region.objects.get_or_create(country=japan, name="Kyoto")
    dolomites_region, _ = Region.objects.get_or_create(country=italy, name="Dolomites")
    kyoto, _ = Place.objects.get_or_create(
        name="Kyoto",
        defaults={
            "region": kyoto_region,
            "latitude": 35.0116,
            "longitude": 135.7681,
            "description": "Quiet streets, temple gardens, and slow mornings.",
            "visited": True,
        },
    )
    dolomites, _ = Place.objects.get_or_create(
        name="The Dolomites",
        defaults={
            "region": dolomites_region,
            "latitude": 46.4102,
            "longitude": 11.8440,
            "description": "Mountain air and trails that go on forever.",
            "visited": False,
        },
    )
    japan_trip = Travel.objects.create(
        title="A week in Japan",
        description="A slow journey through Kyoto and the surrounding mountains.",
        start_date=date(2026, 10, 15),
        end_date=date(2026, 10, 21),
        status="ongoing",
    )
    japan_trip.countries.add(japan)
    italy_trip = Travel.objects.create(
        title="Dolomites, Italy",
        description="A quiet cabin, long walks, and no plans at all.",
        start_date=date(2026, 9, 3),
        end_date=date(2026, 9, 10),
        status="completed",
    )
    italy_trip.countries.add(italy)

    kyoto_photo = TravelPhoto.objects.create(
        travel=japan_trip,
        place=kyoto,
        caption="The quiet side of Kyoto",
        taken_on=date(2026, 10, 18),
        created_at=aware_date(date(2026, 10, 18)),
    )
    dolomites_photo = TravelPhoto.objects.create(
        travel=italy_trip,
        place=dolomites,
        caption="The kind of quiet you can hear",
        taken_on=date(2026, 9, 6),
        created_at=aware_date(date(2026, 9, 6)),
    )
    coast_photo = TravelPhoto.objects.create(
        travel=italy_trip,
        caption="Leave room for the unexpected",
        taken_on=date(2026, 9, 8),
        created_at=aware_date(date(2026, 9, 8)),
    )

    demo_user, _ = User.objects.get_or_create(
        username="maya.demo",
        defaults={"first_name": "Maya", "last_name": "Chen"},
    )
    kyoto_photo.likes.add(demo_user)
    dolomites_photo.likes.add(demo_user)
    PhotoComment.objects.create(
        photo=kyoto_photo,
        guest_name="Maya Chen",
        body="Adding this to my list!",
        created_at=aware_date(date(2026, 10, 18)),
    )
    PhotoComment.objects.create(
        photo=dolomites_photo,
        guest_name="Leo Brooks",
        body="This looks like the perfect kind of quiet.",
        created_at=aware_date(date(2026, 9, 6)),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0002_alter_travelphoto_options_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(create_demo_social_data, migrations.RunPython.noop),
    ]
