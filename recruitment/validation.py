"""Server-side validation for recruitment applications."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from recruitment.models import SOURCE_OPTIONS

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
PIN_RE = re.compile(r"^\d{6}$")
NAME_RE = re.compile(
    r"^[\w\u0900-\u097F][\w\u0900-\u097F .,'()\/&+\-]{0,198}$",
    re.UNICODE,
)

GENDERS = ("Male", "Female", "Other", "Prefer not to say")
SKILL_LEVELS = ("Beginner", "Intermediate", "Advanced", "Expert")
EMPLOYMENT_STATUSES = ("Employed", "Unemployed", "Student", "Self-employed", "Fresher")
NOTICE_PERIODS = ("Immediate", "15 days", "30 days", "60 days", "90 days", "Serving notice")
QUALIFICATIONS = (
    "10th",
    "12th",
    "Diploma",
    "Graduate",
    "Post Graduate",
    "Professional (CA/CS/CMA)",
    "Other",
)
INDIAN_STATES = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
)


def _s(data: dict, key: str, max_len: int = 200) -> str:
    return str(data.get(key) or "").strip()[:max_len]


def _required(data: dict, key: str, label: str, errors: dict, max_len: int = 200) -> str:
    value = _s(data, key, max_len)
    if not value:
        errors[key] = f"{label} is required."
    return value


def parse_dob(value: str) -> date | None:
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def validate_dob(value: str) -> tuple[date | None, str | None]:
    dob = parse_dob(value)
    if not dob:
        return None, "Enter a valid date of birth."
    today = date.today()
    if dob >= today:
        return None, "Date of birth cannot be today or in the future."
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 18:
        return None, "Applicants must be at least 18 years old."
    if age > 70:
        return None, "Please enter a valid date of birth."
    return dob, None


def yes_no(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def validate_application(data: dict, has_resume: bool) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}

    clean["name"] = _required(data, "name", "Full name", errors, 200)
    if clean["name"] and not NAME_RE.match(clean["name"]):
        errors["name"] = "Enter a valid full name (letters, numbers and common punctuation)."

    clean["father_name"] = _required(data, "father_name", "Father's name", errors, 200)
    if clean["father_name"] and not NAME_RE.match(clean["father_name"]):
        errors["father_name"] = "Enter a valid father's name."

    dob, dob_err = validate_dob(_s(data, "dob", 20))
    clean["dob"] = dob
    if dob_err:
        errors["dob"] = dob_err

    clean["gender"] = _required(data, "gender", "Gender", errors, 30)
    if clean["gender"] and clean["gender"] not in GENDERS:
        errors["gender"] = "Select a valid gender."

    mobile = re.sub(r"\D", "", _s(data, "mobile", 20))
    if mobile.startswith("91") and len(mobile) == 12:
        mobile = mobile[2:]
    clean["mobile"] = mobile
    if not MOBILE_RE.match(mobile):
        errors["mobile"] = "Enter a valid 10-digit Indian mobile number."

    clean["email"] = _required(data, "email", "Email address", errors, 254).lower()
    if clean["email"] and not EMAIL_RE.match(clean["email"]):
        errors["email"] = "Enter a valid email address."

    clean["address"] = _required(data, "address", "Current address", errors, 500)
    clean["city"] = _required(data, "city", "City", errors, 120)
    clean["state"] = _required(data, "state", "State", errors, 120)
    clean["pin_code"] = _required(data, "pin_code", "PIN code", errors, 10)
    if clean["pin_code"] and not PIN_RE.match(clean["pin_code"]):
        errors["pin_code"] = "Enter a valid 6-digit PIN code."

    clean["highest_qualification"] = _required(
        data, "highest_qualification", "Highest educational qualification", errors
    )
    clean["last_qualification"] = _required(
        data, "last_qualification", "Last academic qualification / degree", errors
    )
    clean["university_board"] = _required(data, "university_board", "University / Board", errors)
    year_raw = _s(data, "passing_year", 8)
    try:
        year = int(year_raw)
        if year < 1970 or year > date.today().year + 1:
            raise ValueError
        clean["passing_year"] = year
    except ValueError:
        errors["passing_year"] = "Enter a valid year of passing."
        clean["passing_year"] = None
    clean["percentage_cgpa"] = _required(data, "percentage_cgpa", "Percentage / CGPA", errors, 40)

    try:
        years = int(str(data.get("sales_experience_years", "")).strip())
        if years < 0 or years > 50:
            raise ValueError
        clean["sales_experience_years"] = years
    except ValueError:
        errors["sales_experience_years"] = "Enter sales experience in years (0 for freshers)."
        clean["sales_experience_years"] = None

    months_raw = str(data.get("sales_experience_months") or "").strip()
    if months_raw == "":
        clean["sales_experience_months"] = 0
    else:
        try:
            months = int(months_raw)
            if months < 0 or months > 11:
                raise ValueError
            clean["sales_experience_months"] = months
        except ValueError:
            errors["sales_experience_months"] = "Months must be between 0 and 11."
            clean["sales_experience_months"] = None

    clean["previous_company"] = _s(data, "previous_company")
    clean["previous_designation"] = _s(data, "previous_designation")
    clean["responsibilities"] = _s(data, "responsibilities", 2000)
    clean["total_work_experience"] = _s(data, "total_work_experience", 80)
    clean["software_sales_experience"] = _s(data, "software_sales_experience")
    clean["b2b_sales_experience"] = _s(data, "b2b_sales_experience")
    clean["tax_accounting_erp_sales_experience"] = _s(data, "tax_accounting_erp_sales_experience")

    for key, label in (
        ("communication_skills", "Communication skills"),
        ("computer_knowledge", "Computer knowledge"),
        ("ms_excel_knowledge", "MS Excel knowledge"),
        ("crm_erp_knowledge", "CRM/ERP knowledge"),
        ("digital_marketing_knowledge", "Digital marketing knowledge"),
    ):
        value = _required(data, key, label, errors, 40)
        if value and value not in SKILL_LEVELS:
            errors[key] = f"Select a valid level for {label.lower()}."
        clean[key] = value
    clean["other_skills"] = _s(data, "other_skills", 500)

    clean["expected_salary"] = _required(data, "expected_salary", "Expected salary", errors, 80)
    clean["notice_period"] = _required(data, "notice_period", "Notice period", errors, 80)
    clean["current_employment_status"] = _required(
        data, "current_employment_status", "Current employment status", errors, 80
    )
    if clean["current_employment_status"] and clean["current_employment_status"] not in EMPLOYMENT_STATUSES:
        errors["current_employment_status"] = "Select a valid employment status."

    haldwani = yes_no(data.get("willing_to_work_haldwani"))
    travel = yes_no(data.get("willing_to_travel"))
    if haldwani is None:
        errors["willing_to_work_haldwani"] = "Please confirm whether you are willing to work in Haldwani."
    if travel is None:
        errors["willing_to_travel"] = "Please confirm whether you are willing to travel for sales."
    clean["willing_to_work_haldwani"] = haldwani
    clean["willing_to_travel"] = travel

    clean["source"] = _required(data, "source", "How you heard about this opportunity", errors, 80)
    if clean["source"] and clean["source"] not in SOURCE_OPTIONS:
        errors["source"] = "Select a valid source."

    clean["about_candidate"] = _required(data, "about_candidate", "Tell us about yourself", errors, 2000)
    clean["suitability_answer"] = _required(
        data, "suitability_answer", "Suitability answer", errors, 2000
    )

    if not yes_no(data.get("declaration")):
        errors["declaration"] = "You must agree to the declaration before submitting."
    clean["declaration"] = True

    if not has_resume:
        errors["resume"] = "Please upload your resume (PDF, DOC or DOCX, max 5 MB)."

    clean["visitor_id"] = _s(data, "visitor_id", 64)
    clean["session_id"] = _s(data, "session_id", 64)
    return clean, errors
