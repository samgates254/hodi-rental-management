"""Seed a disposable, development-only database for authenticated browser tests."""
import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.utils import timezone
from knox.models import AuthToken
from common.rental_dates import rental_business_date

if settings.DJANGO_ENV == "production":
    raise RuntimeError("Refusing to seed a production database.")
database = Path(settings.DATABASES["default"]["NAME"]).resolve()
if database.suffix != ".sqlite3" or not str(database).startswith(tempfile.gettempdir() + "/hodi-e2e-"):
    raise RuntimeError("Refusing to seed outside a disposable /tmp/hodi-e2e-*.sqlite3 database.")

password = os.environ.get("HODI_E2E_PASSWORD")
manifest = os.environ.get("HODI_E2E_CREDENTIAL_FILE")
if not password or not manifest:
    raise RuntimeError("E2E credentials must be supplied through the isolated runner environment.")

User = get_user_model()
from apps.accounts.models import AccountProfile
from apps.billing.models import Charge, Invoice
from apps.leases.models import Lease
from apps.marketplace.models import CommerceListing, Listing as PropertyListing, ListingPhoto, SupplierProfile
from apps.maintenance.models import MaintenanceRequest, RepairQuotation, RepairQuotationLine, TechnicianProfile, WorkOrder
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from apps.utilities.models import UtilityAccount, UtilityBill


def make_user(username, email, account_type):
    user, created = User.objects.get_or_create(username=username, defaults={
        "email": email, "first_name": username.split("_")[-1].title(), "last_name": "E2E",
    })
    if created:
        user.set_password(password)
        user.save(update_fields=["password"])
    AccountProfile.objects.get_or_create(user=user, defaults={"account_type": account_type})
    return user


owner = make_user("hodi_e2e_owner", "owner@hodi-e2e.invalid", "OWNER")
other_owner = make_user("hodi_e2e_other_owner", "other@hodi-e2e.invalid", "OWNER")
tenant_user = make_user("hodi_e2e_tenant", "tenant@hodi-e2e.invalid", "TENANT")
other_tenant_user = make_user("hodi_e2e_other_tenant", "other-tenant@hodi-e2e.invalid", "TENANT")
accountant = make_user("hodi_e2e_accountant", "accountant@hodi-e2e.invalid", "UNSPECIFIED")
impostor = make_user("hodi_e2e_impostor", "impostor@hodi-e2e.invalid", "UNSPECIFIED")
caretaker = make_user("hodi_e2e_caretaker", "caretaker@hodi-e2e.invalid", "UNSPECIFIED")
technician = make_user("hodi_e2e_technician", "technician@hodi-e2e.invalid", "SERVICE_PROFESSIONAL")
empty_technician = make_user("hodi_e2e_empty_technician", "empty-technician@hodi-e2e.invalid", "SERVICE_PROFESSIONAL")

organization, _ = Organization.objects.get_or_create(name="HODI E2E Demo Organisation")
other_organization, _ = Organization.objects.get_or_create(name="HODI E2E Other Organisation")
OrganizationMembership.objects.get_or_create(organization=organization, user=owner, defaults={"role": "OWNER"})
OrganizationMembership.objects.get_or_create(organization=organization, user=caretaker, defaults={"role": "CARETAKER"})
OrganizationMembership.objects.get_or_create(organization=organization, user=technician, defaults={"role": "TECHNICIAN"})
OrganizationMembership.objects.get_or_create(organization=organization, user=empty_technician, defaults={"role": "TECHNICIAN"})
OrganizationMembership.objects.get_or_create(organization=other_organization, user=other_owner, defaults={"role": "OWNER"})
TechnicianProfile.objects.get_or_create(user=technician, defaults={
    "trade": "PLUMBER", "skills": ["PLUMBER"], "rating_milli": 4000, "acceptance_milli": 800,
})
TechnicianProfile.objects.get_or_create(user=empty_technician, defaults={
    "trade": "PLUMBER", "skills": ["PLUMBER"], "rating_milli": 4000, "acceptance_milli": 800,
})
AccountProfile.objects.filter(user=tenant_user).update(organization=organization)
AccountProfile.objects.filter(user=other_tenant_user).update(organization=other_organization)
today = rental_business_date()

