from django.contrib import admin
from .models import (
    Accommodation, Activity, Country, Expense, ItineraryDay, JournalEntry,
    PhotoComment, Place, Region, Tag, Travel, TravelPhoto,
)

admin.site.register([
    Accommodation, Activity, Country, Expense, ItineraryDay, JournalEntry,
    Place, Region, Tag, Travel, TravelPhoto,
])
admin.site.register(PhotoComment)
