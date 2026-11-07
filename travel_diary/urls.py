from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from diary.api import (
    AccommodationViewSet, ActivityViewSet, CountryViewSet, ExpenseViewSet,
    ItineraryDayViewSet, JournalEntryViewSet, PlaceViewSet, RegionViewSet,
    PhotoCommentViewSet, TagViewSet, TravelPhotoViewSet, TravelViewSet,
)

router = DefaultRouter()
for prefix, viewset in (
    ("countries", CountryViewSet), ("regions", RegionViewSet),
    ("travels", TravelViewSet), ("itinerary-days", ItineraryDayViewSet),
    ("places", PlaceViewSet), ("activities", ActivityViewSet),
    ("accommodations", AccommodationViewSet), ("expenses", ExpenseViewSet),
    ("photos", TravelPhotoViewSet), ("journal-entries", JournalEntryViewSet),
    ("tags", TagViewSet),
    ("photo-comments", PhotoCommentViewSet),
):
    router.register(prefix, viewset)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),
    path("", include("diary.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