def tenancy(org, tenant_user, suffix):
    prop, _ = Property.objects.get_or_create(organization=org, name=f"E2E Property {suffix}")
    building, _ = Building.objects.get_or_create(property=prop, name="Demo Building")
    unit, _ = Unit.objects.get_or_create(building=building, name="E2E-1", defaults={"status": "OCCUPIED"})
    tenant, _ = Tenant.objects.get_or_create(user=tenant_user, defaults={
        "organization": org, "first_name": tenant_user.first_name, "last_name": "E2E", "phone_number": "+254700000001",
    })
    Lease.objects.get_or_create(tenant=tenant, reference=f"E2E-{suffix}", defaults={
        "unit": unit, "start_date": today - timedelta(days=30), "monthly_rent_minor": 2500000, "status": "ACTIVE",
    })
    return prop, unit, tenant

prop, unit, tenant = tenancy(organization, tenant_user, "A")
other_prop, other_unit, other_tenant = tenancy(other_organization, other_tenant_user, "B")

for prop_, unit_, org_, ref, amount in ((prop, unit, organization, "PRIVATE-LANDLORD-REF", 184500), (other_prop, other_unit, other_organization, "OTHER-PRIVATE-REF", 275000)):
    account, _ = UtilityAccount.objects.get_or_create(organization=org_, property=prop_, unit=unit_, service_type="WATER", defaults={
        "provider_name": "E2E Water Utility", "service_reference": ref, "meter_reference": "PRIVATE-METER-REF",
        "responsible_party": "TENANT", "created_by": org_.memberships.get(role="OWNER").user,
    })
    UtilityBill.objects.get_or_create(account=account, period_start=today.replace(day=1), period_end=today, defaults={
        "due_date": today + timedelta(days=7), "amount_minor": amount, "reading_start": 10,
        "reading_end": 12, "reading_unit": "m3", "document_reference": "private-document-key", "recorded_by": owner if org_ == organization else other_owner,
    })
# Landlord-funded bill for the same unit must remain invisible to the tenant.
landlord_account, _ = UtilityAccount.objects.get_or_create(organization=organization, property=prop, unit=unit, service_type="ELECTRICITY", defaults={
    "provider_name": "Private Landlord Power", "service_reference": "LANDLORD-SECRET", "responsible_party": "LANDLORD", "created_by": owner,
})
UtilityBill.objects.get_or_create(account=landlord_account, period_start=today.replace(day=1), period_end=today, defaults={
    "amount_minor": 999999, "recorded_by": owner,
})

supplier, _ = SupplierProfile.objects.get_or_create(organization=organization, business_name="E2E Home Services", defaults={"created_by": owner, "categories": ["cleaning"]})
listing, _ = CommerceListing.objects.get_or_create(organization=organization, supplier=supplier, title="E2E Cleaning Service", defaults={
    "kind": "SERVICE", "category": "cleaning", "description": "Clearly labelled test listing.", "price_minor": 150000,
    "currency": "KES", "price_unit": "visit", "availability": "AVAILABLE", "is_published": True, "created_by": owner,
})

# Public rental listing fixtures exercise real photo records and the public
# photo endpoint. The source images are existing local HODI property imagery;
# these records are isolated E2E fixtures and never enter the development DB.
photo_unit, _ = Unit.objects.get_or_create(building=unit.building, name="E2E-MARKET-PHOTO", defaults={
    "status": "AVAILABLE", "bedrooms": 2,
})
empty_photo_unit, _ = Unit.objects.get_or_create(building=unit.building, name="E2E-MARKET-EMPTY", defaults={
    "status": "AVAILABLE", "bedrooms": 1,
})
photo_listing, _ = PropertyListing.objects.get_or_create(unit=photo_unit, defaults={
    "title": "E2E Photo Listing", "description": "Isolated browser photo fixture.",
    "monthly_rent_minor": 3200000, "bedrooms": 2, "bathrooms": 1,
    "city": "Nairobi", "area": "E2E Test Area", "status": "PUBLISHED",
    "published_at": timezone.now(), "created_by": owner,
})
empty_photo_listing, _ = PropertyListing.objects.get_or_create(unit=empty_photo_unit, defaults={
    "title": "E2E No Photo Listing", "description": "Isolated no-photo browser fixture.",
    "monthly_rent_minor": 1800000, "bedrooms": 1, "bathrooms": 1,
    "city": "Nairobi", "area": "E2E Test Area", "status": "PUBLISHED",
    "published_at": timezone.now(), "created_by": owner,
})
photo_sources = (
    ("property-exterior.jpg", "E2E property exterior photo", "images/hodi/property-exterior.jpg"),
    ("living-room.jpg", "E2E interior photo", "images/living.jpg"),
)
for position, (filename, caption, relative_source) in enumerate(photo_sources):
    if not ListingPhoto.objects.filter(listing=photo_listing, file_name=filename).exists():
        photo = ListingPhoto(
            listing=photo_listing, file_name=filename, content_type="image/jpeg",
            caption=caption, position=position, is_primary=(position == 0),
        )
        source = settings.BASE_DIR.parent / "frontend" / "public" / relative_source
        with source.open("rb") as image_file:
            photo.image.save(filename, File(image_file), save=False)
        photo.save()

