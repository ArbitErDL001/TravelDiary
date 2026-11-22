import re

from django.conf import settings
from django.db import migrations
from django.db.models import Q


DEMO_USERNAMES = (
    "wanderer.alex",
    "roam.maya",
    "travel.leo",
    "explore.nina",
    "journey.sam",
    "pathways.jules",
)


def remove_seeded_demo_content(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    UserProfile = apps.get_model("diary", "UserProfile")
    Travel = apps.get_model("diary", "Travel")
    TravelPhoto = apps.get_model("diary", "TravelPhoto")
    PhotoComment = apps.get_model("diary", "PhotoComment")
    Notification = apps.get_model("diary", "Notification")
    Place = apps.get_model("diary", "Place")
    Country = apps.get_model("diary", "Country")
    Region = apps.get_model("diary", "Region")
    Tag = apps.get_model("diary", "Tag")

    demo_user_ids = set(
        User.objects.filter(username__in=DEMO_USERNAMES).values_list("pk", flat=True)
    )
    test_username = re.compile(r"(?:owner|friend|other)_[0-9a-f]{8}\Z")
    generated_travel = (
        Q(description__startswith="A sample travel story shared by ")
        | Q(description="Sample journey for testing private travel-data CRUD.")
    )
    generated_travel_ids = Travel.objects.filter(generated_travel).values("pk")
    for user in User.objects.all().iterator():
        if user.pk in demo_user_ids or not test_username.fullmatch(user.username):
            continue
        owned_travels = Travel.objects.filter(owner_id=user.pk)
        non_generated_photos = TravelPhoto.objects.filter(author_id=user.pk).exclude(
            travel_id__in=generated_travel_ids,
        )
        if (
            owned_travels.exists()
            and not owned_travels.exclude(generated_travel).exists()
            and not non_generated_photos.exists()
            and not PhotoComment.objects.filter(author_id=user.pk).exists()
        ):
            demo_user_ids.add(user.pk)

    for username, first_name, last_name in (
        ("alex", "Alex", "Morgan"),
        ("maya", "Maya", "Chen"),
        ("leo", "Leo", "Brooks"),
    ):
        user = User.objects.filter(
            username=username, first_name=first_name, last_name=last_name,
        ).first()
        owned_travels = Travel.objects.filter(owner_id=user.pk) if user else Travel.objects.none()
        non_generated_photos = (
            TravelPhoto.objects.filter(author_id=user.pk).exclude(
                travel_id__in=generated_travel_ids,
            )
            if user else TravelPhoto.objects.none()
        )
        if (
            user
            and not owned_travels.exclude(generated_travel).exists()
            and not non_generated_photos.exists()
            and not PhotoComment.objects.filter(author_id=user.pk).exists()
        ):
            demo_user_ids.add(user.pk)

    demo_user = User.objects.filter(
        username="maya.demo", first_name="Maya", last_name="Chen",
    ).first()
    if (
        demo_user
        and (not demo_user.password or demo_user.password.startswith("!"))
        and not Travel.objects.filter(owner_id=demo_user.pk).exclude(generated_travel).exists()
        and not TravelPhoto.objects.filter(author_id=demo_user.pk).exclude(
            travel_id__in=generated_travel_ids,
        ).exists()
        and not PhotoComment.objects.filter(author_id=demo_user.pk).exists()
    ):
        demo_user_ids.add(demo_user.pk)

    generated_travels = Travel.objects.filter(
        Q(description__startswith="A sample travel story shared by ")
        | Q(description="Sample journey for testing private travel-data CRUD.")
    )
    Travel.objects.filter(pk__in=generated_travels.values("pk")).delete()
    Travel.objects.filter(owner_id__in=demo_user_ids).delete()
    TravelPhoto.objects.filter(author_id__in=demo_user_ids).delete()
    PhotoComment.objects.filter(author_id__in=demo_user_ids).delete()
    Notification.objects.filter(
        Q(recipient_id__in=demo_user_ids) | Q(actor_id__in=demo_user_ids)
    ).delete()

    Place.objects.filter(owner_id__in=demo_user_ids).delete()
    Region.objects.filter(owner_id__in=demo_user_ids).delete()
    Country.objects.filter(owner_id__in=demo_user_ids).delete()
    Tag.objects.filter(owner_id__in=demo_user_ids).delete()
    Place.objects.filter(
        Q(description__startswith="A sample place near ")
        | Q(description="Sample place for testing travel-data CRUD.")
        | Q(description__in=(
            "Quiet streets, temple gardens, and slow mornings.",
            "Mountain air and trails that go on forever.",
        ))
    ).delete()
    Region.objects.filter(name__in=("Kyoto sample", "Lisbon sample")).delete()
    Country.objects.filter(name__in=("Japan sample", "Portugal sample")).delete()
    Tag.objects.filter(name__startswith="demo-").delete()

    for profile in UserProfile.objects.select_related("user").exclude(user_id__in=demo_user_ids):
        expected_avatar = f"profile_avatars/{profile.user.username}-avatar.jpg"
        if profile.avatar and profile.avatar.name == expected_avatar:
            profile.avatar = ""
            profile.save(update_fields=["avatar"])

    User.objects.filter(pk__in=demo_user_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0015_photocomment_likes_photocomment_parent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(remove_seeded_demo_content, migrations.RunPython.noop),
    ]
