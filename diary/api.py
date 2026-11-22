from django_filters.rest_framework import FilterSet, filters
from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.decorators import action, api_view
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from datetime import date
from django.db.models import Q
import requests
import unicodedata

from .models import (
    Accommodation, Activity, Country, Expense, ItineraryDay, JournalEntry,
    Notification, PhotoComment, Place, Region, Tag, Travel, TravelPhoto,
)
from .serializers import (
    AccommodationSerializer, ActivitySerializer, CountrySerializer,
    ExpenseSerializer, ItineraryDaySerializer, JournalEntrySerializer,
    PhotoCommentSerializer, PlaceSerializer, RegionSerializer, TagSerializer, TravelPhotoSerializer,
    TravelSerializer,
)


def _restrict_related_queryset(field, queryset):
    relation = field.child_relation if isinstance(field, serializers.ManyRelatedField) else field
    if hasattr(relation, "queryset") and relation.queryset is not None:
        relation.queryset = relation.queryset.filter(pk__in=queryset.values("pk"))


class TravelFilter(FilterSet):
    start_date = filters.DateFromToRangeFilter()
    status = filters.CharFilter(lookup_expr="iexact")

    class Meta:
        model = Travel
        fields = ["status", "countries", "start_date"]


class TravelViewSet(viewsets.ModelViewSet):
    queryset = Travel.objects.prefetch_related("countries", "tags").all()
    serializer_class = TravelSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = TravelFilter
    search_fields = ["title", "description"]
    ordering_fields = ["start_date", "created_at", "title"]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user).order_by("pk")

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        field_serializer = (
            serializer.child if isinstance(serializer, serializers.ListSerializer) else serializer
        )
        tag_field = field_serializer.fields.get("tags")
        if tag_field is not None:
            _restrict_related_queryset(
                tag_field,
                Tag.objects.filter(Q(owner=self.request.user) | Q(travels__owner=self.request.user)).distinct(),
            )
        country_field = field_serializer.fields.get("countries")
        if country_field is not None:
            _restrict_related_queryset(
                country_field,
                Country.objects.filter(Q(owner__isnull=True) | Q(owner=self.request.user)).distinct(),
            )
        return serializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class OwnedTravelChildViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    owner_lookup = "travel__owner"
    parent_field = "travel"
    parent_owner_lookup = "owner"

    def get_queryset(self):
        return self.queryset.filter(**{self.owner_lookup: self.request.user}).order_by("pk")

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        field_serializer = (
            serializer.child if isinstance(serializer, serializers.ListSerializer) else serializer
        )
        parent_field = field_serializer.fields.get(self.parent_field)
        if parent_field is not None and parent_field.queryset is not None:
            parent_field.queryset = parent_field.queryset.filter(
                **{self.parent_owner_lookup: self.request.user}
            )
        return serializer

    def _ensure_owned_parent(self, validated_data, instance=None):
        parent = validated_data.get(self.parent_field)
        if parent is None and instance is not None:
            parent = getattr(instance, self.parent_field)
        travel = parent if isinstance(parent, Travel) else parent.travel
        if travel.owner_id != self.request.user.id:
            raise PermissionDenied("You can only manage records in your own journeys.")

    def perform_create(self, serializer):
        self._ensure_owned_parent(serializer.validated_data)
        serializer.save()

    def perform_update(self, serializer):
        self._ensure_owned_parent(serializer.validated_data, serializer.instance)
        serializer.save()


class IsCountryOrRegionOwnerOrReadOnly(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return obj.owner_id == request.user.id


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [IsCountryOrRegionOwnerOrReadOnly]
    search_fields = ["name", "code"]

    def get_queryset(self):
        return self.queryset.filter(
            Q(owner__isnull=True) | Q(owner=self.request.user)
        ).distinct().order_by("pk")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class RegionViewSet(viewsets.ModelViewSet):
    queryset = Region.objects.select_related("country").all()
    serializer_class = RegionSerializer
    permission_classes = [IsCountryOrRegionOwnerOrReadOnly]
    filterset_fields = ["country"]

    def get_queryset(self):
        return self.queryset.filter(
            Q(owner__isnull=True) | Q(owner=self.request.user)
        ).distinct().order_by("pk")

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        field_serializer = (
            serializer.child if isinstance(serializer, serializers.ListSerializer) else serializer
        )
        country_field = field_serializer.fields.get("country")
        if country_field is not None:
            _restrict_related_queryset(
                country_field,
                Country.objects.filter(Q(owner__isnull=True) | Q(owner=self.request.user)).distinct(),
            )
        return serializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ItineraryDayViewSet(OwnedTravelChildViewSet):
    queryset = ItineraryDay.objects.all()
    serializer_class = ItineraryDaySerializer
    filterset_fields = ["travel", "date"]


class PlaceViewSet(viewsets.ModelViewSet):
    queryset = Place.objects.select_related("region").all()
    serializer_class = PlaceSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["region", "visited"]
    search_fields = ["name", "address", "description"]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user).order_by("pk")

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        field_serializer = (
            serializer.child if isinstance(serializer, serializers.ListSerializer) else serializer
        )
        region_field = field_serializer.fields.get("region")
        if region_field is not None:
            _restrict_related_queryset(
                region_field,
                Region.objects.filter(Q(owner__isnull=True) | Q(owner=self.request.user)).distinct(),
            )
        return serializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ActivityViewSet(OwnedTravelChildViewSet):
    queryset = Activity.objects.select_related("day", "place").all()
    serializer_class = ActivitySerializer
    owner_lookup = "day__travel__owner"
    parent_field = "day"
    parent_owner_lookup = "travel__owner"
    filterset_fields = ["day", "place"]

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        field_serializer = (
            serializer.child if isinstance(serializer, serializers.ListSerializer) else serializer
        )
        place_field = field_serializer.fields.get("place")
        if place_field is not None:
            _restrict_related_queryset(place_field, Place.objects.filter(owner=self.request.user))
        return serializer