invoice, _ = Invoice.objects.get_or_create(organization=organization, tenant=tenant, period_start=today.replace(day=1), defaults={
    "lease": tenant.leases.first(), "period_end": today, "due_date": today + timedelta(days=5), "status": "POSTED",
    "currency": "KES", "total_cents": 2500000, "balance_cents": 2500000,
})
Charge.objects.get_or_create(
    invoice=invoice,
    charge_type="RENT",
    description="E2E monthly rent",
    defaults={
        "organization": organization,
        "tenant": tenant,
        "amount_cents": 2500000,
        "balance_cents": 2500000,
        "due_date": invoice.due_date,
        "lifecycle": "POSTED",
    },
)
Invoice.objects.get_or_create(organization=other_organization, tenant=other_tenant, period_start=today.replace(day=1), defaults={
    "lease": other_tenant.leases.first(), "period_end": today, "due_date": today + timedelta(days=5), "status": "POSTED",
    "currency": "KES", "total_cents": 500000,
})

request, _ = MaintenanceRequest.objects.get_or_create(unit=unit, title="E2E sink repair", defaults={
    "category": "PLUMBING", "tenant": tenant, "created_by": owner, "description": "E2E approved quote fixture",
    "hazard": 1, "vulnerability": 1, "priority_class": 3, "score_millis": 1000,
})
work_order, _ = WorkOrder.objects.get_or_create(request=request)
work_order.assignee = technician
work_order.status = WorkOrder.Status.ASSIGNED
work_order.save(update_fields=["assignee", "status", "updated_at"])
quotation, _ = RepairQuotation.objects.get_or_create(work_order=work_order, explanation="E2E approved material quote", defaults={
    "submitted_by": owner, "materials_estimate_cents": 200000, "status": "APPROVED", "reviewed_by": owner,
    "decision_at": timezone.now(),
})
line, _ = RepairQuotationLine.objects.get_or_create(quotation=quotation, description="E2E copper pipe", defaults={
    "category": "MATERIAL", "quantity": "2.000", "unit": "metre", "unit_price_cents": 100000, "line_total_cents": 200000,
})
Path(manifest).write_text(json.dumps({
    "password": password,
    "users": {"owner": owner.username, "other_owner": other_owner.username, "tenant": tenant_user.username,
              "other_tenant": other_tenant_user.username, "accountant": accountant.username, "impostor": impostor.username,
              "caretaker": caretaker.username, "technician": technician.username,
              "empty_technician": empty_technician.username},
    "tokens": {key: AuthToken.objects.create(user=user)[1] for key, user in {
        "owner": owner, "other_owner": other_owner, "tenant": tenant_user,
        "other_tenant": other_tenant_user, "accountant": accountant, "impostor": impostor,
              "caretaker": caretaker, "technician": technician, "empty_technician": empty_technician,
    }.items()},
    "organization_id": organization.pk,
    "other_organization_id": other_organization.pk,
    "maintenance_request_id": request.pk,
    "quotation_id": quotation.pk,
    "quotation_line_id": line.pk,
    "supplier_id": supplier.pk,
    "listing_id": listing.pk,
    "property_listing_id": str(photo_listing.pk),
    "no_photo_listing_id": str(empty_photo_listing.pk),
    "tenant_utility_amount_minor": 184500,
}), encoding="utf-8")
Path(manifest).chmod(0o600)
print("Seeded isolated HODI E2E demo records.")
