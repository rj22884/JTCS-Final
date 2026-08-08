"""Customer Portal field policy — only Customer Master columns, no duplicates."""

from __future__ import annotations

# Never editable by the customer (always disabled in UI + ignored on save).
PORTAL_READONLY_FIELDS = frozenset({
    "customer_name",
    "pan_number",
})

# Admin / system fields — never accepted from portal self-service updates.
PORTAL_BLOCKED_FIELDS = frozenset({
    "customer_name",
    "pan_number",
    "customer_group",
    "customer_type",
    "customer_status",
    "opening_balance",
    "opening_balance_date",
    "opening_balance_dr_cr",
    "income_tax_password",
    "aadhaar_reference_id",
})

# Editable Customer Master form keys (must exist in FORM_TO_DB).
PORTAL_EDITABLE_FIELDS = frozenset({
    "father_husband_name",
    "company_firm_name",
    "date_of_birth",
    "date_of_incorporation",
    "gender",
    "occupation",
    "mobile_number",
    "alternate_mobile",
    "whatsapp_number",
    "email_id",
    "website",
    "address_line1",
    "address_line2",
    "village",
    "area",
    "city",
    "district",
    "state",
    "state_gst_code",
    "country",
    "pincode",
    "aadhaar_number",
    "gst_number",
    "filing_frequency",
    "tan_number",
    "pran_number",
    "driving_license_number",
    "passport_number",
    "voter_id_number",
    "ration_card_number",
    "msme_registration_number",
    "udyam_registration_number",
    "cin_number",
    "llpin_number",
    "shop_act_license_number",
    "trade_license_number",
    "labour_license_number",
    "pf_establishment_number",
    "esic_registration_number",
    "professional_tax_number",
    "epfo_code",
    "bank_name",
    "branch_name",
    "account_holder_name",
    "account_number",
    "ifsc_code",
    "facebook",
    "instagram",
    "twitter_x",
    "linkedin",
    "youtube",
    "remarks",
    "photo_path",
})

# Profile form sections for UI (label, field keys).
PORTAL_PROFILE_SECTIONS = (
    (
        "Identity",
        (
            ("customer_name", "Customer Name", True),
            ("pan_number", "PAN", True),
            ("father_husband_name", "Father / Husband Name", False),
            ("company_firm_name", "Business / Firm Name", False),
            ("date_of_birth", "Date of Birth", False),
            ("date_of_incorporation", "Date of Incorporation", False),
            ("gender", "Gender", False),
            ("occupation", "Occupation", False),
            ("aadhaar_number", "Aadhaar Number", False),
            ("passport_number", "Passport Number", False),
            ("voter_id_number", "Voter ID Number", False),
            ("driving_license_number", "Driving License Number", False),
            ("ration_card_number", "Ration Card Number", False),
            ("pran_number", "PRAN Number", False),
        ),
    ),
    (
        "Contact",
        (
            ("mobile_number", "Mobile Number", False),
            ("alternate_mobile", "Alternate Mobile", False),
            ("whatsapp_number", "WhatsApp Number", False),
            ("email_id", "Email", False),
            ("website", "Website", False),
        ),
    ),
    (
        "Address",
        (
            ("address_line1", "Address Line 1", False),
            ("address_line2", "Address Line 2", False),
            ("village", "Village", False),
            ("area", "Area", False),
            ("city", "City", False),
            ("district", "District", False),
            ("state", "State", False),
            ("state_gst_code", "State GST Code", False),
            ("country", "Country", False),
            ("pincode", "PIN Code", False),
        ),
    ),
    (
        "Tax & Compliance",
        (
            ("gst_number", "GST Number", False),
            ("filing_frequency", "GST Filing Frequency", False),
            ("tan_number", "TAN Number", False),
            ("msme_registration_number", "MSME Registration Number", False),
            ("udyam_registration_number", "UDYAM Registration Number", False),
            ("cin_number", "CIN Number", False),
            ("llpin_number", "LLPIN Number", False),
            ("shop_act_license_number", "Shop Act License Number", False),
            ("trade_license_number", "Trade License Number", False),
            ("labour_license_number", "Labour License Number", False),
            ("pf_establishment_number", "PF Establishment Number", False),
            ("esic_registration_number", "ESIC Registration Number", False),
            ("professional_tax_number", "Professional Tax Number", False),
            ("epfo_code", "EPFO Code", False),
        ),
    ),
    (
        "Bank Details",
        (
            ("bank_name", "Bank Name", False),
            ("branch_name", "Branch Name", False),
            ("account_holder_name", "Account Holder Name", False),
            ("account_number", "Account Number", False),
            ("ifsc_code", "IFSC Code", False),
        ),
    ),
    (
        "Social & Remarks",
        (
            ("facebook", "Facebook", False),
            ("instagram", "Instagram", False),
            ("twitter_x", "Twitter / X", False),
            ("linkedin", "LinkedIn", False),
            ("youtube", "YouTube", False),
            ("remarks", "Remarks", False),
        ),
    ),
)

PORTAL_MODULES = {
    "profile": {
        "title": "Profile",
        "icon": "bi-person-vcard",
        "blurb": "View and update your Customer Master profile",
    },
    "documents": {
        "title": "Documents",
        "icon": "bi-folder2-open",
        "blurb": "Documents uploaded for your account",
    },
    "itr": {
        "title": "Income Tax Returns",
        "icon": "bi-file-earmark-text",
        "blurb": "ITR follow-ups, status and related records",
    },
    "gst": {
        "title": "GST Returns",
        "icon": "bi-receipt",
        "blurb": "GST follow-ups and invoices",
    },
    "tds": {
        "title": "TDS",
        "icon": "bi-cash-coin",
        "blurb": "TDS follow-ups and related records",
    },
    "notices": {
        "title": "Notices",
        "icon": "bi-bell",
        "blurb": "Notices and compliance alerts on file",
    },
    "downloads": {
        "title": "Downloads",
        "icon": "bi-download",
        "blurb": "Downloadable documents and acknowledgements",
    },
    "payments": {
        "title": "Payments",
        "icon": "bi-credit-card",
        "blurb": "Invoices, receipts and payment history",
    },
    "support": {
        "title": "Support Tickets",
        "icon": "bi-life-preserver",
        "blurb": "Tasks, conversations and support history",
    },
}
