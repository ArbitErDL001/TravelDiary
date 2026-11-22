import os
import random
import secrets
from urllib.parse import urlencode

import requests
from django import forms
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from .models import (
    Accommodation, Activity, Country, Expense, Friendship, ItineraryDay,
    JournalEntry, Notification, PhotoComment, Place, Region, Tag, Travel,
    TravelPhoto, UserProfile,
)

JOURNEY_FALLBACK_IMAGES = (
    "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1516483638261-f4dbaf036963?auto=format&fit=crop&w=1200&q=82",
    "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1200&q=82",
)


class TravelForm(forms.ModelForm):
    class Meta:
        model = Travel
        fields = ["title", "description", "start_date", "end_date", "status", "countries"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "countries": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["countries"].queryset = Country.objects.filter(
            Q(owner__isnull=True) | Q(owner=user)
        ).distinct()


class OwnedTravelForm(forms.ModelForm):
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        if "travel" in self.fields:
            self.fields["travel"].queryset = Travel.objects.filter(owner=user)


class ItineraryDayForm(OwnedTravelForm):
    class Meta:
        model = ItineraryDay
        fields = ["travel", "day_number", "date", "notes"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


class ActivityForm(OwnedTravelForm):
    class Meta:
        model = Activity
        fields = ["day", "place", "title", "start_time", "duration_minutes", "notes"]
        widgets = {"start_time": forms.TimeInput(attrs={"type": "time"})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["day"].queryset = ItineraryDay.objects.filter(travel__owner=user)
        self.fields["place"].queryset = Place.objects.filter(owner=user)


class AccommodationForm(OwnedTravelForm):
    class Meta:
        model = Accommodation
        fields = ["travel", "name", "address", "check_in", "check_out", "booking_reference", "notes"]
        widgets = {
            "check_in": forms.DateInput(attrs={"type": "date"}),
            "check_out": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["address"].widget.attrs.update({
            "data-location-autocomplete": "address",
        })


class ExpenseForm(OwnedTravelForm):
    class Meta:
        model = Expense
        fields = ["travel", "category", "description", "amount", "currency", "spent_on"]
        widgets = {"spent_on": forms.DateInput(attrs={"type": "date"})}


class JournalEntryForm(OwnedTravelForm):
    class Meta:
        model = JournalEntry
        fields = ["travel", "title", "body", "entry_date", "mood"]
        widgets = {"entry_date": forms.DateInput(attrs={"type": "date"})}


class PlaceForm(forms.ModelForm):
    class Meta:
        model = Place
        fields = ["name", "region", "address", "latitude", "longitude", "description", "visited"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.update({
            "data-location-autocomplete": "place",
            "data-location-address-target": "#id_address",
            "data-location-latitude-target": "#id_latitude",
            "data-location-longitude-target": "#id_longitude",
        })
        self.fields["address"].widget.attrs.update({
            "data-location-autocomplete": "address",
            "data-location-latitude-target": "#id_latitude",
            "data-location-longitude-target": "#id_longitude",
        })
        self.fields["region"].queryset = Region.objects.filter(
            Q(owner__isnull=True) | Q(owner=user)
        ).distinct()


class InlineJourneyForm(forms.Form):
    title = forms.CharField(max_length=200, label="Journey name")
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(choices=Travel._meta.get_field("status").choices)
    country_name = forms.CharField(max_length=100, required=False, label="Country")
    country_code = forms.CharField(max_length=3, min_length=2, required=False, label="Country code")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["country_name"].widget.attrs.update({
            "data-location-autocomplete": "country",
            "data-location-code-target": "#id_new_journey-country_code",
        })

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be on or after the start date.")
        country_name = cleaned_data.get("country_name", "").strip()
        country_code = cleaned_data.get("country_code", "").strip()
        if bool(country_name) != bool(country_code):
            self.add_error("country_name", "Choose a country recommendation to fill its code.")
        if country_code:
            cleaned_data["country_code"] = country_code.upper()
        return cleaned_data


class PrivateTripDetailsForm(forms.Form):
    details = forms.CharField(
        max_length=5000,
        required=False,
        label="Private trip details",
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Add notes, plans, or other trip details for your travel data.",
        }),
    )


class InlineAccommodationForm(forms.Form):
    name = forms.CharField(max_length=180, required=False)
    address = forms.CharField(max_length=255, required=False)
    check_in = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    check_out = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    booking_reference = forms.CharField(max_length=100, required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def clean(self):
        cleaned_data = super().clean()
        if any(value not in (None, "") for value in cleaned_data.values()):
            for field in ("name", "check_in", "check_out"):
                if not cleaned_data.get(field):
                    self.add_error(field, "This field is required when adding an accommodation.")
            check_in = cleaned_data.get("check_in")
            check_out = cleaned_data.get("check_out")
            if check_in and check_out and check_out < check_in:
                self.add_error("check_out", "Check-out must be on or after check-in.")
        return cleaned_data

    def has_details(self):
        return any(value not in (None, "") for value in self.cleaned_data.values())


class InlineExpenseForm(forms.Form):
    category = forms.ChoiceField(
        choices=[("", "Choose a category")] + list(Expense._meta.get_field("category").choices),
        required=False,
    )
    description = forms.CharField(max_length=200, required=False)
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    currency = forms.CharField(max_length=3, required=False, initial="USD")
    spent_on = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned_data = super().clean()
        if any(value not in (None, "") for value in cleaned_data.values()):
            for field in ("description", "amount", "spent_on"):
                if cleaned_data.get(field) in (None, ""):
                    self.add_error(field, "This field is required when adding an expense.")
        return cleaned_data

    def has_details(self):
        return any(value not in (None, "") for value in self.cleaned_data.values())


class InlineJournalEntryForm(forms.Form):
    title = forms.CharField(max_length=200, required=False)
    body = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    entry_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    mood = forms.CharField(max_length=40, required=False)

    def clean(self):
        cleaned_data = super().clean()
        if any(value not in (None, "") for value in cleaned_data.values()):
            for field in ("title", "body", "entry_date"):
                if not cleaned_data.get(field):
                    self.add_error(field, "This field is required when adding a journal entry.")
        return cleaned_data

    def has_details(self):
        return any(value not in (None, "") for value in self.cleaned_data.values())


class JourneyTagsForm(forms.Form):
    tags = forms.CharField(
        max_length=600,
        required=False,
        help_text="Separate tags with commas. Tags appear publicly with this post.",
    )

    def clean_tags(self):
        tags = []
        seen = set()
        for value in self.cleaned_data["tags"].split(","):
            name = value.strip()
            normalized = name.casefold()
            if not name or normalized in seen:
                continue
            if len(name) > 60:
                raise ValidationError("Each tag must be 60 characters or fewer.")
            tags.append(name)
            seen.add(normalized)
        return tags

    def has_details(self):
        return bool(self.cleaned_data.get("tags"))


class InlinePlaceForm(forms.Form):
    name = forms.CharField(
        max_length=180,
        label="Search for a place",
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    address = forms.CharField(max_length=255, required=False, label="Address")
    latitude = forms.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90,
        widget=forms.HiddenInput(),
    )
    longitude = forms.DecimalField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.update({
            "data-location-autocomplete": "place",
            "data-location-address-target": "#id_new_place-address",
            "data-location-latitude-target": "#id_new_place-latitude",
            "data-location-longitude-target": "#id_new_place-longitude",
        })


class TravelPhotoForm(OwnedTravelForm):
    class Meta:
        model = TravelPhoto
        fields = ["travel", "place", "image", "caption", "taken_on", "tags"]
        widgets = {"taken_on": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["place"].queryset = Place.objects.filter(owner=user)
        self.fields["tags"].queryset = Tag.objects.filter(
            Q(travels__owner=user) | Q(owner=user)
        ).distinct()


class CountryAssignmentForm(forms.Form):
    travel = forms.ModelChoiceField(queryset=Travel.objects.none())
    countries = forms.ModelMultipleChoiceField(
        queryset=Country.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    new_country_name = forms.CharField(max_length=100, required=False, label="Or add a country")
    new_country_code = forms.CharField(
        min_length=2, max_length=3, required=False,
        label="Country code (ISO, 2-3 letters)",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["travel"].queryset = Travel.objects.filter(owner=user)
        self.fields["countries"].queryset = Country.objects.filter(
            Q(owner__isnull=True) | Q(owner=user)
        ).distinct()
        self.fields["new_country_name"].widget.attrs.update({
            "data-location-autocomplete": "country",
            "data-location-code-target": "#id_new_country_code",
        })
        self.fields["new_country_code"].widget.attrs.update({"inputmode": "text", "autocomplete": "off"})


class RegionAssignmentForm(forms.Form):
    place = forms.ModelChoiceField(queryset=Place.objects.none())
    region = forms.ModelChoiceField(queryset=Region.objects.none(), required=False)
    country = forms.ModelChoiceField(queryset=Country.objects.none(), required=False)
    new_region_name = forms.CharField(max_length=120, required=False, label="Or create a region")

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["place"].queryset = Place.objects.filter(owner=user)
        self.fields["region"].queryset = Region.objects.filter(
            Q(owner__isnull=True) | Q(owner=user)
        ).distinct()
        self.fields["country"].queryset = Country.objects.filter(
            Q(owner__isnull=True) | Q(owner=user)
        ).distinct()
        self.fields["new_region_name"].widget.attrs.update({
            "data-location-autocomplete": "region",
            "data-location-country-target": "#id_country",
        })

    def save(self):
        place = self.cleaned_data["place"]
        region = self.cleaned_data["region"]
        region_name = self.cleaned_data["new_region_name"].strip()
        if region_name:
            country = self.cleaned_data["country"]
            if country is None:
                self.add_error("country", "Choose a country for the new region.")
                return None
            region, _ = Region.objects.get_or_create(
                country=country, name=region_name, owner=self.user,
            )
        place.region = region
        place.save(update_fields=["region"])
        return place


class TravelTagsForm(forms.Form):
    travel = forms.ModelChoiceField(queryset=Travel.objects.none())
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    new_tag = forms.CharField(max_length=60, required=False, label="Or create a tag")

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["travel"].queryset = Travel.objects.filter(owner=user)
        self.fields["tags"].queryset = Tag.objects.filter(
            Q(owner=user) | Q(travels__owner=user)
        ).distinct()

    def save(self, user):
        travel = self.cleaned_data["travel"]
        tags = self.cleaned_data["tags"]
        tag_name = self.cleaned_data["new_tag"].strip()
        if tag_name:
            tag, _ = Tag.objects.get_or_create(name=tag_name, owner=user)
            tags = list(tags) + [tag]
        travel.tags.set(tags)
        return travel


class PrivateCountryForm(forms.ModelForm):
    class Meta:
        model = Country
        fields = ["name", "code"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.update({
            "data-location-autocomplete": "country",
            "data-location-code-target": "#id_code",
        })
        self.fields["code"].widget.attrs.update({"inputmode": "text", "autocomplete": "off"})

    def clean_code(self):
        code = self.cleaned_data["code"].upper()
        if Country.objects.filter(owner=self.instance.owner, code=code).exclude(pk=self.instance.pk).exists():
            raise ValidationError("You already have a country with this code.")
        return code


class PrivateRegionForm(forms.ModelForm):
    class Meta:
        model = Region
        fields = ["country", "name"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.update({
            "data-location-autocomplete": "region",
            "data-location-country-target": "#id_country",
        })
        self.fields["country"].queryset = Country.objects.filter(
            Q(owner__isnull=True) | Q(owner=user)
        ).distinct()

    def clean(self):
        cleaned_data = super().clean()
        country = cleaned_data.get("country")
        name = cleaned_data.get("name")
        if country and name and Region.objects.filter(
            owner=self.instance.owner, country=country, name=name,
        ).exclude(pk=self.instance.pk).exists():
            self.add_error("name", "You already have a region with this name in that country.")
        return cleaned_data


class PrivateTagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"]
        if Tag.objects.filter(owner=self.instance.owner, name=name).exclude(pk=self.instance.pk).exists():
            raise ValidationError("You already have a tag with this name.")
        return name


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "diary/landing.html")


def dashboard(request):
    travels = list(
        Travel.objects.filter(owner=request.user).prefetch_related("countries", "photos")
        if request.user.is_authenticated else Travel.objects.none()
    )
    photo_query = TravelPhoto.objects.select_related(
        "travel", "place", "author", "author__travel_profile", "journal_entry",
    ).prefetch_related(
        "tags", "likes", "comments__author", "comments__likes",
        "comments__replies__author", "comments__replies__likes",
    )
    if request.user.is_authenticated:
        friend_ids = Friendship.objects.filter(
            user=request.user, status="accepted",
        ).values_list("friend_id", flat=True)
        photo_query = photo_query.filter(Q(author=request.user) | Q(author_id__in=friend_ids))
    photos = list(photo_query.all())
    random.shuffle(photos)
    current_travel = next((travel for travel in travels if travel.status == "ongoing"), travels[0] if travels else None)
    current_photo = next((photo for photo in photos if current_travel and photo.travel_id == current_travel.id), None)
    today = timezone.localdate()
    current_progress = 0
    if current_travel:
        total_days = max((current_travel.end_date - current_travel.start_date).days + 1, 1)
        elapsed_days = min(max((today - current_travel.start_date).days + 1, 0), total_days)
        current_progress = round(elapsed_days / total_days * 100)
    display_name = (
        request.user.get_full_name() or request.user.username
        if request.user.is_authenticated
        else "Explorer"
    )
    profile = UserProfile.objects.filter(user=request.user).first() if request.user.is_authenticated else None
    first_name = display_name.split()[0]
    notifications = _notifications(request)
    return render(request, "diary/dashboard.html", {
        "active_page": "feed",
        "travels": travels,
        "places": Place.objects.filter(owner=request.user) if request.user.is_authenticated else Place.objects.none(),
        "photos": photos,
        "photo_travels": Travel.objects.filter(owner=request.user) if request.user.is_authenticated else Travel.objects.none(),
        "photo_places": Place.objects.filter(owner=request.user) if request.user.is_authenticated else Place.objects.none(),
        "photo_tags": Tag.objects.filter(Q(owner=request.user) | Q(travels__owner=request.user)).distinct() if request.user.is_authenticated else Tag.objects.none(),
        "current_travel": current_travel,
        "current_photo": current_photo,
        "current_journey_fallback": random.choice(JOURNEY_FALLBACK_IMAGES),
        "current_place": current_photo.place if current_photo else None,
        "current_progress": current_progress,
        "travel_count": len(travels),
        "country_count": len({country.id for travel in travels for country in travel.countries.all()}),
        "photo_count": len(photos),
        "place_count": Place.objects.count(),
        "user_name": display_name,
        "user_first_name": first_name,
        "user_initials": "".join(part[0] for part in display_name.split()[:2]).upper(),
        "user_avatar": profile.avatar.url if profile and profile.avatar else "",
        "notifications": notifications,
        "notification_count": sum(notification["unread"] for notification in notifications),
    })


def upload_photo(request):
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        travel = get_object_or_404(Travel, pk=request.POST.get("travel"), owner=request.user)
        place = get_object_or_404(Place, pk=request.POST.get("place"), owner=request.user) if request.POST.get("place") else None
        tag_ids = request.POST.getlist("tags")
        allowed_tags = Tag.objects.filter(
            Q(owner=request.user) | Q(travels__owner=request.user)
        ).distinct()
        tags = list(allowed_tags.filter(pk__in=tag_ids))
        if len(tags) != len(set(tag_ids)):
            return HttpResponseBadRequest("One or more selected tags are not available to this account.")
        photo = TravelPhoto.objects.create(
            travel=travel,
            author=request.user,
            place=place,
            image=request.FILES["image"],
            caption=request.POST.get("caption", ""),
            taken_on=request.POST.get("taken_on") or None,
        )
        photo.tags.set(tags)
    return redirect("dashboard")


def add_memory(request):
    context = _social_context(request, "add_memory")
    new_journey_form = InlineJourneyForm(prefix="new_journey")
    private_trip_details_form = PrivateTripDetailsForm()
    accommodation_form = InlineAccommodationForm(prefix="accommodation")
    expense_form = InlineExpenseForm(prefix="expense")
    journal_entry_form = InlineJournalEntryForm(prefix="journal")
    journey_tags_form = JourneyTagsForm(prefix="journey_tags")
    new_place_form = InlinePlaceForm(prefix="new_place")
    context.update({
        "photo_travels": Travel.objects.filter(owner=request.user) if request.user.is_authenticated else Travel.objects.none(),
        "photo_places": Place.objects.filter(owner=request.user) if request.user.is_authenticated else Place.objects.none(),
        "photo_tags": Tag.objects.filter(Q(owner=request.user) | Q(travels__owner=request.user)).distinct() if request.user.is_authenticated else Tag.objects.none(),
        "new_journey_form": new_journey_form,
        "private_trip_details_form": private_trip_details_form,
        "accommodation_form": accommodation_form,
        "expense_form": expense_form,
        "journal_entry_form": journal_entry_form,
        "journey_tags_form": journey_tags_form,
        "new_place_form": new_place_form,
    })
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        errors = []
        private_trip_details_form = PrivateTripDetailsForm(request.POST)
        accommodation_form = InlineAccommodationForm(request.POST, prefix="accommodation")
        expense_form = InlineExpenseForm(request.POST, prefix="expense")
        journal_entry_form = InlineJournalEntryForm(request.POST, prefix="journal")
        journey_tags_form = JourneyTagsForm(request.POST, prefix="journey_tags")
        if not private_trip_details_form.is_valid():
            errors.append("Check the private trip details.")
        if not accommodation_form.is_valid():
            errors.append("Check the accommodation details.")
        if not expense_form.is_valid():
            errors.append("Check the expense details.")
        if not journal_entry_form.is_valid():
            errors.append("Check the journal entry details.")
        if not journey_tags_form.is_valid():
            errors.append("Check the journey tags.")
        travel_value = request.POST.get("travel", "")
        place_value = request.POST.get("place", "")
        if travel_value == "__new__":
            new_journey_form = InlineJourneyForm(request.POST, prefix="new_journey")
            if not new_journey_form.is_valid():
                errors.append("Check the new journey details.")
        elif travel_value:
            travel = get_object_or_404(Travel, pk=travel_value, owner=request.user)
        else:
            errors.append("Choose a journey or create a new one.")

        if place_value == "__new__":
            new_place_form = InlinePlaceForm(request.POST, prefix="new_place")
            if not new_place_form.is_valid():
                errors.append("Choose a place recommendation so its map coordinates are included.")
        elif place_value:
            place = get_object_or_404(Place, pk=place_value, owner=request.user)
        else:
            place = None

        image = request.FILES.get("image")
        if image is None:
            errors.append("Choose a photo to share.")
        tag_ids = request.POST.getlist("tags")
        allowed_tags = Tag.objects.filter(
            Q(owner=request.user) | Q(travels__owner=request.user)
        ).distinct()
        tags = list(allowed_tags.filter(pk__in=tag_ids))
        if len(tags) != len(set(tag_ids)):
            errors.append("One or more selected tags are not available to this account.")
        if errors:
            context.update({
                "new_journey_form": new_journey_form,
                "private_trip_details_form": private_trip_details_form,
                "accommodation_form": accommodation_form,
                "expense_form": expense_form,
                "journal_entry_form": journal_entry_form,
                "journey_tags_form": journey_tags_form,
                "new_place_form": new_place_form,
                "memory_errors": errors,
            })
            return render(request, "diary/add_memory.html", context, status=400)

        with transaction.atomic():
            if travel_value == "__new__":
                journey_data = new_journey_form.cleaned_data
                travel = Travel.objects.create(
                    owner=request.user,
                    title=journey_data["title"],
                    description=private_trip_details_form.cleaned_data["details"].strip(),
                    start_date=journey_data["start_date"],
                    end_date=journey_data["end_date"],
                    status=journey_data["status"],
                )
                country_name = journey_data.get("country_name", "").strip()
                country_code = journey_data.get("country_code", "").strip().upper()
                if country_name and country_code:
                    country = Country.objects.filter(
                        owner__isnull=True, name__iexact=country_name,
                    ).first() or Country.objects.filter(
                        owner=request.user, name__iexact=country_name,
                    ).first()
                    if country is None:
                        country = Country.objects.filter(
                            Q(owner__isnull=True) | Q(owner=request.user),
                            code=country_code,
                        ).first()
                    if country is None:
                        country = Country.objects.create(
                            owner=request.user, name=country_name, code=country_code,
                        )
                    travel.countries.add(country)
            else:
                details = private_trip_details_form.cleaned_data["details"].strip()
                if details:
                    travel.description = details
                    travel.save(update_fields=["description"])
            if place_value == "__new__":
                place_data = new_place_form.cleaned_data
                place = Place.objects.create(
                    owner=request.user,
                    name=place_data["name"],
                    address=place_data["address"],
                    latitude=place_data["latitude"],
                    longitude=place_data["longitude"],
                )
            photo = TravelPhoto.objects.create(
                travel=travel,
                author=request.user,
                place=place,
                image=image,
                caption=request.POST.get("caption", ""),
                taken_on=request.POST.get("taken_on") or None,
            )
            photo.tags.set(tags)
            if accommodation_form.has_details():
                Accommodation.objects.create(
                    travel=travel,
                    **accommodation_form.cleaned_data,
                )
            if expense_form.has_details():
                expense_data = expense_form.cleaned_data
                Expense.objects.create(
                    travel=travel,
                    category=expense_data["category"] or "other",
                    description=expense_data["description"],
                    amount=expense_data["amount"],
                    currency=(expense_data["currency"] or "USD").upper(),
                    spent_on=expense_data["spent_on"],
                )
            if journal_entry_form.has_details():
                JournalEntry.objects.create(
                    travel=travel,
                    photo=photo,
                    **journal_entry_form.cleaned_data,
                )
            for name in journey_tags_form.cleaned_data["tags"]:
                tag = Tag.objects.filter(
                    owner=request.user, name__iexact=name,
                ).first()
                if tag is None:
                    tag = Tag.objects.create(owner=request.user, name=name)
                tag.travels.add(travel)
                photo.tags.add(tag)
        return redirect("dashboard")
    return render(request, "diary/add_memory.html", context)


def add_journey(request):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    context = _social_context(request, "add_journey")
    context["countries"] = Country.objects.filter(
        Q(owner__isnull=True) | Q(owner=request.user)
    ).distinct()
    context["google_maps_api_key"] = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if request.method == "POST":
        country_id = request.POST.get("country")
        country_name = request.POST.get("country_name", "").strip()
        with transaction.atomic():
            country = None
            if country_id:
                available_countries = Country.objects.filter(
                    Q(owner__isnull=True) | Q(owner=request.user)
                )
                if country_id.startswith("code:"):
                    code = country_id.removeprefix("code:").upper()
                    country = available_countries.filter(code=code).first()
                    if country is None and country_name:
                        country = available_countries.filter(name__iexact=country_name).first()
                    if country is None:
                        country_data = {
                            "JPN": "Japan", "FRA": "France", "ITA": "Italy", "PRT": "Portugal",
                            "ESP": "Spain", "GBR": "United Kingdom", "GRC": "Greece", "ISL": "Iceland",
                            "IRL": "Ireland", "NLD": "Netherlands", "DEU": "Germany", "AUT": "Austria",
                            "CZE": "Czechia", "HRV": "Croatia", "CHE": "Switzerland", "NOR": "Norway",
                            "SWE": "Sweden", "TUR": "Turkey", "MAR": "Morocco", "EGY": "Egypt",
                            "ZAF": "South Africa", "KEN": "Kenya", "TZA": "Tanzania",
                            "ARE": "United Arab Emirates", "JOR": "Jordan", "IND": "India", "NPL": "Nepal",
                            "LKA": "Sri Lanka", "THA": "Thailand", "VNM": "Vietnam", "KHM": "Cambodia",
                            "MYS": "Malaysia", "IDN": "Indonesia", "PHL": "Philippines", "KOR": "South Korea",
                            "CHN": "China", "SGP": "Singapore", "AUS": "Australia", "NZL": "New Zealand",
                            "USA": "United States", "CAN": "Canada", "MEX": "Mexico", "CRI": "Costa Rica",
                            "BRA": "Brazil", "PER": "Peru", "ARG": "Argentina", "CHL": "Chile",
                        }
                        country_name = country_name or country_data.get(code, code)
                        country, created = Country.objects.get_or_create(
                            owner=request.user,
                            code=code,
                            defaults={"name": country_name},
                        )
                        if not created and country.name.casefold() != country_name.casefold():
                            return HttpResponseBadRequest("That country code is already used by another country.")
                else:
                    country = get_object_or_404(available_countries, pk=country_id)

            travel = Travel.objects.create(
                owner=request.user,
                title=request.POST["title"],
                description=request.POST.get("description", ""),
                start_date=request.POST["start_date"],
                end_date=request.POST["end_date"],
                status=request.POST.get("status", "planned"),
            )
            if country:
                travel.countries.add(country)
        return redirect("journeys")
    return render(request, "diary/add_journey.html", context)


def manage_travel(request, travel_id=None):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    travel = (
        get_object_or_404(Travel, pk=travel_id, owner=request.user)
        if travel_id is not None else None
    )
    form = TravelForm(request.POST or None, instance=travel, user=request.user)
    if request.method == "POST" and form.is_valid():
        travel = form.save(commit=False)
        travel.owner = request.user
        travel.save()
        form.save_m2m()
        return redirect("profile")
    return render(request, "diary/travel_form.html", {
        "form": form,
        "travel": travel,
        "active_page": "profile",
    })


def delete_travel(request, travel_id):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    travel = get_object_or_404(Travel, pk=travel_id, owner=request.user)
    travel.delete()
    return redirect("profile")


PROFILE_DATA_TABS = [
    ("journeys", "Journeys"),
    ("countries", "Countries"),
    ("regions", "Regions"),
    ("itinerary-days", "Itinerary days"),
    ("places", "Saved places"),
    ("activities", "Activities"),
    ("accommodations", "Accommodations"),
    ("expenses", "Expenses"),
    ("photos", "Photos"),
    ("journal-entries", "Journal entries"),
    ("tags", "Tags"),
]

PROFILE_DATA_MODELS = {
    "journeys": (
        Travel, TravelForm, lambda user: Travel.objects.filter(owner=user),
    ),
    "itinerary-days": (
        ItineraryDay, ItineraryDayForm,
        lambda user: ItineraryDay.objects.filter(travel__owner=user),
    ),
    "places": (Place, PlaceForm, lambda user: Place.objects.filter(owner=user)),
    "activities": (
        Activity, ActivityForm,
        lambda user: Activity.objects.filter(day__travel__owner=user),
    ),
    "accommodations": (
        Accommodation, AccommodationForm,
        lambda user: Accommodation.objects.filter(travel__owner=user),
    ),
    "expenses": (
        Expense, ExpenseForm,
        lambda user: Expense.objects.filter(travel__owner=user),
    ),
    "photos": (
        TravelPhoto, TravelPhotoForm,
        lambda user: TravelPhoto.objects.filter(author=user, travel__owner=user),
    ),
    "journal-entries": (
        JournalEntry, JournalEntryForm,
        lambda user: JournalEntry.objects.filter(travel__owner=user),
    ),
}


def _profile_data_redirect(category):
    return redirect("profile_data", category=category)


def profile_data_view(request, category, record_id=None, action=None, item=False):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    tab_labels = dict(PROFILE_DATA_TABS)
    if category not in tab_labels:
        return HttpResponseBadRequest("Unknown travel data category.")
    editing_item = item
    item_form = None
    if item:
        item_models = {
            "countries": (Country, PrivateCountryForm),
            "regions": (Region, PrivateRegionForm),
            "tags": (Tag, PrivateTagForm),
        }
        model, form_class = item_models.get(category, (None, None))
        if model is None:
            return HttpResponseBadRequest("This category does not support direct record editing.")
        instance = get_object_or_404(model, pk=record_id, owner=request.user)
        if action == "delete":
            if request.method != "POST":
                return HttpResponseNotAllowed(["POST"])
            instance.delete()
            return _profile_data_redirect(category)
        item_form = form_class(request.POST or None, instance=instance, user=request.user) if category == "regions" else form_class(request.POST or None, instance=instance)
        if request.method == "POST" and item_form.is_valid():
            item_form.save()
            return _profile_data_redirect(category)
        record_id = None
    if category == "countries":
        travel = get_object_or_404(Travel, pk=record_id, owner=request.user) if record_id else None
        if action == "delete":
            if request.method != "POST":
                return HttpResponseNotAllowed(["POST"])
            travel = get_object_or_404(Travel, pk=record_id, owner=request.user)
            country = get_object_or_404(
                Country.objects.filter(Q(owner__isnull=True) | Q(owner=request.user)),
                pk=request.POST.get("country_id"),
            )
            travel.countries.remove(country)
            if country.owner_id == request.user.id and not country.travels.exists() and not country.regions.exists():
                country.delete()
            return _profile_data_redirect(category)
        initial = {"travel": travel, "countries": travel.countries.all() if travel else []}
        form = CountryAssignmentForm(
            request.POST or None, user=request.user,
            initial=initial if request.method != "POST" else None,
        )
        if request.method == "POST" and form.is_valid():
            travel = form.cleaned_data["travel"]
            previous_countries = list(travel.countries.all())
            countries = list(form.cleaned_data["countries"])
            name = form.cleaned_data["new_country_name"].strip()
            code = form.cleaned_data["new_country_code"].strip().upper()
            if name or code:
                if not name or not code:
                    if not name:
                        form.add_error("new_country_name", "Enter a country name.")
                    if not code:
                        form.add_error("new_country_code", "Enter a two- or three-letter country code.")
                else:
                    country = Country.objects.filter(
                        owner__isnull=True, name__iexact=name,
                    ).first() or Country.objects.filter(
                        owner=request.user, name__iexact=name,
                    ).first()
                    if country is None:
                        country = Country.objects.filter(
                            Q(owner__isnull=True) | Q(owner=request.user),
                            code=code,
                        ).first()
                    if country and country.name.casefold() != name.casefold():
                        form.add_error("new_country_code", "That code is already used by another country.")
                    else:
                        if country is None:
                            country, created = Country.objects.get_or_create(
                                code=code, owner=request.user, defaults={"name": name},
                            )
                            if not created and country.name.casefold() != name.casefold():
                                form.add_error("new_country_code", "That code is already used by another country.")
                        if not form.errors:
                            countries.append(country)
            if not form.errors:
                travel.countries.set(countries)
                for previous_country in previous_countries:
                    if (
                        previous_country.owner_id == request.user.id
                        and not previous_country.travels.exists()
                        and not previous_country.regions.exists()
                    ):
                        previous_country.delete()
                return _profile_data_redirect(category)
        entries = [
            {"parent": trip, "item": country}
            for trip in Travel.objects.filter(owner=request.user).prefetch_related("countries")
            for country in trip.countries.all()
        ]
        linked_country_ids = {entry["item"].pk for entry in entries}
        entries.extend(
            {"parent": None, "item": country}
            for country in Country.objects.filter(owner=request.user).exclude(pk__in=linked_country_ids)
        )
    elif category == "regions":
        place = get_object_or_404(Place, pk=record_id, owner=request.user) if record_id else None
        if action == "delete":
            if request.method != "POST":
                return HttpResponseNotAllowed(["POST"])
            place = get_object_or_404(Place, pk=record_id, owner=request.user)
            region = place.region
            place.region = None
            place.save(update_fields=["region"])
            if region and region.owner_id == request.user.id and not region.places.exists():
                country = region.country
                region.delete()
                if (
                    country.owner_id == request.user.id
                    and not country.travels.exists()
                    and not country.regions.exists()
                ):
                    country.delete()
            return _profile_data_redirect(category)
        initial = {"place": place, "region": place.region if place else None}
        form = RegionAssignmentForm(
            request.POST or None, user=request.user,
            initial=initial if request.method != "POST" else None,
        )
        if request.method == "POST" and form.is_valid():
            old_region = place.region if place else None
            updated_place = form.save()
            if updated_place is not None:
                if old_region and old_region.owner_id == request.user.id and not old_region.places.exists():
                    country = old_region.country
                    old_region.delete()
                    if (
                        country.owner_id == request.user.id
                        and not country.travels.exists()
                        and not country.regions.exists()
                    ):
                        country.delete()
                return _profile_data_redirect(category)
        entries = [
            {"parent": place, "item": place.region}
            for place in Place.objects.filter(owner=request.user).select_related("region")
            if place.region_id
        ]
        linked_region_ids = {entry["item"].pk for entry in entries}
        entries.extend(
            {"parent": None, "item": region}
            for region in Region.objects.filter(owner=request.user).exclude(pk__in=linked_region_ids)
        )
    elif category == "tags":
        travel = get_object_or_404(Travel, pk=record_id, owner=request.user) if record_id else None
        if action == "delete":
            if request.method != "POST":
                return HttpResponseNotAllowed(["POST"])
            travel = get_object_or_404(Travel, pk=record_id, owner=request.user)
            tag = get_object_or_404(
                Tag.objects.filter(Q(owner=request.user) | Q(travels__owner=request.user)).distinct(),
                pk=request.POST.get("tag_id"),
            )
            travel.tags.remove(tag)
            if tag.owner_id == request.user.id and not tag.travels.exists() and not tag.photos.exists():
                tag.delete()
            return _profile_data_redirect(category)
        initial = {"travel": travel, "tags": travel.tags.all() if travel else []}
        form = TravelTagsForm(
            request.POST or None, user=request.user,
            initial=initial if request.method != "POST" else None,
        )
        if request.method == "POST" and form.is_valid():
            form.save(request.user)
            Tag.objects.filter(owner=request.user, travels__isnull=True, photos__isnull=True).delete()
            return _profile_data_redirect(category)
        entries = [
            {"parent": trip, "item": tag}
            for trip in Travel.objects.filter(owner=request.user).prefetch_related("tags")
            for tag in trip.tags.all()
        ]
        linked_tag_ids = {entry["item"].pk for entry in entries}
        entries.extend(
            {"parent": None, "item": tag}
            for tag in Tag.objects.filter(owner=request.user).exclude(pk__in=linked_tag_ids)
        )
    else:
        model, form_class, queryset_for_user = PROFILE_DATA_MODELS[category]
        queryset = queryset_for_user(request.user)
        instance = get_object_or_404(queryset, pk=record_id) if record_id else None
        if action == "delete":
            if request.method != "POST":
                return HttpResponseNotAllowed(["POST"])
            instance.delete()
            return _profile_data_redirect(category)
        form = form_class(
            request.POST or None,
            request.FILES or None,
            instance=instance,
            user=request.user,
        )
        if request.method == "POST" and form.is_valid():
            item = form.save(commit=False)
            if isinstance(item, (Place, Travel)):
                item.owner = request.user
            if isinstance(item, TravelPhoto):
                item.author = request.user
            item.save()
            form.save_m2m()
            return _profile_data_redirect(category)
        entries = [{"item": item} for item in queryset]

    tabs = [
        {"slug": slug, "label": label, "active": slug == category}
        for slug, label in PROFILE_DATA_TABS
    ]
    context = _social_context(request, "profile")
    context.update({
        "active_page": "profile",
        "category": category,
        "category_label": tab_labels[category],
        "tabs": tabs,
        "form": item_form or form,
        "entries": entries,
        "editing": editing_item or (record_id is not None and action != "delete"),
        "editing_item": editing_item,
        "record_id": record_id,
    })
    return render(request, "diary/profile_data.html", context)


def profile_view(request, user_id=None):
    context = _social_context(request, "profile")
    if user_id is not None:
        profile_user = User.objects.filter(pk=user_id).first()
    else:
        profile_user = request.user if request.user.is_authenticated else None
    is_owner = bool(profile_user and request.user.is_authenticated and profile_user.pk == request.user.pk)
    is_friend = bool(
        profile_user
        and request.user.is_authenticated
        and Friendship.objects.filter(
            user=request.user, friend=profile_user, status="accepted",
        ).exists()
    )
    if is_friend:
        is_friend = Friendship.objects.filter(
            user=profile_user, friend=request.user, status="accepted",
        ).exists()
    profile = UserProfile.objects.filter(user=profile_user).first() if profile_user else None
    context["profile_user"] = profile_user
    context["profile_bio"] = profile.bio if profile else ""
    context["guest_profile"] = not request.user.is_authenticated
    context["is_profile_owner"] = is_owner
    context["is_profile_friend"] = is_friend
    context["profile_avatar"] = profile.avatar.url if profile and profile.avatar else ""
    context["profile_cover"] = profile.cover_image.url if profile and profile.cover_image else ""
    profile_photo_query = TravelPhoto.objects.select_related(
        "travel", "place", "author", "author__travel_profile", "journal_entry",
    ).prefetch_related(
        "tags", "likes", "comments__author", "comments__likes",
        "comments__replies__author", "comments__replies__likes",
    )
    context["posted_photos"] = (
        profile_photo_query.filter(author=profile_user)
        if is_owner or is_friend else TravelPhoto.objects.none()
    )
    context["liked_photos"] = (
        profile_photo_query.filter(likes=profile_user).distinct()
        if is_owner else TravelPhoto.objects.none()
    )
    profile_connections_by_id = {}
    profile_friend_ids = set()
    excluded_recommendation_ids = {profile_user.id} if profile_user else set()
    if is_owner:
        relationships = Friendship.objects.filter(
            Q(user=profile_user) | Q(friend=profile_user),
        ).select_related("user__travel_profile", "friend__travel_profile")
        for relationship in relationships:
            connected_user = (
                relationship.friend if relationship.user_id == profile_user.id
                else relationship.user
            )
            excluded_recommendation_ids.add(connected_user.id)
            if relationship.status == "accepted":
                profile_friend_ids.add(connected_user.id)
                profile_connections_by_id[connected_user.id] = {
                    "user": connected_user, "status": "Friend",
                }
            elif relationship.user_id == profile_user.id:
                profile_connections_by_id.setdefault(connected_user.id, {
                    "user": connected_user, "status": "Following",
                })
        context["profile_recommendations"] = (
            User.objects.exclude(id__in=excluded_recommendation_ids)
            .select_related("travel_profile")
            .order_by("?")[:5]
        )
    else:
        context["profile_recommendations"] = User.objects.none()
    context["profile_connections"] = list(profile_connections_by_id.values())
    context["friend_count"] = len(profile_friend_ids)
    context["posted_count"] = TravelPhoto.objects.filter(author=profile_user).count() if is_owner else 0
    if is_owner:
        owned_travels = Travel.objects.filter(owner=profile_user)
        travel_ids = owned_travels.values_list("id", flat=True)
        owned_places = Place.objects.filter(
            Q(owner=profile_user) | Q(photos__author=profile_user) | Q(activities__day__travel__owner=profile_user)
        ).distinct()
        profile_crud = [
            {"slug": "journeys", "label": "Journeys", "items": owned_travels, "count": owned_travels.count()},
            {"slug": "countries", "label": "Countries", "items": Country.objects.filter(travels__owner=profile_user).distinct(), "count": Country.objects.filter(travels__owner=profile_user).distinct().count()},
            {"slug": "places", "label": "Saved places", "items": owned_places, "count": owned_places.count()},
            {"slug": "regions", "label": "Regions", "items": Region.objects.filter(places__in=owned_places).distinct(), "count": Region.objects.filter(places__in=owned_places).distinct().count()},
            {"slug": "itinerary-days", "label": "Itinerary days", "items": ItineraryDay.objects.filter(travel_id__in=travel_ids), "count": ItineraryDay.objects.filter(travel_id__in=travel_ids).count()},
            {"slug": "activities", "label": "Activities", "items": Activity.objects.filter(day__travel_id__in=travel_ids), "count": Activity.objects.filter(day__travel_id__in=travel_ids).count()},
            {"slug": "accommodations", "label": "Accommodations", "items": Accommodation.objects.filter(travel_id__in=travel_ids), "count": Accommodation.objects.filter(travel_id__in=travel_ids).count()},
            {"slug": "expenses", "label": "Expenses", "items": Expense.objects.filter(travel_id__in=travel_ids), "count": Expense.objects.filter(travel_id__in=travel_ids).count()},
            {"slug": "photos", "label": "Photos", "items": TravelPhoto.objects.filter(author=profile_user), "count": TravelPhoto.objects.filter(author=profile_user).count()},
            {"slug": "journal-entries", "label": "Journal entries", "items": JournalEntry.objects.filter(travel_id__in=travel_ids), "count": JournalEntry.objects.filter(travel_id__in=travel_ids).count()},
            {"slug": "tags", "label": "Tags", "items": Tag.objects.filter(Q(owner=profile_user) | Q(travels__owner=profile_user)).distinct(), "count": Tag.objects.filter(Q(owner=profile_user) | Q(travels__owner=profile_user)).distinct().count()},
        ]
        profile_crud_by_slug = {record["slug"]: record for record in profile_crud}
        context["profile_crud_groups"] = [
            {
                "number": "01",
                "title": "Plan your journey",
                "description": "Create a journey first, then connect the countries you plan to visit.",
                "records": [profile_crud_by_slug[slug] for slug in ("journeys", "countries")],
            },
            {
                "number": "02",
                "title": "Connect places and days",
                "description": "Save places, link regions, add itinerary days, then plan activities.",
                "records": [
                    profile_crud_by_slug[slug]
                    for slug in ("places", "regions", "itinerary-days", "activities")
                ],
            },
            {
                "number": "03",
                "title": "Add the trip details",
                "description": "Keep bookings, expenses, photos, journal entries, and tags with your journey.",
                "records": [
                    profile_crud_by_slug[slug]
                    for slug in (
                        "accommodations", "expenses", "photos", "journal-entries", "tags",
                    )
                ],
            },
        ]
    return render(request, "diary/profile.html", context)


def settings_view(request):
    if not request.user.is_authenticated:
        return redirect("/login/?next=/settings/")
    if request.method == "POST":
        avatar = request.FILES.get("avatar")
        cover_image = request.FILES.get("cover_image")
        bio = request.POST.get("bio", "").strip()
        if "bio" in request.POST and len(bio) > 500:
            return HttpResponseBadRequest("Bio must be 500 characters or fewer.")
        for upload, label in ((avatar, "Profile photos"), (cover_image, "Profile backgrounds")):
            if upload and upload.size > 5 * 1024 * 1024:
                return HttpResponseBadRequest(f"{label} must be 5 MB or smaller.")
            if upload:
                try:
                    forms.ImageField().clean(upload)
                except ValidationError as error:
                    return HttpResponseBadRequest("; ".join(error.messages))
        request.user.first_name = request.POST.get("first_name", "").strip()
        request.user.last_name = request.POST.get("last_name", "").strip()
        request.user.email = request.POST.get("email", "").strip()
        request.user.save(update_fields=["first_name", "last_name", "email"])
        if "bio" in request.POST or avatar or cover_image:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            update_fields = []
            if "bio" in request.POST:
                profile.bio = bio
                update_fields.append("bio")
            if avatar:
                profile.avatar = avatar
                update_fields.append("avatar")
            if cover_image:
                profile.cover_image = cover_image
                update_fields.append("cover_image")
            if update_fields:
                profile.save(update_fields=update_fields)
        return redirect("profile")
    context = _social_context(request, "settings")
    context["profile"] = UserProfile.objects.filter(user=request.user).first()
    return render(request, "diary/settings.html", context)


def add_comment(request, photo_id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=/diary/")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = request.POST.get("body", "").strip()
    if not body or len(body) > 1000:
        return HttpResponseBadRequest("Comments must be between 1 and 1000 characters.")
    parent_id = request.POST.get("parent_comment")
    parent = None
    if parent_id:
        parent = get_object_or_404(PhotoComment, pk=parent_id, photo_id=photo_id, parent__isnull=True)
    comment = PhotoComment.objects.create(
        photo_id=photo_id,
        author=request.user,
        parent=parent,
        body=body,
    )
    recipients = {comment.photo.author_id}
    if parent:
        recipients.add(parent.author_id)
    for recipient_id in recipients - {None, request.user.id}:
        Notification.objects.create(
            recipient_id=recipient_id,
            actor=request.user,
            photo=comment.photo,
            kind="comment",
        )
    return redirect("dashboard")


def like_comment(request, comment_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Log in to like comments."}, status=401)
    comment = get_object_or_404(PhotoComment, pk=comment_id)
    if comment.likes.filter(pk=request.user.pk).exists():
        comment.likes.remove(request.user)
        liked = False
    else:
        comment.likes.add(request.user)
        liked = True
        if comment.author_id and comment.author_id != request.user.id:
            Notification.objects.create(
                recipient_id=comment.author_id,
                actor=request.user,
                photo=comment.photo,
                kind="comment_like",
            )
    return JsonResponse({"liked": liked, "like_count": comment.likes.count()})


def _redirect_after_post_action(request):
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("dashboard")


def edit_photo_caption(request, photo_id):
    photo = TravelPhoto.objects.filter(pk=photo_id).first()
    if photo is None:
        return redirect("dashboard")
    if not request.user.is_authenticated or photo.author_id != request.user.id:
        return HttpResponseForbidden("You can only edit your own posts.")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    caption = request.POST.get("caption", "").strip()
    if len(caption) > 255:
        return HttpResponseBadRequest("Captions must be 255 characters or fewer.")
    photo.caption = caption
    photo.save(update_fields=["caption"])
    return _redirect_after_post_action(request)


def delete_photo(request, photo_id):
    photo = TravelPhoto.objects.filter(pk=photo_id).first()
    if photo is None:
        return redirect("dashboard")
    if not request.user.is_authenticated or photo.author_id != request.user.id:
        return HttpResponseForbidden("You can only delete your own posts.")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    photo.delete()
    return _redirect_after_post_action(request)


def edit_comment(request, comment_id):
    comment = PhotoComment.objects.filter(pk=comment_id).first()
    if comment is None:
        return redirect("dashboard")
    if not request.user.is_authenticated or comment.author_id != request.user.id:
        return HttpResponseForbidden("You can only edit your own comments.")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = request.POST.get("body", "").strip()
    if not body or len(body) > 1000:
        return HttpResponseBadRequest("Comments must be between 1 and 1000 characters.")
    comment.body = body
    comment.save(update_fields=["body"])
    return _redirect_after_post_action(request)


def delete_comment(request, comment_id):
    comment = PhotoComment.objects.filter(pk=comment_id).first()
    if comment is None:
        return redirect("dashboard")
    if not request.user.is_authenticated or comment.author_id != request.user.id:
        return HttpResponseForbidden("You can only delete your own comments.")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    comment.delete()
    return _redirect_after_post_action(request)


def map_view(request):
    places = Place.objects.filter(owner=request.user) if request.user.is_authenticated else Place.objects.none()
    map_posts = TravelPhoto.objects.none()
    if request.user.is_authenticated:
        outgoing_friend_ids = set(Friendship.objects.filter(
            user=request.user, status="accepted",
        ).values_list("friend_id", flat=True))
        incoming_friend_ids = set(Friendship.objects.filter(
            friend=request.user, status="accepted",
        ).values_list("user_id", flat=True))
        friend_ids = outgoing_friend_ids & incoming_friend_ids
        map_posts = TravelPhoto.objects.filter(
            Q(author=request.user) | Q(travel__owner=request.user) | Q(author_id__in=friend_ids),
            place__isnull=False,
        ).select_related("place", "travel", "author").order_by("-created_at")
    return render(request, "diary/map.html", _social_context(request, "map") | {
        "places": places,
        "map_posts": map_posts,
    })


def photo_detail(request, photo_id):
    photo = get_object_or_404(
        TravelPhoto.objects.select_related(
            "travel", "place", "author", "author__travel_profile", "journal_entry",
        ).prefetch_related(
            "tags", "likes", "comments__author", "comments__likes",
            "comments__replies__author", "comments__replies__likes",
        ),
        pk=photo_id,
    )
    is_owner = request.user.is_authenticated and (
        photo.author_id == request.user.id or photo.travel.owner_id == request.user.id
    )
    is_friend = False
    if request.user.is_authenticated and photo.author_id and not is_owner:
        is_friend = (
            Friendship.objects.filter(
                user=request.user, friend_id=photo.author_id, status="accepted",
            ).exists()
            and Friendship.objects.filter(
                user_id=photo.author_id, friend=request.user, status="accepted",
            ).exists()
        )
    if not is_owner and not is_friend:
        raise Http404
    return render(request, "diary/photo_detail.html", _social_context(request, "map") | {
        "photo": photo,
    })


def _social_context(request, active_page):
    display_name = (
        request.user.get_full_name() or request.user.username
        if request.user.is_authenticated
        else "Explorer"
    )
    profile = UserProfile.objects.filter(user=request.user).first() if request.user.is_authenticated else None
    context = {
        "active_page": active_page,
        "user_name": display_name,
        "user_initials": "".join(part[0] for part in display_name.split()[:2]).upper(),
        "user_avatar": profile.avatar.url if profile and profile.avatar else "",
        "user_first_name": display_name.split()[0],
        "travel_count": Travel.objects.count(),
        "photo_count": TravelPhoto.objects.count(),
        "place_count": Place.objects.count(),
    }
    context["notifications"] = _notifications(request)
    context["notification_count"] = sum(notification["unread"] for notification in context["notifications"])
    return context


def _notifications(request=None):
    notifications = []
    if request and request.user.is_authenticated:
        for item in Notification.objects.filter(recipient=request.user).select_related("actor", "photo", "photo__travel"):
            follow_back_state = None
            if item.kind == "follow" and item.actor:
                reverse_relation = Friendship.objects.filter(
                    user=request.user, friend=item.actor,
                ).first()
                follow_back_state = reverse_relation.status if reverse_relation else "available"
            notifications.append({
                "id": item.id,
                "kind": item.kind,
                "name": item.actor.get_full_name() or item.actor.username if item.actor else "A traveler",
                "text": {
                    "like": "liked your travel diary",
                    "comment_like": "liked your comment",
                    "comment": "commented on your travel diary",
                    "follow": "followed you",
                    "friend_accepted": "accepted your friend request",
                }.get(item.kind, "interacted with you"),
                "photo": item.photo,
                "user": item.actor,
                "time": item.created_at,
                "unread": item.read_at is None,
                "follow_back_state": follow_back_state,
            })
        return notifications
    for photo in TravelPhoto.objects.select_related("travel").prefetch_related("likes", "comments").all():
        for user in photo.likes.all():
            notifications.append({
                "kind": "like",
                "name": user.get_full_name() or user.username,
                "text": "liked your travel diary",
                "photo": photo,
                "time": photo.created_at,
                "unread": False,
            })
        for comment in photo.comments.all():
            notifications.append({
                "kind": "comment",
                "name": comment.author.get_full_name() if comment.author else (comment.guest_name or "A traveler"),
                "text": "commented on your travel diary",
                "photo": photo,
                "time": comment.created_at,
                "unread": False,
            })
    for photo in TravelPhoto.objects.select_related("travel").order_by("-created_at")[:3]:
        notifications.append({
            "kind": "post",
            "name": "Travel circle",
            "text": "shared a new travel diary",
            "photo": photo,
            "time": photo.created_at,
            "unread": False,
        })
    if request and request.user.is_authenticated:
        incoming_follows = Friendship.objects.filter(
            friend=request.user, status="pending",
        ).exclude(user=request.user).select_related("user")
        for follow in incoming_follows:
            if not Friendship.objects.filter(user=request.user, friend=follow.user).exists():
                notifications.append({
                    "kind": "follow",
                    "name": follow.user.get_full_name() or follow.user.username,
                    "text": "followed you",
                    "photo": None,
                    "user": follow.user,
                    "time": follow.created_at,
                })
    return sorted(notifications, key=lambda item: item["time"], reverse=True)


def diary_view(request):
    context = _social_context(request, "diary")
    entries = list(TravelPhoto.objects.select_related("travel", "place").prefetch_related("comments").all())
    context["entries"] = entries
    return render(request, "diary/diary.html", context)


def journeys_view(request):
    context = _social_context(request, "journeys")
    context["journeys"] = (
        Travel.objects.filter(owner=request.user).prefetch_related("countries", "photos")
        if request.user.is_authenticated else Travel.objects.none()
    )
    return render(request, "diary/journeys.html", context)


def saved_places_view(request):
    context = _social_context(request, "saved")
    context["places"] = Place.objects.filter(owner=request.user) if request.user.is_authenticated else Place.objects.none()
    return render(request, "diary/saved_places.html", context)


def circle_view(request):
    context = _social_context(request, "circle")
    recent_photos = list(TravelPhoto.objects.select_related("travel", "place").all()[:6])
    context["recent_photos"] = recent_photos
    current_user = request.user if request.user.is_authenticated else None
    excluded_ids = {current_user.id} if current_user else set()
    if current_user:
        relationships = Friendship.objects.filter(
            Q(user=current_user) | Q(friend=current_user),
        )
        for relationship in relationships:
            excluded_ids.add(
                relationship.friend_id
                if relationship.user_id == current_user.id
                else relationship.user_id
            )
    context["suggestions"] = (
        User.objects.exclude(id__in=excluded_ids)
        .select_related("travel_profile")
        .order_by("?")[:3]
    )
    return render(request, "diary/circle.html", context)


def friends_view(request):
    context = _social_context(request, "circle")
    current_user = request.user if request.user.is_authenticated else None
    friend_ids = set()
    if current_user:
        accepted = Friendship.objects.filter(status="accepted")
        friend_ids = set(accepted.filter(user=current_user).values_list("friend_id", flat=True))
        friend_ids.update(accepted.filter(friend=current_user).values_list("user_id", flat=True))
        incoming = Friendship.objects.filter(friend=current_user, status="pending").select_related("user")
        outgoing_ids = set(Friendship.objects.filter(user=current_user, status="pending").values_list("friend_id", flat=True))
    context["friends"] = User.objects.filter(id__in=friend_ids)
    context["incoming_requests"] = incoming
    context["outgoing_requests"] = User.objects.filter(id__in=outgoing_ids)
    context["suggestions"] = User.objects.exclude(id=current_user.id if current_user else 0).exclude(id__in=friend_ids | outgoing_ids).exclude(id__in=incoming.values_list("user_id", flat=True))
    context["is_authenticated"] = bool(current_user)
    return render(request, "diary/friends.html", context)


def add_friend(request, user_id):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next=/friends/")
    if request.method == "POST" and request.user.id != user_id:
        target = User.objects.filter(id=user_id).first()
        if target is None:
            next_url = request.POST.get("next", "")
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect("friends")
        try:
            with transaction.atomic():
                relation, created = Friendship.objects.get_or_create(
                    user=request.user,
                    friend=target,
                    defaults={"status": "pending"},
                )
                if created:
                    Notification.objects.create(recipient=target, actor=request.user, kind="follow")
        except IntegrityError:
            pass
    return redirect("friends")


def accept_friend(request, user_id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=/friends/")
    if request.method == "POST":
        request_row = Friendship.objects.filter(
            user_id=user_id, friend=request.user, status="pending"
        ).first()
        if request_row:
            request_row.status = "accepted"
            request_row.save(update_fields=["status"])
            Friendship.objects.update_or_create(
                user=request.user,
                friend_id=user_id,
                defaults={"status": "accepted"},
            )
            Notification.objects.create(
                recipient=request_row.user,
                actor=request.user,
                kind="friend_accepted",
            )
    return redirect("friends")


def remove_friend(request, user_id):
    if not request.user.is_authenticated:
        return redirect("/login/?next=/friends/")
    if request.method == "POST":
        Friendship.objects.filter(
            user=request.user, friend_id=user_id, status="accepted"
        ).delete()
        Friendship.objects.filter(
            user_id=user_id, friend=request.user, status="accepted"
        ).delete()
    return redirect("friends")


def login_view(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
        if user:
            login(request, user)
            return redirect(request.POST.get("next") or "dashboard")
        return render(request, "diary/login.html", {"error": "Those login details were not recognized."})
    return render(request, "diary/login.html", {"next": request.GET.get("next", "")})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("dashboard")
    return render(request, "diary/signup.html", {"form": form})


def google_login(request):
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        return render(
            request,
            "diary/login.html",
            {
                "error": "Google sign-in is not configured yet. You can create an account or log in with your username.",
                "next": request.GET.get("next", ""),
            },
        )
    state = secrets.token_urlsafe(32)
    request.session["google_oauth_state"] = state
    redirect_uri = request.build_absolute_uri("/oauth/google/callback/")
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
    )
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


def google_callback(request):
    if request.GET.get("state") != request.session.pop("google_oauth_state", None):
        return render(request, "diary/login.html", {"error": "Google sign-in could not be verified."})
    code = request.GET.get("code")
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not code or not client_id or not client_secret:
        return render(request, "diary/login.html", {"error": "Google sign-in was not completed."})
    redirect_uri = request.build_absolute_uri("/oauth/google/callback/")
    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if token_response.status_code != 200:
        return render(request, "diary/login.html", {"error": "Google sign-in could not be completed."})
    access_token = token_response.json().get("access_token")
    profile_response = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if profile_response.status_code != 200:
        return render(request, "diary/login.html", {"error": "Google profile information could not be read."})
    profile = profile_response.json()
    email = profile.get("email")
    if not email:
        return render(request, "diary/login.html", {"error": "Google did not provide an email address."})
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        base_username = "".join(character for character in email.split("@")[0].lower() if character.isalnum())[:120] or "traveler"
        username = base_username
        suffix = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username[:115]}{suffix}"
            suffix += 1
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=profile.get("given_name", ""),
            last_name=profile.get("family_name", ""),
        )
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("dashboard")


def logout_view(request):
    logout(request)
    return redirect("landing")


def notifications_view(request):
    if request.user.is_authenticated:
        Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return render(request, "diary/notifications.html", _social_context(request, "notifications"))


def mark_notifications_read(request):
    if request.user.is_authenticated:
        Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return redirect(request.META.get("HTTP_REFERER") or "dashboard")


def delete_notification(request, notification_id):
    if request.method == "POST" and request.user.is_authenticated:
        Notification.objects.filter(id=notification_id, recipient=request.user).delete()
    return redirect(request.META.get("HTTP_REFERER") or "notifications")
