from datetime import date
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import (
    Accommodation, Country, Expense, Friendship, ItineraryDay, JournalEntry,
    Notification, PhotoComment, Place, Region, Tag, Travel, TravelPhoto,
    UserProfile,
)


def uploaded_test_image(name):
    image_data = BytesIO()
    Image.new("RGB", (1, 1), color="white").save(image_data, format="JPEG")
    return SimpleUploadedFile(name, image_data.getvalue(), content_type="image/jpeg")


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

    def test_database_migrations_do_not_leave_demo_accounts_or_content(self):
        demo_usernames = (
            "alex", "maya", "leo", "maya.demo",
            "wanderer.alex", "roam.maya", "travel.leo",
            "explore.nina", "journey.sam", "pathways.jules",
        )
        self.assertFalse(User.objects.filter(username__in=demo_usernames).exists())
        self.assertFalse(Travel.objects.filter(description__startswith="A sample travel story shared by ").exists())
        self.assertFalse(Travel.objects.filter(title__startswith="Sample journey").exists())
        self.assertFalse(TravelPhoto.objects.filter(caption__startswith="Sample photo").exists())
        self.assertFalse(Country.objects.filter(name__endswith=" sample").exists())
        self.assertFalse(Place.objects.filter(name__startswith="Sample place").exists())
        self.assertFalse(Tag.objects.filter(name__startswith="demo-").exists())

    def test_login_page_has_no_google_sign_in_option(self):
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Continue with Google")
        self.assertContains(response, "Log in")

    def test_profile_travel_crud_is_owner_only(self):
        self.client.force_login(self.owner)
        response = self.client.get("/profile/")
        self.assertContains(response, "Quiet weekend")
        self.assertContains(self.client.get("/journeys/"), "Quiet weekend")
        self.assertContains(response, "Suggested order for organizing your travel data")
        self.assertContains(response, "Start with a journey")
        self.assertEqual(
            [
                [record["slug"] for record in group["records"]]
                for group in response.context["profile_crud_groups"]
            ],
            [
                ["journeys", "countries"],
                ["places", "regions", "itinerary-days", "activities"],
                ["accommodations", "expenses", "photos", "journal-entries", "tags"],
            ],
        )

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

    def test_memory_form_can_create_journey_and_recommended_place(self):
        self.client.force_login(self.owner)
        form_response = self.client.get("/memory/new/")
        self.assertContains(form_response, "Create a new journey")
        self.assertContains(form_response, "Map location picker")
        self.assertContains(form_response, 'id="memory-place-search"')
        self.assertContains(form_response, 'data-location-autocomplete="place"')
        self.assertContains(form_response, 'data-place-map-confirm')
        self.assertContains(form_response, 'id="memory-place-map"')
        self.assertContains(form_response, "Confirm location")
        self.assertNotContains(form_response, 'id="id_new_place-name" type="text"')
        self.assertNotContains(form_response, 'id="id_new_place-address" type="text"')
        self.assertContains(form_response, "it will not appear with your public post")
        self.assertContains(form_response, 'data-photo-preview')

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                "/memory/new/",
                {
                    "travel": "__new__",
                    "new_journey-title": "Recent Italy trip",
                    "new_journey-start_date": "2026-06-01",
                    "new_journey-end_date": "2026-06-04",
                    "new_journey-status": "completed",
                    "new_journey-country_name": "Italy",
                    "new_journey-country_code": "ITA",
                    "details": "Private note: booked a small room near the station.",
                    "place": "__new__",
                    "new_place-name": "Colosseum",
                    "new_place-address": "Piazza del Colosseo, Rome, Italy",
                    "new_place-latitude": "41.890210",
                    "new_place-longitude": "12.492230",
                    "caption": "A day in Rome",
                    "image": uploaded_test_image("rome.jpg"),
                },
            )
            self.assertRedirects(response, "/diary/")
            photo = TravelPhoto.objects.get(caption="A day in Rome")
            self.assertTrue(photo.image.storage.exists(photo.image.name))

        travel = Travel.objects.get(owner=self.owner, title="Recent Italy trip")
        self.assertEqual(travel.status, "completed")
        self.assertEqual(
            travel.description,
            "Private note: booked a small room near the station.",
        )
        self.assertTrue(travel.countries.filter(name="Italy").exists())
        place = Place.objects.get(owner=self.owner, name="Colosseum")
        photo = TravelPhoto.objects.get(caption="A day in Rome")
        self.assertEqual(photo.travel, travel)
        self.assertEqual(photo.place, place)
        self.assertEqual(str(place.latitude), "41.890210")
        self.assertEqual(str(place.longitude), "12.492230")

    @override_settings(MAPTILER_API_KEY="test-maptiler-key")
    def test_maptiler_key_is_available_to_both_map_views(self):
        self.client.force_login(self.owner)

        memory_response = self.client.get("/memory/new/")
        map_response = self.client.get("/map/")

        self.assertContains(memory_response, 'data-maptiler-api-key="test-maptiler-key"')
        self.assertContains(map_response, 'data-maptiler-api-key="test-maptiler-key"')

    def test_memory_saves_private_details_to_existing_journey_not_public_post(self):
        private_details = "Remember the tucked-away guesthouse near the station."
        self.travel.description = "Older private travel notes."
        self.travel.save(update_fields=["description"])
        self.client.force_login(self.owner)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            form_response = self.client.get("/memory/new/")
            self.assertContains(form_response, 'data-private-details="Older private travel notes."')
            response = self.client.post(
                "/memory/new/",
                {
                    "travel": self.travel.pk,
                    "details": private_details,
                    "caption": "A morning on the road",
                    "image": uploaded_test_image("private-details.jpg"),
                },
            )
            self.assertRedirects(response, "/diary/")

            photo = TravelPhoto.objects.get(caption="A morning on the road")
            public_post = self.client.get(f"/photos/{photo.pk}/")
            self.assertEqual(public_post.status_code, 200)
            self.assertNotContains(public_post, private_details)

        self.travel.refresh_from_db()
        self.assertEqual(self.travel.description, private_details)

    def test_memory_adds_private_records_and_public_journal_and_tags(self):
        private_values = (
            "Private Harbor Hotel",
            "12 Private Lane",
            "BOOKING-SECRET-77",
            "Private lodging note",
            "Private dinner receipt",
            "987.65",
        )
        public_journal = "The harbor lights made a lovely evening."
        public_tags = ("harbor-walk", "city-lights")
        friend = User.objects.create_user(username="memory-friend", password="pass12345")
        Friendship.objects.create(user=self.owner, friend=friend, status="accepted")
        Friendship.objects.create(user=friend, friend=self.owner, status="accepted")
        self.client.force_login(self.owner)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                "/memory/new/",
                {
                    "travel": self.travel.pk,
                    "caption": "Evening at the harbor",
                    "accommodation-name": private_values[0],
                    "accommodation-address": private_values[1],
                    "accommodation-check_in": "2026-06-01",
                    "accommodation-check_out": "2026-06-03",
                    "accommodation-booking_reference": private_values[2],
                    "accommodation-notes": private_values[3],
                    "expense-category": "food",
                    "expense-description": private_values[4],
                    "expense-amount": private_values[5],
                    "expense-currency": "USD",
                    "expense-spent_on": "2026-06-02",
                    "journal-title": "Harbor evening",
                    "journal-body": public_journal,
                    "journal-entry_date": "2026-06-02",
                    "journal-mood": "peaceful",
                    "journey_tags-tags": ", ".join(public_tags),
                    "image": uploaded_test_image("harbor.jpg"),
                },
            )
            self.assertRedirects(response, "/diary/")

            accommodation = Accommodation.objects.get(travel=self.travel)
            expense = Expense.objects.get(travel=self.travel)
            photo = TravelPhoto.objects.get(caption="Evening at the harbor")
            journal_entry = JournalEntry.objects.get(photo=photo)
            self.assertEqual(accommodation.name, private_values[0])
            self.assertEqual(accommodation.booking_reference, private_values[2])
            self.assertEqual(accommodation.notes, private_values[3])
            self.assertEqual(accommodation.address, private_values[1])
            self.assertEqual(expense.description, private_values[4])
            self.assertEqual(str(expense.amount), private_values[5])
            self.assertEqual(expense.currency, "USD")
            self.assertEqual(journal_entry.body, public_journal)
            self.assertEqual(set(photo.tags.values_list("name", flat=True)), set(public_tags))
            self.assertEqual(set(self.travel.tags.values_list("name", flat=True)), set(public_tags))

            self.client.force_login(friend)
            public_post = self.client.get(f"/photos/{photo.pk}/")
            self.assertEqual(public_post.status_code, 200)
            self.assertContains(public_post, public_journal)
            for tag in public_tags:
                self.assertContains(public_post, f"#{tag}")
            for private_value in private_values:
                self.assertNotContains(public_post, private_value)

            public_feed = self.client.get("/diary/")
            self.assertContains(public_feed, public_journal)
            for private_value in private_values:
                self.assertNotContains(public_feed, private_value)

            api_client = APIClient()
            api_client.force_authenticate(friend)
            self.assertEqual(api_client.get("/api/accommodations/").data["count"], 0)
            self.assertEqual(api_client.get("/api/expenses/").data["count"], 0)

        self.client.force_login(self.owner)
        self.assertContains(self.client.get("/profile/data/journal-entries/"), "Harbor evening")

    def test_memory_rejects_incomplete_optional_record_without_saving_post(self):
        self.client.force_login(self.owner)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                "/memory/new/",
                {
                    "travel": self.travel.pk,
                    "caption": "Should not be saved",
                    "accommodation-name": "Incomplete booking",
                    "image": uploaded_test_image("incomplete.jpg"),
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "This field is required when adding an accommodation.", status_code=400)
        self.assertFalse(TravelPhoto.objects.filter(caption="Should not be saved").exists())
        self.assertFalse(Accommodation.objects.filter(travel=self.travel).exists())

    def test_new_memory_place_requires_suggested_coordinates(self):
        self.client.force_login(self.owner)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                "/memory/new/",
                {
                    "travel": self.travel.pk,
                    "place": "__new__",
                    "new_place-name": "Unlocated place",
                    "image": uploaded_test_image("memory.jpg"),
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Pin a location on the map and confirm it", status_code=400)
        self.assertFalse(Place.objects.filter(owner=self.owner, name="Unlocated place").exists())

    @patch("diary.api.requests.get")
    def test_reverse_geocode_returns_name_address_and_coordinates(self, mock_get):
        mock_get.return_value.json.return_value = {
            "name": "Eiffel Tower",
            "display_name": "Eiffel Tower, Paris, France",
            "address": {"city": "Paris", "country": "France"},
        }

        response = self.client.get("/api/reverse-geocode/?latitude=48.8584&longitude=2.2945")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            "name": "Eiffel Tower",
            "address": "Eiffel Tower, Paris, France",
            "latitude": 48.8584,
            "longitude": 2.2945,
        })
        mock_get.assert_called_once()

    def test_reverse_geocode_rejects_out_of_range_coordinates(self):
        response = self.client.get("/api/reverse-geocode/?latitude=91&longitude=0")

        self.assertEqual(response.status_code, 400)

    def test_memory_rejects_invalid_image_upload(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            "/memory/new/",
            {
                "travel": self.travel.pk,
                "caption": "Not an image",
                "image": SimpleUploadedFile(
                    "not-an-image.jpg",
                    b"not an image",
                    content_type="image/jpeg",
                ),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Upload a valid image.", status_code=400)
        self.assertFalse(TravelPhoto.objects.filter(caption="Not an image").exists())

    def test_quick_posts_create_and_reuse_my_memories_journey(self):
        Friendship.objects.create(user=self.owner, friend=self.other, status="accepted")
        Friendship.objects.create(user=self.other, friend=self.owner, status="accepted")
        self.client.force_login(self.owner)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            for caption in ("First quick post", "Second quick post"):
                response = self.client.post(
                    "/memory/new/",
                    {
                        "travel": "__quick__",
                        "caption": caption,
                        "image": uploaded_test_image(f"{caption.replace(' ', '-').lower()}.jpg"),
                    },
                    follow=True,
                )
                self.assertEqual(response.redirect_chain, [("/diary/", 302)])
                self.assertContains(response, 'data-upload-success-dialog')
                self.assertContains(response, 'data-upload-success-close')

            memory_journeys = Travel.objects.filter(owner=self.owner, title="My memories")
            self.assertEqual(memory_journeys.count(), 1)
            self.assertEqual(
                TravelPhoto.objects.filter(
                    travel=memory_journeys.get(),
                    author=self.owner,
                ).count(),
                2,
            )

        feed_response = self.client.get("/diary/")
        self.assertContains(feed_response, "First quick post")
        self.assertContains(feed_response, "Second quick post")
        self.assertContains(self.client.get("/memories/"), "First quick post")
        self.assertContains(self.client.get("/profile/"), "First quick post")
        self.assertContains(self.client.get("/notifications/"), "posted a new memory")
        friend_client = self.client_class()
        friend_client.force_login(self.other)
        self.assertContains(friend_client.get("/diary/"), "First quick post")
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.owner,
                kind="post",
                photo__author=self.owner,
            ).count(),
            2,
        )

    def test_profile_upload_shows_ok_confirmation_and_is_visible_to_friends(self):
        Friendship.objects.create(user=self.owner, friend=self.other, status="accepted")
        Friendship.objects.create(user=self.other, friend=self.owner, status="accepted")
        self.client.force_login(self.owner)

        profile_response = self.client.get("/profile/")
        self.assertContains(profile_response, 'id="profile-quick-image"')
        self.assertContains(profile_response, 'class="file-picker"')
        self.assertContains(profile_response, "Choose a photo to upload")
        self.assertContains(profile_response, "data-profile-upload-picker-label-text")

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                "/memory/new/",
                {
                    "travel": "__quick__",
                    "next": "/profile/",
                    "caption": "Profile quick upload",
                    "image": uploaded_test_image("profile-quick-upload.jpg"),
                },
                follow=True,
            )

        self.assertEqual(response.redirect_chain, [("/profile/", 302)])
        self.assertContains(response, 'data-upload-success-dialog')
        self.assertContains(response, 'data-upload-success-close')
        self.assertContains(response, "Your photo has been uploaded successfully.")
        self.assertContains(response, "Profile quick upload")

        friend_client = self.client_class()
        friend_client.force_login(self.other)
        self.assertContains(
            friend_client.get(f"/profile/{self.owner.pk}/"),
            "Profile quick upload",
        )

    def test_my_diary_only_shows_posts_authored_by_current_user(self):
        own_post = TravelPhoto.objects.create(
            travel=self.travel,
            author=self.owner,
            caption="My private diary post",
        )
        other_travel = Travel.objects.create(
            owner=self.other,
            title="Another traveler's trip",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 4),
        )
        TravelPhoto.objects.create(
            travel=other_travel,
            author=self.other,
            caption="Another account's post",
        )
        liked_post = TravelPhoto.objects.create(
            travel=other_travel,
            author=self.other,
            caption="Post I liked",
        )
        liked_post.likes.add(self.owner)

        self.client.force_login(self.owner)
        response = self.client.get("/memories/")

        self.assertEqual([entry.pk for entry in response.context["entries"]], [own_post.pk])
        self.assertEqual([entry.pk for entry in response.context["liked_entries"]], [liked_post.pk])
        self.assertContains(response, 'class="diary-like-button liked"')
        self.assertContains(response, 'aria-pressed="true"')

        self.client.logout()
        guest_response = self.client.get("/memories/")
        self.assertEqual(guest_response.context["entries"], [])
        self.assertEqual(guest_response.context["liked_entries"], [])

    def test_top_avatar_opens_account_actions(self):
        self.client.force_login(self.owner)

        diary_response = self.client.get("/memories/")
        dashboard_response = self.client.get("/diary/")

        self.assertContains(diary_response, 'class="account top-account"')
        self.assertContains(diary_response, 'aria-label="Open account menu"')
        self.assertContains(diary_response, "Account settings")
        self.assertContains(diary_response, "Log out")
        self.assertContains(dashboard_response, 'class="account top-account"')
        self.assertContains(dashboard_response, "Account settings")
        self.assertContains(dashboard_response, "Log out")

    def test_dashboard_keeps_liked_post_button_lit_after_reload(self):
        Friendship.objects.create(user=self.owner, friend=self.other, status="accepted")
        photo = TravelPhoto.objects.create(
            travel=self.travel,
            author=self.other,
            caption="Liked feed post",
        )
        api_client = APIClient()
        api_client.force_authenticate(self.owner)
        like_response = api_client.post(f"/api/photos/{photo.pk}/like/")
        self.assertEqual(like_response.status_code, 200)
        self.assertEqual(like_response.data, {"liked": True, "like_count": 1})
        self.client.force_login(self.owner)

        response = self.client.get("/diary/")

        self.assertContains(response, f'data-photo-id="{photo.pk}" data-liked="true"')
        self.assertContains(response, 'class="like-button liked"')
        self.assertContains(response, 'aria-pressed="true"')

    def test_new_journey_cannot_use_another_users_private_country(self):
        private_country = Country.objects.create(
            owner=self.other,
            name="Other user's country",
            code="OTH",
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            "/journeys/new/",
            {
                "title": "Private country test",
                "start_date": "2026-06-01",
                "end_date": "2026-06-04",
                "status": "planned",
                "country": private_country.pk,
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Travel.objects.filter(owner=self.owner, title="Private country test").exists())

    def test_location_recommendations_are_enabled_for_travel_data_fields(self):
        self.client.force_login(self.owner)
        self.assertContains(
            self.client.get("/profile/data/countries/"),
            'data-location-autocomplete="country"',
        )
        self.assertContains(
            self.client.get("/profile/data/places/"),
            'data-location-autocomplete="place"',
        )
        self.assertContains(
            self.client.get("/profile/data/places/"),
            'data-location-autocomplete="address"',
        )
        self.assertContains(
            self.client.get("/profile/data/regions/"),
            'data-location-autocomplete="region"',
        )
        self.assertContains(
            self.client.get("/profile/data/accommodations/"),
            'data-location-autocomplete="address"',
        )

    @patch("diary.api.requests.get")
    def test_country_search_does_not_recommend_a_place_in_another_country(self, mock_get):
        mock_get.return_value.json.return_value = {
            "features": [
                {
                    "properties": {
                        "name": "Japan",
                        "city": "Rome",
                        "state": "Lazio",
                        "country": "Italy",
                        "countrycode": "it",
                    },
                    "geometry": {"coordinates": [12.492, 41.89]},
                },
                {
                    "properties": {
                        "name": "Kyoto",
                        "city": "Kyoto",
                        "state": "Kyoto",
                        "country": "Japan",
                        "countrycode": "jp",
                    },
                    "geometry": {"coordinates": [135.768, 35.011]},
                },
            ],
        }
        response = self.client.get("/api/photon/?q=Japan&kind=country")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["features"]), 1)
        self.assertEqual(response.json()["features"][0]["country"], "Japan")

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
            PhotoComment.objects.create(
                photo=own_photo,
                author=self.owner,
                body="A memory comment",
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
        self.assertContains(profile_response, 'data-profile-post-like')
        self.assertContains(profile_response, 'data-profile-post-save')
        self.assertContains(profile_response, 'data-profile-post-share')
        self.assertContains(profile_response, 'data-profile-post-comment-focus')
        self.assertContains(profile_response, 'data-profile-post-reply')
        self.assertContains(profile_response, 'data-comment-like-url')
        self.assertContains(profile_response, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(profile_response, f'href="/diary/#post-{own_photo.pk}"')

    def test_photo_credit_popover_is_beside_image_label(self):
        source_url = "https://commons.wikimedia.org/?curid=11726877"
        photo = TravelPhoto.objects.create(
            travel=self.travel,
            author=self.owner,
            caption="Great Wall at Mutianyu",
            credit_text=f"Velatrix, CC0; Wikimedia Commons: {source_url}",
            credit_url=source_url,
        )
        self.client.force_login(self.owner)

        dashboard_response = self.client.get("/diary/")
        self.assertContains(dashboard_response, f'href="{source_url}"')
        self.assertContains(dashboard_response, "Photo credit")
        self.assertContains(dashboard_response, ">!</summary>")
        self.assertNotContains(dashboard_response, "Wikimedia Commons:")
        self.assertLess(
            dashboard_response.content.index(b'class="photo-label"'),
            dashboard_response.content.index(b'class="photo-credit-popover"'),
        )
        self.assertLess(
            dashboard_response.content.index(b'class="photo-credit-popover"'),
            dashboard_response.content.index(b'class="photo-count"'),
        )

        detail_response = self.client.get(f"/photos/{photo.pk}/")
        self.assertContains(detail_response, f'href="{source_url}"')
        self.assertContains(detail_response, "Photo credit")
        self.assertContains(detail_response, "profile-photo-credit")

    def test_map_marks_tagged_posts_and_opens_standalone_post_pages(self):
        friend = User.objects.create_user(username="map-friend")
        outsider = User.objects.create_user(username="map-outsider")
        friend_travel = Travel.objects.create(
            owner=friend,
            title="Coastal escape",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 4),
        )
        outsider_travel = Travel.objects.create(
            owner=outsider,
            title="Private trip",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 4),
        )
        own_place = Place.objects.create(
            owner=self.owner,
            name="Old town",
            latitude="48.208200",
            longitude="16.373800",
        )
        friend_place = Place.objects.create(
            owner=friend,
            name="Blue coast",
            latitude="36.721300",
            longitude="-4.421400",
        )
        own_post = TravelPhoto.objects.create(
            travel=self.travel,
            author=self.owner,
            place=own_place,
            caption="A walk through old town",
        )
        friend_post = TravelPhoto.objects.create(
            travel=friend_travel,
            author=friend,
            place=friend_place,
            caption="Sunset by the coast",
        )
        TravelPhoto.objects.create(
            travel=self.travel,
            author=self.owner,
            caption="No tagged location",
        )
        private_post = TravelPhoto.objects.create(
            travel=outsider_travel,
            author=outsider,
            place=Place.objects.create(
                owner=outsider,
                name="Private location",
                latitude="40.712800",
                longitude="-74.006000",
            ),
            caption="Private memory",
        )
        Friendship.objects.create(user=self.owner, friend=friend, status="accepted")
        Friendship.objects.create(user=friend, friend=self.owner, status="accepted")
        self.client.force_login(self.owner)

        map_response = self.client.get("/map/")
        post_ids_on_map = {photo.pk for photo in map_response.context["map_posts"]}

        self.assertEqual(post_ids_on_map, {own_post.pk, friend_post.pk})
        self.assertContains(map_response, "A walk through old town")
        self.assertContains(map_response, "Sunset by the coast")
        self.assertNotContains(map_response, "Private memory")
        self.assertTemplateUsed(map_response, "diary/map.html")

        detail_response = self.client.get(f"/photos/{own_post.pk}/")
        self.assertTemplateUsed(detail_response, "diary/photo_detail.html")
        self.assertContains(detail_response, 'data-photo-post-detail')
        self.assertContains(detail_response, "A walk through old town")
        self.assertContains(detail_response, "data-profile-post-like")
        self.assertContains(detail_response, "data-profile-post-save")
        self.assertContains(detail_response, "data-profile-post-share")
        self.assertEqual(self.client.get(f"/photos/{friend_post.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/photos/{private_post.pk}/").status_code, 404)

    def test_settings_can_update_profile_bio(self):
        self.client.force_login(self.owner)
        settings_response = self.client.get("/settings/")
        self.assertContains(settings_response, 'name="bio"')

        response = self.client.post(
            "/settings/",
            {
                "first_name": self.owner.first_name,
                "last_name": self.owner.last_name,
                "email": self.owner.email,
                "bio": "Collecting trails, stories, and local food.",
            },
        )
        self.assertRedirects(response, "/profile/")
        profile = UserProfile.objects.get(user=self.owner)
        self.assertEqual(profile.bio, "Collecting trails, stories, and local food.")
        self.assertContains(self.client.get("/profile/"), profile.bio)

        invalid_response = self.client.post(
            "/settings/",
            {
                "first_name": self.owner.first_name,
                "last_name": self.owner.last_name,
                "email": self.owner.email,
                "bio": "x" * 501,
            },
        )
        self.assertEqual(invalid_response.status_code, 400)
        profile.refresh_from_db()
        self.assertEqual(profile.bio, "Collecting trails, stories, and local food.")

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
