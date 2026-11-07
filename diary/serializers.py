from rest_framework import serializers
from .models import (
    Accommodation, Activity, Country, Expense, ItineraryDay, JournalEntry,
    PhotoComment, Place, Region, Tag, Travel, TravelPhoto,
)


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = "__all__"
        read_only_fields = ["owner"]


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = "__all__"
        read_only_fields = ["owner"]


class TravelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Travel
        fields = "__all__"
        read_only_fields = ["owner"]


class ItineraryDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = ItineraryDay
        fields = "__all__"


class PlaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = "__all__"
        read_only_fields = ["owner"]


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = "__all__"


class AccommodationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Accommodation
        fields = "__all__"


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = "__all__"


class TravelPhotoSerializer(serializers.ModelSerializer):
    like_count = serializers.IntegerField(source="likes.count", read_only=True)

    class Meta:
        model = TravelPhoto
        fields = ["id", "travel", "place", "image", "caption", "taken_on", "tags",
                  "created_at", "like_count"]


class PhotoCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    like_count = serializers.IntegerField(source="likes.count", read_only=True)

    class Meta:
        model = PhotoComment
        fields = ["id", "photo", "parent", "author", "guest_name", "author_name", "body", "created_at", "like_count"]
        read_only_fields = ["author", "author_name", "guest_name", "created_at", "like_count"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        parent = attrs.get("parent")
        photo = attrs.get("photo", getattr(self.instance, "photo", None))
        if parent and (photo is None or parent.parent_id is not None or parent.photo_id != photo.id):
            raise serializers.ValidationError({"parent": "Replies must be attached to a top-level comment on the same photo."})
        return attrs

    def get_author_name(self, obj):
        return obj.author.get_username() if obj.author else (obj.guest_name or "Guest")


class JournalEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalEntry
        fields = "__all__"


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = "__all__"
        read_only_fields = ["owner"]
