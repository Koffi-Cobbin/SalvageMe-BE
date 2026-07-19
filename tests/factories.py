import factory
from django.contrib.gis.geos import Point
from factory.django import DjangoModelFactory

from apps.accounts.models import AdminRole, User, UserRating
from apps.dropoff.models import DropOffPoint
from apps.exchanges.models import Exchange
from apps.listings.models import Category, Listing, ListingPhoto
from apps.moderation.models import AuditLog, Report
from apps.partners.models import PartnerApplication
from apps.requests.models import BookRequest


class AdminRoleFactory(DjangoModelFactory):
    class Meta:
        model = AdminRole
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Role {n}")
    description = "A test role."
    capabilities = factory.LazyFunction(list)


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    role = User.Role.BOTH
    is_verified = True
    location = Point(-0.1276, 51.5072, srid=4326)  # London, arbitrary default

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or "testpass123!")
        if create:
            self.save()


class UserRatingFactory(DjangoModelFactory):
    class Meta:
        model = UserRating

    rated_user = factory.SubFactory(UserFactory)
    rated_by = factory.SubFactory(UserFactory)
    exchange = factory.SubFactory("tests.factories.ExchangeFactory")
    score = 5
    comment = "Great exchange!"


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Category {n}")


class ListingFactory(DjangoModelFactory):
    class Meta:
        model = Listing

    owner = factory.SubFactory(UserFactory)
    title = factory.Sequence(lambda n: f"Listing {n}")
    description = "A gently used book, ready for a new home."
    category = factory.SubFactory(CategoryFactory)
    condition = Listing.Condition.GOOD
    status = Listing.Status.AVAILABLE
    location = Point(-0.1276, 51.5072, srid=4326)


class ListingPhotoFactory(DjangoModelFactory):
    class Meta:
        model = ListingPhoto

    listing = factory.SubFactory(ListingFactory)
    fileforge_file_id = factory.Sequence(lambda n: n + 1)
    url = factory.LazyAttribute(lambda o: f"https://cdn.example.com/files/{o.fileforge_file_id}")
    order = 0


class BookRequestFactory(DjangoModelFactory):
    class Meta:
        model = BookRequest

    listing = factory.SubFactory(ListingFactory)
    requester = factory.SubFactory(UserFactory)
    message = "I'd love this book for my classroom."


class ExchangeFactory(DjangoModelFactory):
    class Meta:
        model = Exchange

    listing = factory.SubFactory(ListingFactory)
    donor = factory.SelfAttribute("listing.owner")
    recipient = factory.SubFactory(UserFactory)


class DropOffPointFactory(DjangoModelFactory):
    class Meta:
        model = DropOffPoint

    name = factory.Sequence(lambda n: f"Community Center {n}")
    address = "123 Main St"
    location = Point(-0.1276, 51.5072, srid=4326)


class ReportFactory(DjangoModelFactory):
    class Meta:
        model = Report

    reporter = factory.SubFactory(UserFactory)
    target_type = Report.TargetType.LISTING
    target_id = 1
    reason = Report.Reason.SPAM


class AuditLogFactory(DjangoModelFactory):
    class Meta:
        model = AuditLog

    actor = factory.SubFactory(UserFactory)
    action = "test_action"
    target_type = "listing"
    target_id = 1


class PartnerApplicationFactory(DjangoModelFactory):
    class Meta:
        model = PartnerApplication

    applicant_name = factory.Sequence(lambda n: f"Applicant {n}")
    applicant_email = factory.LazyAttribute(lambda o: f"{o.applicant_name.lower().replace(' ', '')}@example.com")
    applicant_user = factory.SubFactory(UserFactory)
