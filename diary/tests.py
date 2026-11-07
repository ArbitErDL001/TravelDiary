from datetime import date
from io import StringIO
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    Accommodation, Activity, Country, Expense, ItineraryDay, JournalEntry,
    Friendship, PhotoComment, Place, Region, Tag, Travel, TravelPhoto, UserProfile,
)


class PrivateTravelDataTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pass12345")
        self.other = User.objects.create_user(username="other", password="pass12345")
        self.travel = Travel.objects.create(
            owner=self.owner,
            title="Quiet weekend",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 4),
        )
        self.day = ItineraryDay.objects.create(
            travel=self.travel,
            day_number=1,
            date=date(2026, 6, 1),
        )

    def test_profile_travel_crud_is_owner_only(self):
        self.client.force_login(self.owner)
        response = self.client.get("/profile/")
        self.assertContains(response, "Quiet weekend")
        self.assertContains(self.client.get("/journeys/"), "Quiet weekend")

        response = self.client.post(
            f"/profile/travels/{self.travel.pk}/edit/",
            {
                "title": "Updated weekend",
                "description": "A private plan",
                "start_date": "2026-06-01",
                "end_date": "2026-06-04",
                "status": "planned",
            },
        )
        self.assertRedirects(response, "/profile/")
        self.travel.refresh_from_db()
        self.assertEqual(self.travel.title, "Updated weekend")

        other_client = self.client_class()
        other_client.force_login(self.other)
        self.assertEqual(other_client.get("/profile/travels/%s/edit/" % self.travel.pk).status_code, 404)
        self.assertNotContains(other_client.get(f"/profile/{self.owner.pk}/"), "Updated weekend")
        self.assertNotContains(other_client.get("/journeys/"), "Updated weekend")
        self.assertEqual(
            other_client.post(f"/profile/travels/{self.travel.pk}/delete/").status_code,
            404,
        )
        self.assertTrue(Travel.objects.filter(pk=self.travel.pk).exists())

        self.client.post(f"/profile/travels/{self.travel.pk}/delete/")
        self.assertFalse(Travel.objects.filter(pk=self.travel.pk).exists())

    def test_profile_memory_cards_open_post_dialog_content(self):
        self.client.force_login(self.owner)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            own_photo = TravelPhoto.objects.create(
                travel=self.travel,
                author=self.owner,
                caption="My profile memory",
                image=SimpleUploadedFile(
                    "profile-memory.jpg",
                    b"profile-image",
                    content_type="image/jpeg",
                ),
            )
            other_travel = Travel.objects.create(
                owner=self.other,
                title="Other journey",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 4),
            )
            liked_photo = TravelPhoto.objects.create(
                travel=other_travel,
                author=self.other,
                caption="A liked memory",
                image=SimpleUploadedFile(
                    "liked-memory.jpg",
                    b"liked-image",
                    content_type="image/jpeg",
                ),
            )
            liked_photo.likes.add(self.owner)

            profile_response = self.client.get("/profile/")

        self.assertContains(profile_response, f'data-photo-id="{own_photo.pk}"')
        self.assertContains(profile_response, f'data-photo-id="{liked_photo.pk}"')
        self.assertContains(profile_response, 'data-profile-post-dialog')
        self.assertContains(profile_response, 'data-fullscreen-photo')
        self.assertContains(profile_response, 'data-profile-image-download download')
        self.assertNotContains(profile_response, f'href="/diary/#post-{own_photo.pk}"')

    def test_friend_posts_have_fullscreen_download_controls(self):
        self.client.force_login(self.owner)
        Friendship.objects.create(user=self.owner, friend=self.other, status="accepted")
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            TravelPhoto.objects.create(
                travel=self.travel,
                author=self.other,
                caption="Shared friend photo",
                image=SimpleUploadedFile(
                    "shared-friend-photo.jpg",
                    b"test-image",
                    content_type="image/jpeg",
                ),
            )
            feed_response = self.client.get("/diary/")
            circle_response = self.client.get("/circle/")

        self.assertContains(feed_response, 'alt="Shared friend photo" data-fullscreen-photo')
        self.assertContains(circle_response, 'alt="Shared friend photo" data-fullscreen-photo')
        self.assertContains(feed_response, 'data-profile-image-download download')
        self.assertContains(circle_response, 'data-profile-image-download download')

    def test_profile_shows_connections_and_friend_recommendations(self):
        friend = User.objects.create_user(username="friend")
        recommendation = User.objects.create_user(username="recommended")
        Friendship.objects.create(user=self.owner, friend=friend, status="accepted")
        Friendship.objects.create(user=friend, friend=self.owner, status="accepted")
        Friendship.objects.create(user=self.owner, friend=self.other, status="pending")
        self.client.force_login(self.owner)

        response = self.client.get("/profile/")

        self.assertContains(response, "Friends &amp; following")
        self.assertContains(response, "friend")
        self.assertContains(response, "Following")
        self.assertContains(response, "recommended")
        self.assertNotIn(self.other, response.context["profile_recommendations"])
        self.assertContains(response, f'name="next" value="/profile/"')
        connections = response.context["profile_connections"]
        connection_ids = [connection["user"].id for connection in connections]
        self.assertEqual(len(connection_ids), 2)
        self.assertEqual(len(connection_ids), len(set(connection_ids)))

    def test_profile_data_tabs_and_expenses_are_private_crud(self):
        self.client.force_login(self.owner)
        UserProfile.objects.create(
            user=self.owner,
            avatar="profile_avatars/owner.jpg",
        )
        categories = (
            "journeys", "countries", "regions", "itinerary-days", "places",
            "activities", "accommodations", "expenses", "photos",
            "journal-entries", "tags",
        )
        for category in categories:
            with self.subTest(category=category):
                response = self.client.get(f"/profile/data/{category}/")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "profile_avatars/owner.jpg")
                self.assertContains(response, "<strong>owner</strong>")

        response = self.client.post(
            "/profile/data/expenses/",
            {
                "travel": self.travel.pk,
                "category": "food",
                "description": "Private dinner",
                "amount": "18.50",
                "currency": "USD",
                "spent_on": "2026-06-02",
            },
        )
        self.assertRedirects(response, "/profile/data/expenses/")
        expense = Expense.objects.get(description="Private dinner")
        self.assertEqual(expense.travel.owner, self.owner)

        self.client.post(f"/profile/data/expenses/{expense.pk}/delete/")
        self.assertFalse(Expense.objects.filter(pk=expense.pk).exists())

        place_response = self.client.post(
            "/profile/data/places/",
            {
                "name": "My private place",
                "latitude": "10.000000",
                "longitude": "20.000000",
                "address": "",
                "description": "",
            },
        )
        self.assertRedirects(place_response, "/profile/data/places/")
        place = Place.objects.get(name="My private place")
        self.assertEqual(place.owner, self.owner)

        country_response = self.client.post(
            "/profile/data/countries/",
            {
                "travel": self.travel.pk,
                "new_country_name": "Hidden country",
                "new_country_code": "HID",
            },
        )
        self.assertRedirects(country_response, "/profile/data/countries/")
        country = Country.objects.get(owner=self.owner, code="HID")
        self.assertTrue(self.travel.countries.filter(pk=country.pk).exists())
        public_country = Country.objects.create(name="Japan", code="JPN")
        self.assertRedirects(
            self.client.post(
                "/profile/data/countries/",
                {"travel": self.travel.pk, "countries": [country.pk, public_country.pk]},
            ),
            "/profile/data/countries/",
        )
        self.assertTrue(self.travel.countries.filter(pk=public_country.pk).exists())
        self.assertRedirects(
            self.client.post(
                "/profile/data/regions/",
                {
                    "place": place.pk,
                    "country": public_country.pk,
                    "new_region_name": "Private region",
                },
            ),
            "/profile/data/regions/",
        )
        place.refresh_from_db()
        region = place.region
        self.assertEqual(region.owner, self.owner)
        self.assertRedirects(
            self.client.post(
                "/profile/data/tags/",
                {"travel": self.travel.pk, "new_tag": "private-tag"},
            ),
            "/profile/data/tags/",
        )
        self.assertTrue(Tag.objects.get(name="private-tag", owner=self.owner).travels.filter(pk=self.travel.pk).exists())
        country_edit = self.client.post(
            f"/profile/data/countries/item/{country.pk}/edit/",
            {"name": "Hidden continent", "code": "HID"},
        )
        self.assertRedirects(country_edit, "/profile/data/countries/")
        country.refresh_from_db()
        self.assertEqual(country.name, "Hidden continent")
        region_edit = self.client.post(
            f"/profile/data/regions/item/{region.pk}/edit/",
            {"country": public_country.pk, "name": "Secret coast"},
        )
        self.assertRedirects(region_edit, "/profile/data/regions/")
        region.refresh_from_db()
        self.assertEqual(region.name, "Secret coast")
        tag = Tag.objects.get(name="private-tag", owner=self.owner)
        tag_edit = self.client.post(
            f"/profile/data/tags/item/{tag.pk}/edit/",
            {"name": "personal-tag"},
        )
        self.assertRedirects(tag_edit, "/profile/data/tags/")

        other_client = self.client_class()
        other_client.force_login(self.other)
        self.assertNotContains(other_client.get("/profile/data/places/"), "My private place")
        self.assertNotContains(other_client.get("/profile/data/countries/"), "Hidden continent")
        self.assertNotContains(other_client.get("/profile/data/regions/"), "Secret coast")
        self.assertNotContains(other_client.get("/profile/data/tags/"), "personal-tag")
        self.assertEqual(
            other_client.post(f"/profile/data/places/{place.pk}/delete/").status_code,
            404,
        )
        for category, item_id in (("countries", country.pk), ("regions", region.pk), ("tags", tag.pk)):
            self.assertEqual(
                other_client.get(f"/profile/data/{category}/item/{item_id}/edit/").status_code,
                404,
            )
        self.client.post(f"/profile/data/tags/item/{tag.pk}/delete/")
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())

    def test_travel_api_limits_read_and_write_to_owner(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        self.assertEqual(client.get("/api/travels/").data["count"], 1)

        client.force_authenticate(self.other)
        self.assertEqual(client.get("/api/travels/").data["count"], 0)
        self.assertEqual(client.get(f"/api/travels/{self.travel.pk}/").status_code, 404)
        response = client.post(
            "/api/travels/",
            {
                "title": "Another account's trip",
                "start_date": "2026-07-01",
                "end_date": "2026-07-02",
                "status": "planned",
                "owner": self.owner.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        created = Travel.objects.get(pk=response.data["id"])
        self.assertEqual(created.owner, self.other)

    def test_child_records_are_scoped_and_cannot_be_attached_to_foreign_travel(self):
        Expense.objects.create(
            travel=self.travel,
            description="Train ticket",
            amount="25.00",
            spent_on=date(2026, 6, 1),
        )
        client = APIClient()
        client.force_authenticate(self.other)
        self.assertEqual(client.get("/api/itinerary-days/").data["count"], 0)
        self.assertEqual(client.get("/api/expenses/").data["count"], 0)
        response = client.post(
            "/api/itinerary-days/",
            {
                "travel": self.travel.pk,
                "day_number": 2,
                "date": "2026-06-02",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        client.force_authenticate(self.owner)
        self.assertEqual(client.get("/api/itinerary-days/").data["count"], 1)
        response = client.post(
            "/api/itinerary-days/",
            {
                "travel": self.travel.pk,
                "day_number": 2,
                "date": "2026-06-02",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_private_api_resources_are_owner_scoped(self):
        place = Place.objects.create(
            owner=self.owner, name="Owner-only API place",
            latitude="10.000000", longitude="20.000000",
        )
        Tag.objects.create(name="Owner-only API tag", owner=self.owner)
        client = APIClient()
        client.force_authenticate(self.other)
        self.assertEqual(client.get("/api/places/").data["count"], 0)
        self.assertEqual(client.get("/api/tags/").data["count"], 0)
        self.assertEqual(client.get(f"/api/places/{place.pk}/").status_code, 404)
        private_country = Country.objects.create(name="API private", code="API", owner=self.owner)
        country_response = client.get("/api/countries/")
        self.assertNotIn(private_country.pk, [row["id"] for row in country_response.data["results"]])
        self.assertEqual(client.get(f"/api/countries/{private_country.pk}/").status_code, 404)

        response = client.post(
            "/api/photos/",
            {"travel": self.travel.pk, "caption": "Not this user's journey"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_comment_replies_likes_and_owner_controls(self):
        photo = TravelPhoto.objects.create(travel=self.travel, author=self.owner)
        other_photo = TravelPhoto.objects.create(travel=self.travel, author=self.owner)
        comment = PhotoComment.objects.create(
            photo=photo,
            author=self.owner,
            body="A helpful tip",
        )

        self.client.force_login(self.other)
        like_url = f"/comments/{comment.pk}/like/"
        response = self.client.post(like_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"liked": True, "like_count": 1})
        response = self.client.post(like_url)
        self.assertEqual(response.json(), {"liked": False, "like_count": 0})

        api_client = APIClient()
        api_client.force_authenticate(self.other)
        response = api_client.post(
            "/api/photo-comments/",
            {"photo": photo.pk, "parent": comment.pk, "body": "Thanks for sharing"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        reply = PhotoComment.objects.get(pk=response.data["id"])
        self.assertEqual(reply.parent, comment)
        self.assertEqual(reply.photo, photo)

        response = api_client.post(
            "/api/photo-comments/",
            {"photo": other_photo.pk, "parent": comment.pk, "body": "Wrong post"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            f"/comments/{comment.pk}/edit/",
            {"body": "Attempted edit"},
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(f"/comments/{comment.pk}/delete/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(PhotoComment.objects.filter(pk=comment.pk).exists())

        self.client.force_login(self.owner)
        response = self.client.get("/diary/")
        self.assertContains(response, "<textarea")
        self.assertContains(response, "Thanks for sharing")
        self.assertContains(response, "data-comment-like-url")
        self.assertNotContains(response, "Comment as")
        self.assertRedirects(
            self.client.post(
                f"/comments/{comment.pk}/edit/",
                {"body": "Updated tip"},
            ),
            "/diary/",
        )
        comment.refresh_from_db()
        self.assertEqual(comment.body, "Updated tip")
        self.assertRedirects(
            self.client.post(f"/comments/{comment.pk}/delete/"),
            "/diary/",
        )
        self.assertFalse(PhotoComment.objects.filter(pk=comment.pk).exists())
        self.assertFalse(PhotoComment.objects.filter(pk=reply.pk).exists())

    def test_seed_travel_data_demo_adds_two_of_each_category_idempotently(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                call_command("seed_travel_data_demo", stdout=StringIO())
                call_command("seed_travel_data_demo", stdout=StringIO())

                for user in (self.owner, self.other):
                    with self.subTest(user=user.username):
                        self.assertEqual(Travel.objects.filter(owner=user, title__contains="sample journey").count(), 2)
                        self.assertEqual(ItineraryDay.objects.filter(travel__owner=user, notes__contains="Sample itinerary").count(), 2)
                        self.assertEqual(Place.objects.filter(owner=user, name__contains="sample").count(), 2)
                        self.assertEqual(Activity.objects.filter(day__travel__owner=user, title__contains="Sample activity").count(), 2)
                        self.assertEqual(Accommodation.objects.filter(travel__owner=user, name__contains="Sample stay").count(), 2)
                        self.assertEqual(Expense.objects.filter(travel__owner=user, description__contains="Sample expense").count(), 2)
                        photos = TravelPhoto.objects.filter(author=user, caption__contains="Sample photo")
                        self.assertEqual(photos.count(), 2)
                        self.assertTrue(all(photo.image and photo.image.storage.exists(photo.image.name) for photo in photos))
                        self.assertTrue(all(photo.image.name.endswith("-v2.jpg") for photo in photos))
                        self.assertEqual(JournalEntry.objects.filter(travel__owner=user, title__contains="Sample journal").count(), 2)
                        self.assertEqual(Tag.objects.filter(owner=user, name__startswith="demo-").count(), 2)
                        self.assertEqual(Country.objects.filter(owner=user, travels__owner=user).distinct().count(), 2)
                        self.assertEqual(Region.objects.filter(owner=user, places__owner=user).distinct().count(), 2)
