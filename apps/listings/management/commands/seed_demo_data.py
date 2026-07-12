"""
Populates the database with realistic demo data for frontend development:
users (donors/recipients), categories, listings in a mix of statuses,
a couple of requests, one in-progress exchange, and a drop-off point.

    python manage.py seed_demo_data
    python manage.py seed_demo_data --flush   # wipe demo data first
"""
import random

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.dropoff.models import DropOffPoint
from apps.exchanges.models import Exchange
from apps.listings.models import Category, Listing
from apps.requests.models import BookRequest

# Roughly the London area, spread out enough that the `near=` geo filter
# has something interesting to do against these seeded points.
LOCATIONS = [
    (51.5072, -0.1276),  # Central London
    (51.5155, -0.0922),  # Shoreditch
    (51.4816, -0.1911),  # Chelsea
    (51.5433, -0.0119),  # Hackney
    (51.4700, -0.4543),  # Hounslow
]

DEMO_USERS = [
    {"username": "donor_amara", "email": "amara@example.com", "role": User.Role.DONOR},
    {"username": "donor_felix", "email": "felix@example.com", "role": User.Role.DONOR},
    {"username": "recipient_priya", "email": "priya@example.com", "role": User.Role.RECIPIENT},
    {"username": "recipient_marcus", "email": "marcus@example.com", "role": User.Role.RECIPIENT},
    {"username": "both_sophie", "email": "sophie@example.com", "role": User.Role.BOTH},
]

CATEGORY_NAMES = ["Fiction", "Non-Fiction", "Textbooks", "Children's Books", "Reference"]

LISTING_TEMPLATES = [
    ("Introduction to Algebra", "Textbooks", "9th-10th grade", Listing.Condition.GOOD),
    ("To Kill a Mockingbird", "Fiction", "High school", Listing.Condition.WORN),
    ("The Very Hungry Caterpillar", "Children's Books", "Pre-K", Listing.Condition.NEW),
    ("A Brief History of Time", "Non-Fiction", "Adult", Listing.Condition.FAIR),
    ("Oxford English Dictionary (Concise)", "Reference", "All ages", Listing.Condition.GOOD),
    ("Chemistry: The Central Science", "Textbooks", "11th-12th grade", Listing.Condition.FAIR),
    ("Charlotte's Web", "Children's Books", "Elementary", Listing.Condition.GOOD),
    ("Sapiens: A Brief History of Humankind", "Non-Fiction", "Adult", Listing.Condition.NEW),
]


class Command(BaseCommand):
    help = "Seeds realistic demo data (users, categories, listings, requests, an exchange, a drop-off point)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true", help="Delete existing demo users/listings before seeding."
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        with transaction.atomic():
            users = self._seed_users()
            categories = self._seed_categories()
            listings = self._seed_listings(users, categories)
            self._seed_requests_and_exchange(users, listings)
            self._seed_dropoff_point(users)

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write(f"  Users: {len(users)}")
        self.stdout.write(f"  Categories: {len(categories)}")
        self.stdout.write(f"  Listings: {len(listings)}")
        self.stdout.write("  Demo login: username='donor_amara' password='DemoPass123!' (all demo users share this)")

    def _flush(self):
        usernames = [u["username"] for u in DEMO_USERS]
        deleted, _ = User.objects.filter(username__in=usernames).delete()
        self.stdout.write(f"Flushed {deleted} existing demo object(s).")

    def _seed_users(self):
        users = []
        for i, spec in enumerate(DEMO_USERS):
            lat, lng = LOCATIONS[i % len(LOCATIONS)]
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "email": spec["email"],
                    "role": spec["role"],
                    "is_verified": True,
                    "location": Point(lng, lat, srid=4326),
                    "phone": f"+44 7{random.randint(100000000, 999999999)}",
                },
            )
            if created:
                user.set_password("DemoPass123!")
                user.save()
            users.append(user)
        return users

    def _seed_categories(self):
        categories = {}
        for name in CATEGORY_NAMES:
            category, _ = Category.objects.get_or_create(name=name)
            categories[name] = category
        return categories

    def _seed_listings(self, users, categories):
        donors = [u for u in users if u.role in (User.Role.DONOR, User.Role.BOTH)]
        listings = []
        for i, (title, category_name, grade_level, condition) in enumerate(LISTING_TEMPLATES):
            owner = donors[i % len(donors)]
            lat, lng = LOCATIONS[i % len(LOCATIONS)]
            listing = Listing.objects.create(
                owner=owner,
                title=title,
                description=(
                    f"A {condition} copy of '{title}', ready to find a new home. "
                    f"Great for {grade_level.lower()} readers."
                ),
                category=categories[category_name],
                grade_level=grade_level,
                condition=condition,
                location=Point(lng, lat, srid=4326),
            )
            listings.append(listing)
        return listings

    def _seed_requests_and_exchange(self, users, listings):
        recipients = [u for u in users if u.role in (User.Role.RECIPIENT, User.Role.BOTH)]
        if not recipients or not listings:
            return

        # A pending request on one listing.
        BookRequest.objects.get_or_create(
            listing=listings[0],
            requester=recipients[0],
            defaults={"message": "This would be perfect for my classroom library!"},
        )

        # An in-progress exchange (request already accepted) on another listing.
        exchange_listing = listings[1]
        exchange_recipient = recipients[-1]
        if not Exchange.objects.filter(listing=exchange_listing).exists():
            exchange_listing.mark_pending()
            Exchange.objects.create(
                listing=exchange_listing,
                donor=exchange_listing.owner,
                recipient=exchange_recipient,
            )

    def _seed_dropoff_point(self, users):
        coordinator = next((u for u in users if u.is_staff), None)
        DropOffPoint.objects.get_or_create(
            name="Riverside Community Center",
            defaults={
                "address": "12 Riverside Walk, London",
                "location": Point(-0.1276, 51.5072, srid=4326),
                "coordinator": coordinator,
            },
        )