class AccommodationViewSet(OwnedTravelChildViewSet):
    queryset = Accommodation.objects.all()
    serializer_class = AccommodationSerializer
    filterset_fields = ["travel"]


class ExpenseViewSet(OwnedTravelChildViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    filterset_fields = ["travel", "category", "currency"]


class IsPhotoOwnerOrReadOnly(IsAuthenticatedOrReadOnly):
    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return request.user.is_authenticated and obj.author_id == request.user.id


class IsCommentOwnerOrReadOnly(IsAuthenticatedOrReadOnly):
    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return request.user.is_authenticated and obj.author_id == request.user.id


class IsTagOwnerOrReadOnly(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return obj.owner_id == request.user.id


class TravelPhotoViewSet(viewsets.ModelViewSet):
    queryset = TravelPhoto.objects.prefetch_related("tags", "likes", "comments").all()
    serializer_class = TravelPhotoSerializer
    permission_classes = [IsPhotoOwnerOrReadOnly]
    filterset_fields = ["travel", "place"]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        field_serializer = (
            serializer.child if isinstance(serializer, serializers.ListSerializer) else serializer
        )
        user = self.request.user if self.request.user.is_authenticated else None
        travel_field = field_serializer.fields.get("travel")
        if travel_field is not None:
            _restrict_related_queryset(travel_field, Travel.objects.filter(owner=user))
        place_field = field_serializer.fields.get("place")
        if place_field is not None:
            _restrict_related_queryset(place_field, Place.objects.filter(owner=user))
        tag_field = field_serializer.fields.get("tags")
        if tag_field is not None:
            _restrict_related_queryset(
                tag_field,
                Tag.objects.filter(Q(owner=user) | Q(travels__owner=user)).distinct(),
            )
        return serializer

    def _ensure_owned_travel(self, validated_data, instance=None):
        travel = validated_data.get("travel")
        if travel is None and instance is not None:
            travel = instance.travel
        if travel is None or travel.owner_id != self.request.user.id:
            raise PermissionDenied("You can only add photos to your own journeys.")

    def perform_create(self, serializer):
        self._ensure_owned_travel(serializer.validated_data)
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        self._ensure_owned_travel(serializer.validated_data, serializer.instance)
        serializer.save()

    @action(detail=True, methods=["post"], permission_classes=[])
    def like(self, request, pk=None):
        photo = self.get_object()
        if request.user.is_authenticated:
            if photo.likes.filter(pk=request.user.pk).exists():
                photo.likes.remove(request.user)
                liked = False
            else:
                photo.likes.add(request.user)
                liked = True
                if photo.author and photo.author != request.user:
                    Notification.objects.create(recipient=photo.author, actor=request.user, photo=photo, kind="like")
        else:
            return Response({"detail": "Log in to like photos."}, status=401)
        return Response({"liked": liked, "like_count": photo.likes.count()})


class PhotoCommentViewSet(viewsets.ModelViewSet):
    queryset = PhotoComment.objects.select_related("author").all()
    serializer_class = PhotoCommentSerializer
    permission_classes = [IsCommentOwnerOrReadOnly]
    filterset_fields = ["photo"]

    def perform_create(self, serializer):
        user = self.request.user
        comment = serializer.save(author=user, guest_name="")
        recipients = {comment.photo.author_id}
        if comment.parent_id:
            recipients.add(comment.parent.author_id)
        for recipient_id in recipients - {None, user.id}:
            Notification.objects.create(
                recipient_id=recipient_id,
                actor=user,
                photo=comment.photo,
                kind="comment",
            )


class JournalEntryViewSet(OwnedTravelChildViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    filterset_fields = ["travel", "entry_date"]
    search_fields = ["title", "body", "mood"]


class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsTagOwnerOrReadOnly]

    def get_queryset(self):
        return self.queryset.filter(
            Q(owner=self.request.user) | Q(travels__owner=self.request.user)
        ).distinct().order_by("pk")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


@api_view(["GET"])
def geocode(request):
    query = request.query_params.get("q", "").strip()
    if not query:
        return Response({"detail": "q is required."}, status=400)
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "jsonv2", "limit": 5},
        headers={"User-Agent": "TravelDiary/1.0"},
        timeout=10,
    )
    response.raise_for_status()
    return Response(response.json())


