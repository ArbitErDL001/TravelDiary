from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("diary", "0019_travelphoto_credit_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="bio",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
