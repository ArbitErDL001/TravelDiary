from django.conf import settings
from django.db import migrations
import django.db.models
import django.db.models.deletion
from django.contrib.auth.hashers import make_password


def create_test_accounts(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Friendship = apps.get_model("diary", "Friendship")

    accounts = [
        ("alex", "Alex", "Morgan"),
        ("maya", "Maya", "Chen"),
        ("leo", "Leo", "Brooks"),
    ]
    users = {}
    for username, first_name, last_name in accounts:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": first_name, "last_name": last_name},
        )
        if created:
            user.password = make_password("roam1234")
            user.save()
        users[username] = user

    Friendship.objects.get_or_create(user=users["alex"], friend=users["maya"])
    Friendship.objects.get_or_create(user=users["maya"], friend=users["alex"])


class Migration(migrations.Migration):
    dependencies = [
        ("diary", "0003_seed_social_demo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Friendship",
            fields=[
                ("id", django.db.models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", django.db.models.DateTimeField(auto_now_add=True)),
                ("friend", django.db.models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="friend_of", to=settings.AUTH_USER_MODEL)),
                ("user", django.db.models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="friendships", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="friendship",
            constraint=django.db.models.UniqueConstraint(fields=("user", "friend"), name="unique_friendship"),
        ),
        migrations.RunPython(create_test_accounts, migrations.RunPython.noop),
    ]
