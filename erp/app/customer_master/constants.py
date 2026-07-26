"""
Customer Master — field groups, tabs per customer group, form/DB mapping.
"""

CUSTOMER_GROUPS = [
    {"code": "ITR", "label": "ITR"},
    {"code": "TDS", "label": "TDS"},
    {"code": "GST", "label": "GST"},
    {"code": "DSC", "label": "DSC"},
]

CUSTOMER_TYPES = [
    "Individual",
    "Proprietor",
    "Partnership",
    "LLP",
    "Private Limited",
    "Public Limited",
    "Trust",
    "Society",
    "NGO",
    "Government",
    "Other",
]

CUSTOMER_STATUSES = ["Active", "Inactive", "Blocked"]
GENDERS = ["Male", "Female", "Other"]
GST_FILING_FREQUENCIES = ["Monthly", "Quarterly", "Yearly"]

MASTER_MANDATORY_FIELDS = frozenset({
    "customer_name",
    "mobile_number",
    "pan_number",
    "aadhaar_number",
    "address_line1",
    "pincode",
    "email_id",
})

# Customer Type "Other": only name is mandatory. PAN defaults to placeholder when blank.
OTHER_CUSTOMER_TYPE = "Other"
OTHER_TYPE_MANDATORY_FIELDS = frozenset({
    "customer_name",
})

FORM_TO_DB = {
    "customer_group": "CustomerGroup",
    "customer_type": "CustomerType",
    "customer_name": "CustomerName",
    "father_husband_name": "FatherHusbandName",
    "company_firm_name": "CompanyFirmName",
    "date_of_birth": "DateOfBirth",
    "date_of_incorporation": "DateOfIncorporation",
    "gender": "Gender",
    "occupation": "Occupation",
    "mobile_number": "MobileNumber",
    "alternate_mobile": "AlternateMobile",
    "whatsapp_number": "WhatsAppNumber",
    "email_id": "EmailID",
    "website": "Website",
    "address_line1": "AddressLine1",
    "address_line2": "AddressLine2",
    "village": "Village",
    "area": "Area",
    "city": "City",
    "district": "District",
    "state": "State",
    "country": "Country",
    "pincode": "Pincode",
    "aadhaar_number": "AadhaarNumber",
    "pan_number": "PANNumber",
    "income_tax_password": "IncomeTaxPassword",
    "gst_number": "GSTNumber",
    "filing_frequency": "FilingFrequency",
    "tan_number": "TANNumber",
    "pran_number": "PRANNumber",
    "driving_license_number": "DrivingLicenseNumber",
    "passport_number": "PassportNumber",
    "voter_id_number": "VoterIDNumber",
    "ration_card_number": "RationCardNumber",
    "msme_registration_number": "MSMERegistrationNumber",
    "udyam_registration_number": "UDYAMRegistrationNumber",
    "cin_number": "CINNumber",
    "llpin_number": "LLPINNumber",
    "shop_act_license_number": "ShopActLicenseNumber",
    "trade_license_number": "TradeLicenseNumber",
    "labour_license_number": "LabourLicenseNumber",
    "pf_establishment_number": "PFEstablishmentNumber",
    "esic_registration_number": "ESICRegistrationNumber",
    "professional_tax_number": "ProfessionalTaxNumber",
    "epfo_code": "EPFOCode",
    "bank_name": "BankName",
    "branch_name": "BranchName",
    "account_holder_name": "AccountHolderName",
    "account_number": "AccountNumber",
    "ifsc_code": "IFSCCode",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "twitter_x": "TwitterX",
    "linkedin": "LinkedIn",
    "youtube": "YouTube",
    "customer_status": "CustomerStatus",
    "remarks": "Remarks",
    "opening_balance": "OpeningBalance",
    "opening_balance_date": "OpeningBalanceDate",
    "opening_balance_dr_cr": "OpeningBalanceDrCr",
}

DB_TO_FORM = {db: form for form, db in FORM_TO_DB.items()}

GROUP_TABS = {
    "ITR": ["basic", "contact", "address", "itr", "bank", "social"],
    "TDS": ["basic", "contact", "address", "tds", "compliance", "bank"],
    "GST": ["basic", "contact", "address", "gst", "business", "bank"],
    "DSC": ["basic", "contact", "address", "dsc", "bank"],
}

TAB_LABELS = {
    "basic": "Basic Info",
    "contact": "Contact",
    "address": "Address",
    "itr": "ITR Details",
    "tds": "TDS Details",
    "gst": "GST Details",
    "dsc": "DSC Details",
    "business": "Business Registration",
    "compliance": "Compliance",
    "bank": "Bank Details",
    "social": "Social Media",
}

GRID_COLUMNS = [
    ("customer_id", "ID"),
    ("customer_name", "Customer Name"),
    ("customer_group", "Group"),
    ("mobile_number", "Mobile"),
    ("pan_number", "PAN"),
    ("email_id", "Email"),
    ("city", "City"),
    ("customer_status", "Status"),
]
