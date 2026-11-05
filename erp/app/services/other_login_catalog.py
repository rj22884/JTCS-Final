"""Configurable Other Login services. Flip status to ENABLED to turn a card on."""

from __future__ import annotations

from dataclasses import dataclass

STATUS_ENABLED = "ENABLED"
STATUS_DISABLED = "DISABLED"
STATUS_COMING_SOON = "COMING_SOON"


@dataclass(frozen=True)
class OtherLoginService:
    key: str
    name: str
    subtitle: str
    status: str
    icon: str = "bi-box-arrow-in-right"
    login_url: str | None = None

    @property
    def enabled(self) -> bool:
        return self.status == STATUS_ENABLED

    @property
    def status_label(self) -> str:
        if self.enabled:
            return "Login"
        return "Coming Soon"


OTHER_LOGIN_SERVICES: tuple[OtherLoginService, ...] = (
    OtherLoginService(
        key="uttarakhand_fps",
        name="Uttarakhand FPS Login",
        subtitle="Uttarakhand Ration Card / Food & Civil Supplies",
        status=STATUS_ENABLED,
        icon="bi-shop-window",
        login_url="/fps-login",
    ),
    OtherLoginService(
        key="aadhaar",
        name="Aadhaar Login",
        subtitle="UIDAI – Aadhaar Services",
        status=STATUS_COMING_SOON,
        icon="bi-fingerprint",
    ),
    OtherLoginService(
        key="pan",
        name="PAN Login",
        subtitle="Income Tax / PAN Services",
        status=STATUS_COMING_SOON,
        icon="bi-card-heading",
    ),
    OtherLoginService(
        key="gst",
        name="GST Login",
        subtitle="GST Portal – Taxpayer Services",
        status=STATUS_COMING_SOON,
        icon="bi-receipt",
    ),
    OtherLoginService(
        key="income_tax",
        name="Income Tax Login",
        subtitle="Income Tax e-Filing Portal",
        status=STATUS_COMING_SOON,
        icon="bi-file-earmark-text",
    ),
    OtherLoginService(
        key="tds_traces",
        name="TDS / TRACES Login",
        subtitle="TDS Return & Form 26AS Services",
        status=STATUS_COMING_SOON,
        icon="bi-file-earmark-spreadsheet",
    ),
    OtherLoginService(
        key="epfo",
        name="EPFO Login",
        subtitle="PF / UAN / Employee Services",
        status=STATUS_COMING_SOON,
        icon="bi-people",
    ),
    OtherLoginService(
        key="esic",
        name="ESIC Login",
        subtitle="Employee State Insurance Services",
        status=STATUS_COMING_SOON,
        icon="bi-heart-pulse",
    ),
    OtherLoginService(
        key="udyam",
        name="Udyam Registration Login",
        subtitle="MSME / Udyam Registration",
        status=STATUS_COMING_SOON,
        icon="bi-building",
    ),
    OtherLoginService(
        key="mca",
        name="MCA Login",
        subtitle="Ministry of Corporate Affairs – Company/LLP Services",
        status=STATUS_COMING_SOON,
        icon="bi-briefcase",
    ),
    OtherLoginService(
        key="digilocker",
        name="DigiLocker Login",
        subtitle="Digital Documents & Certificates",
        status=STATUS_COMING_SOON,
        icon="bi-lock",
    ),
    OtherLoginService(
        key="edistrict_uk",
        name="e-District Uttarakhand Login",
        subtitle="Certificates & Citizen Services",
        status=STATUS_COMING_SOON,
        icon="bi-journal-text",
    ),
    OtherLoginService(
        key="bhulekh_uk",
        name="Uttarakhand Revenue / Bhulekh Login",
        subtitle="Land Records & Property Records",
        status=STATUS_COMING_SOON,
        icon="bi-geo-alt",
    ),
    OtherLoginService(
        key="vahan",
        name="Vahan Login",
        subtitle="Vehicle Registration & Transport Services",
        status=STATUS_COMING_SOON,
        icon="bi-truck",
    ),
    OtherLoginService(
        key="sarathi",
        name="Sarathi Login",
        subtitle="Driving Licence / Transport Services",
        status=STATUS_COMING_SOON,
        icon="bi-person-vcard",
    ),
    OtherLoginService(
        key="passport_seva",
        name="Passport Seva Login",
        subtitle="Passport & Application Services",
        status=STATUS_COMING_SOON,
        icon="bi-book",
    ),
    OtherLoginService(
        key="nps",
        name="NPS Login",
        subtitle="National Pension System",
        status=STATUS_COMING_SOON,
        icon="bi-piggy-bank",
    ),
    OtherLoginService(
        key="gem",
        name="GeM Login",
        subtitle="Government e-Marketplace",
        status=STATUS_COMING_SOON,
        icon="bi-cart3",
    ),
    OtherLoginService(
        key="cpgrams",
        name="CPGRAMS Login",
        subtitle="Government Grievance Services",
        status=STATUS_COMING_SOON,
        icon="bi-megaphone",
    ),
    OtherLoginService(
        key="jan_aadhaar",
        name="Jan Aadhaar / Citizen Services",
        subtitle="Citizen Welfare & Government Services",
        status=STATUS_COMING_SOON,
        icon="bi-person-badge",
    ),
    OtherLoginService(
        key="pfms",
        name="PFMS Login",
        subtitle="Public Financial Management System",
        status=STATUS_COMING_SOON,
        icon="bi-cash-stack",
    ),
    OtherLoginService(
        key="eway_bill",
        name="e-Way Bill Login",
        subtitle="GST E-Way Bill Services",
        status=STATUS_COMING_SOON,
        icon="bi-signpost-2",
    ),
    OtherLoginService(
        key="einvoice",
        name="e-Invoice Login",
        subtitle="GST e-Invoice Services",
        status=STATUS_COMING_SOON,
        icon="bi-receipt-cutoff",
    ),
    OtherLoginService(
        key="fssai",
        name="FSSAI Login",
        subtitle="Food Business Registration & Licensing",
        status=STATUS_COMING_SOON,
        icon="bi-egg-fried",
    ),
    OtherLoginService(
        key="startup_india",
        name="Startup India Login",
        subtitle="Startup Registration & Services",
        status=STATUS_COMING_SOON,
        icon="bi-rocket-takeoff",
    ),
)


def list_other_login_services() -> list[OtherLoginService]:
    return list(OTHER_LOGIN_SERVICES)


def get_other_login_service(key: str) -> OtherLoginService | None:
    needle = (key or "").strip().lower()
    for item in OTHER_LOGIN_SERVICES:
        if item.key == needle:
            return item
    return None
