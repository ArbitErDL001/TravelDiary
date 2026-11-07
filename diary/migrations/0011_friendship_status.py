from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("diary", "0010_travel_owner")]

    operations = [
        migrations.AddField(
            model_name="friendship",
            name="status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("accepted", "Accepted")],
                default="pending",
                max_length=10,
            ),
        ),
        migrations.RunSQL(
            "UPDATE diary_friendship SET status = 'accepted'",
            migrations.RunSQL.noop,
        ),
    ]
