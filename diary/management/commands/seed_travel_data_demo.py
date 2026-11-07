from datetime import date, time, timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from diary.models import (
    Accommodation, Activity, Country, Expense, ItineraryDay, JournalEntry,
    Place, Region, Tag, Travel, TravelPhoto,
)


DEMO_IMAGE_FILES = ("sample-kyoto.jpg", "sample-coast.jpg")


def _demo_image(index):
    image_path = Path(settings.BASE_DIR) / "static" / "diary" / "demo-images" / DEMO_IMAGE_FILES[index]
    return image_path.read_bytes()


class Command(BaseCommand):
    help = "Add repeatable travel-data samples and image posts for existing users."

    @transaction.atomic
    def handle(self, *args, **options):
        users = list(User.objects.order_by("pk"))
        today = date.today()
        image_posts = 0

        for user_index, user in enumerate(users):
            countries = []
            regions = []
            for index, (name, code) in enumerate((("Japan", "JPN"), ("Portugal", "PRT"))):
                country, _ = Country.objects.get_or_create(
                    owner=user,
                    code=code,
                    defaults={"name": f"{name} sample"},
                )
                countries.append(country)
                region, _ = Region.objects.get_or_create(
                    owner=user,
                    country=country,
                    name=("Kyoto sample", "Lisbon sample")[index],
                )
                regions.append(region)

            places = []
            for index, name in enumerate(("Sample place 1 · Kyoto", "Sample place 2 · Lisbon")):
                place, _ = Place.objects.get_or_create(
                    owner=user,
                    name=name,
                    defaults={
                        "region": regions[index],
                        "address": f"Sample address {index + 1}",
                        "latitude": 35.0116 if index == 0 else 38.7223,
                        "longitude": 135.7681 if index == 0 else -9.1393,
                        "description": "Sample place for testing travel-data CRUD.",
                        "visited": index == 0,
                    },
                )
                places.append(place)

            travels = []
            days = []
            for index, title in enumerate(("Sample journey 1 · Kyoto", "Sample journey 2 · Lisbon")):
                start_date = today - timedelta(days=35 + index * 20 + user_index)
                travel, _ = Travel.objects.get_or_create(
                    owner=user,
                    title=title,
                    defaults={
                        "description": "Sample journey for testing private travel-data CRUD.",
                        "start_date": start_date,
                        "end_date": start_date + timedelta(days=3),
                        "status": "completed",
                    },
                )
                travel.countries.add(countries[index])
                travels.append(travel)
                day, _ = ItineraryDay.objects.get_or_create(
                    travel=travel,
                    day_number=1,
                    defaults={
                        "date": travel.start_date,
                        "notes": "Sample itinerary day for testing.",
                    },
                )
                days.append(day)

            tags = []
            for index, tag_name in enumerate(("demo-journey", "demo-photo")):
                tag, _ = Tag.objects.get_or_create(
                    owner=user,
                    name=f"{tag_name}-{index + 1}",
                )
                tag.travels.add(travels[index])
                tags.append(tag)

            for index, travel in enumerate(travels):
                Activity.objects.get_or_create(
                    day=days[index],
                    title=f"Sample activity {index + 1}",
                    defaults={
                        "place": places[index],
                        "start_time": time(9, 0),
                        "duration_minutes": 90,
                        "notes": "Sample activity for development testing.",
                    },
                )
                Accommodation.objects.get_or_create(
                    travel=travel,
                    name=f"Sample stay {index + 1}",
                    defaults={
                        "address": f"Sample address {index + 1}",
                        "check_in": travel.start_date,
                        "check_out": travel.start_date + timedelta(days=2),
                        "booking_reference": f"DEMO-{user.pk}-{index + 1}",
                        "notes": "Development sample accommodation.",
                    },
                )
                Expense.objects.get_or_create(
                    travel=travel,
                    description=f"Sample expense {index + 1}",
                    defaults={
                        "category": ("food", "transport")[index],
                        "amount": "24.50" if index == 0 else "18.00",
                        "currency": "USD",
                        "spent_on": travel.start_date,
                    },
                )
                JournalEntry.objects.get_or_create(
                    travel=travel,
                    title=f"Sample journal {index + 1}",
                    defaults={
                        "body": "A sample entry for testing journal CRUD.",
                        "entry_date": travel.start_date,
                        "mood": ("curious", "peaceful")[index],
                    },
                )
                photo, _ = TravelPhoto.objects.get_or_create(
                    travel=travel,
                    author=user,
                    caption=f"Sample photo {index + 1}",
                    defaults={
                        "place": places[index],
                        "taken_on": travel.start_date,
                    },
                )
                filename = f"demo-user-{user.pk}-photo-{index + 1}-v2.jpg"
                expected_image_name = f"travel_photos/{filename}"
                if (
                    not photo.image
                    or photo.image.name != expected_image_name
                    or not photo.image.storage.exists(photo.image.name)
                ):
                    photo.image.save(
                        filename,
                        ContentFile(_demo_image(index)),
                        save=True,
                    )
                    image_posts += 1
                photo.tags.add(tags[index])

        self.stdout.write(self.style.SUCCESS(
            f"Seeded two records per travel-data category for {len(users)} existing users "
            f"and ensured generated images for {image_posts} sample posts."
        ))
