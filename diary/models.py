from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="travel_profile")
    avatar = models.ImageField(upload_to="profile_avatars/", blank=True)
    cover_image = models.ImageField(upload_to="profile_covers/", blank=True)
    bio = models.CharField(max_length=500, blank=True, default="")


class Country(models.Model):
    owner = models.ForeignKey("auth.User", on_delete=models.CASCADE, null=True, blank=True, related_name="travel_countries")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "code"], name="unique_owner_country_code"),
        ]

    def __str__(self):
        return self.name


class Region(models.Model):
    owner = models.ForeignKey("auth.User", on_delete=models.CASCADE, null=True, blank=True, related_name="travel_regions")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="regions")
    name = models.CharField(max_length=120)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "country", "name"], name="unique_owner_country_region"),
        ]

    def __str__(self):
        return f"{self.name}, {self.country.code}"


class Travel(models.Model):
    owner = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="travel_journeys")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=[
        ("planned", "Planned"), ("ongoing", "Ongoing"), ("completed", "Completed"),
    ], default="planned")
    countries = models.ManyToManyField(Country, blank=True, related_name="travels")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.title


class ItineraryDay(models.Model):
    travel = models.ForeignKey(Travel, on_delete=models.CASCADE, related_name="days")
    day_number = models.PositiveIntegerField()
    date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["travel", "day_number"]
        unique_together = ("travel", "day_number")

    def __str__(self):
        return f"{self.travel.title} - Day {self.day_number}"


class Place(models.Model):
    owner = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="saved_travel_places")
    name = models.CharField(max_length=180)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name="places")
    address = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    description = models.TextField(blank=True)
    visited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Activity(models.Model):
    day = models.ForeignKey(ItineraryDay, on_delete=models.CASCADE, related_name="activities")
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True, related_name="activities")
    title = models.CharField(max_length=180)
    start_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.title


class Accommodation(models.Model):
    travel = models.ForeignKey(Travel, on_delete=models.CASCADE, related_name="accommodations")
    name = models.CharField(max_length=180)
    address = models.CharField(max_length=255, blank=True)
    check_in = models.DateField()
    check_out = models.DateField()
    booking_reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Expense(models.Model):
    travel = models.ForeignKey(Travel, on_delete=models.CASCADE, related_name="expenses")
    category = models.CharField(max_length=40, choices=[
        ("transport", "Transport"), ("food", "Food"), ("stay", "Accommodation"),
        ("activity", "Activity"), ("other", "Other"),
    ], default="other")
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    spent_on = models.DateField()

    def __str__(self):
        return f"{self.description} ({self.amount} {self.currency})"


class TravelPhoto(models.Model):
    travel = models.ForeignKey(Travel, on_delete=models.CASCADE, related_name="photos")
    author = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="travel_memories")
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True, related_name="photos")
    image = models.ImageField(upload_to="travel_photos/", blank=True)
    caption = models.CharField(max_length=255, blank=True)
    credit_text = models.CharField(max_length=255, blank=True)
    credit_url = models.URLField(max_length=500, blank=True)
    taken_on = models.DateField(null=True, blank=True)
    tags = models.ManyToManyField("Tag", blank=True, related_name="photos")
    likes = models.ManyToManyField("auth.User", blank=True, related_name="liked_travel_photos")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    @property
    def credit_display(self):
        return self.credit_text.split("; ", 1)[0]


class PhotoComment(models.Model):
    photo = models.ForeignKey(TravelPhoto, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    guest_name = models.CharField(max_length=80, blank=True)
    body = models.TextField(max_length=1000)
    likes = models.ManyToManyField("auth.User", blank=True, related_name="liked_photo_comments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class JournalEntry(models.Model):
    travel = models.ForeignKey(Travel, on_delete=models.CASCADE, related_name="journal_entries")
    photo = models.OneToOneField(
        TravelPhoto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_entry",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    entry_date = models.DateField()
    mood = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]


class Tag(models.Model):
    owner = models.ForeignKey("auth.User", on_delete=models.CASCADE, null=True, blank=True, related_name="travel_tags")
    name = models.CharField(max_length=60)
    travels = models.ManyToManyField(Travel, blank=True, related_name="tags")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_owner_tag_name"),
        ]

    def __str__(self):
        return self.name


class Friendship(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="friendships")
    friend = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="friend_of")
    status = models.CharField(max_length=10, choices=[("pending", "Pending"), ("accepted", "Accepted")], default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "friend"], name="unique_friendship"),
        ]
        ordering = ["-created_at"]


class Notification(models.Model):
    recipient = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="triggered_notifications")
    photo = models.ForeignKey(TravelPhoto, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    kind = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
