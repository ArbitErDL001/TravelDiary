from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
import requests

from diary.models import Friendship, Place, Travel, TravelPhoto, UserProfile


DEMO_ACCOUNTS = [
    ("wanderer.alex", "Alex", "Santos"),
    ("roam.maya", "Maya", "Reyes"),
    ("travel.leo", "Leo", "Garcia"),
    ("explore.nina", "Nina", "Cruz"),
    ("journey.sam", "Sam", "Lim"),
    ("pathways.jules", "Jules", "Tan"),
]

DESTINATIONS = [
    ("Cebu City weekend", "Cebu City"),
    ("Island mornings", "Siargao"),
    ("Quiet Kyoto streets", "Kyoto"),
    ("Coastal escape", "Palawan"),
    ("Mountain air", "Baguio"),
    ("A day in Lisbon", "Lisbon"),
]

POST_IMAGES = [
    "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1516483638261-f4dbaf036963?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1530789253388-582c481c54b0?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1521292270410-a8c4d716d518?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1200&q=82",
]


class Command(BaseCommand):
    help = "Create repeatable development accounts, friendships, and feed posts."

    @transaction.atomic
    def handle(self, *args, **options):
        image_cache = {}

        def save_post_image(photo, image_url, filename):
            if photo.image:
                return
            if image_url not in image_cache:
                response = requests.get(image_url, timeout=20)
                response.raise_for_status()
                image_cache[image_url] = response.content
            photo.image.save(filename, ContentFile(image_cache[image_url]), save=True)

        users = list(User.objects.order_by("id"))
        demo_users = []
        for username, first_name, last_name in DEMO_ACCOUNTS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": f"{username}@example.test",
                },
            )
            if created:
                user.set_password("RoamDemo123!")
                user.save(update_fields=["password"])
            demo_users.append(user)

        all_users = list(dict.fromkeys(users + demo_users))
        if len(all_users) < 2:
            self.stdout.write(self.style.WARNING("Create at least one account before seeding the feed."))
            return

        place_by_name = {
            place.name: place
            for place in Place.objects.filter(name__in={name for _, name in DESTINATIONS})
        }
        for index, (_, city) in enumerate(DESTINATIONS):
            place_by_name.setdefault(
                city,
                Place.objects.create(
                    name=city,
                    latitude=10.3157 + index * 0.1,
                    longitude=123.8854 + index * 0.1,
                    description=f"A sample place near {city}.",
                ),
            )

        for index, user in enumerate(all_users):
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.avatar:
                response = requests.get(
                    f"https://i.pravatar.cc/160?img={(index % 70) + 1}",
                    timeout=15,
                )
                response.raise_for_status()
                profile.avatar.save(
                    f"{user.username}-avatar.jpg",
                    ContentFile(response.content),
                    save=True,
                )

            friend = all_users[(index + 1) % len(all_users)]
            Friendship.objects.update_or_create(
                user=user, friend=friend, defaults={"status": "accepted"},
            )
            Friendship.objects.update_or_create(
                user=friend, friend=user, defaults={"status": "accepted"},
            )

            title, city = DESTINATIONS[index % len(DESTINATIONS)]
            travel, _ = Travel.objects.get_or_create(
                owner=user,
                title=f"{title} · {user.username}",
                defaults={
                    "description": f"A sample travel story shared by {user.get_full_name() or user.username}.",
                    "start_date": date.today() - timedelta(days=index + 10),
                    "end_date": date.today() - timedelta(days=index + 7),
                    "status": "completed",
                },
            )
            post_specs = [
                (f"{city} in a few memorable moments", POST_IMAGES[(index * 3) % len(POST_IMAGES)]),
                (f"Golden light over {city}", POST_IMAGES[(index * 3 + 1) % len(POST_IMAGES)]),
                (f"A quiet corner of {city}", POST_IMAGES[(index * 3 + 2) % len(POST_IMAGES)]),
            ]
            for post_index, (caption, image_url) in enumerate(post_specs):
                photo, created = TravelPhoto.objects.get_or_create(
                    travel=travel,
                    author=user,
                    caption=caption,
                    defaults={"place": place_by_name[city]},
                )
                save_post_image(
                    photo,
                    image_url,
                    f"{user.username}-post-{post_index + 1}.jpg",
                )
                if created:
                    photo.likes.add(friend)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(demo_users)} demo accounts and feed data for {len(all_users)} accounts. "
            "Demo password: RoamDemo123!"
        ))