def _normalize_location_text(value):
    return unicodedata.normalize(
        "NFKD", str(value or ""),
    ).encode("ascii", "ignore").decode("ascii").casefold()


@api_view(["GET"])
def photon_search(request):
    query = request.query_params.get("q", "").strip()
    if len(query) < 2:
        return Response({"features": []})
    normalized_query = unicodedata.normalize("NFKD", query).encode("ascii", "ignore").decode("ascii").casefold()
    query_terms = normalized_query.split()
    country_search = request.query_params.get("kind") == "country"
    try:
        response = requests.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": 6, "lang": "en"},
            headers={"User-Agent": "RoamTravelDiary/1.0"},
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException:
        return Response({"detail": "Place recommendations are temporarily unavailable."}, status=502)
    features = []
    for feature in response.json().get("features", []):
        properties = feature.get("properties", {})
        country_code = (properties.get("countrycode") or "").upper()
        if not properties.get("name") or not country_code:
            continue
        city = properties.get("city") or properties.get("town") or properties.get("village")
        state = properties.get("state")
        country = properties.get("country")
        if country_search:
            country_text = _normalize_location_text(country)
            locality_text = _normalize_location_text(f"{city or ''} {state or ''}")
            matches_query = normalized_query in country_text or (
                bool(query_terms) and all(term in locality_text for term in query_terms)
            )
        else:
            searchable_text = _normalize_location_text(
                f"{properties['name']} {city or ''} {state or ''} {country or ''}",
            )
            matches_query = bool(query_terms) and all(term in searchable_text for term in query_terms)
        if not matches_query:
            continue
        features.append({
            "name": properties["name"],
            "city": city,
            "state": state,
            "country": country,
            "country_code": country_code,
            "coordinates": feature.get("geometry", {}).get("coordinates", []),
        })
    return Response({"features": features})


@api_view(["GET"])
def nearby_recommendations(request):
    try:
        latitude = float(request.query_params["latitude"])
        longitude = float(request.query_params["longitude"])
    except (KeyError, TypeError, ValueError):
        return Response({"detail": "latitude and longitude are required numbers."}, status=400)
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return Response({"detail": "latitude and longitude are out of range."}, status=400)

    try:
        reverse = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": latitude, "lon": longitude, "format": "jsonv2", "zoom": 10},
            headers={"User-Agent": "RoamTravelDiary/1.0"},
            timeout=8,
        )
        reverse.raise_for_status()
        address = reverse.json().get("address", {})
        area = address.get("city") or address.get("town") or address.get("municipality") or address.get("county")
        if not area:
            return Response({"area": "your area", "places": []})
        categories = ["park", "museum", "viewpoint", "market"]
        offset = date.today().toordinal() % len(categories)
        places = []
        for category in categories[offset:] + categories[:offset]:
            response = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": f"{category} {area}", "limit": 4, "lang": "en"},
                headers={"User-Agent": "RoamTravelDiary/1.0"},
                timeout=8,
            )
            response.raise_for_status()
            for feature in response.json().get("features", []):
                properties = feature.get("properties", {})
                name = properties.get("name")
                if name and not any(place["name"] == name for place in places):
                    places.append({
                        "name": name,
                        "category": category.title(),
                        "city": properties.get("city") or area,
                        "latitude": feature.get("geometry", {}).get("coordinates", [None, None])[1],
                        "longitude": feature.get("geometry", {}).get("coordinates", [None, None])[0],
                    })
                if len(places) >= 6:
                    break
            if len(places) >= 6:
                break
        return Response({"area": area, "places": places})
    except requests.RequestException:
        return Response({"detail": "Nearby recommendations are temporarily unavailable."}, status=502)


@api_view(["GET"])
def weather(request):
    try:
        latitude = float(request.query_params["latitude"])
        longitude = float(request.query_params["longitude"])
    except (KeyError, TypeError, ValueError):
        return Response({"detail": "latitude and longitude are required numbers."}, status=400)
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": latitude, "longitude": longitude, "current": "temperature_2m,weather_code"},
        timeout=10,
    )
    response.raise_for_status()
    return Response(response.json())
