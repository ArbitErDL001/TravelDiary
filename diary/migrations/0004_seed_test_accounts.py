from django.conf import settings
from django.db import migrations
import django.db.models
import django.db.models.deletion


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
    ]
