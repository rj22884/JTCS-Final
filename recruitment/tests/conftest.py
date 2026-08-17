import io
from pathlib import Path

import pytest

from recruitment import create_app
from recruitment.config import TestingConfig
from recruitment.extensions import db
from recruitment.seed import seed_defaults


class TestConfig(TestingConfig):
    pass


@pytest.fixture()
def app(tmp_path):
    TestConfig.UPLOAD_DIR = tmp_path / "uploads"
    TestConfig.APPLICATION_PDF_DIR = tmp_path / "application_pdfs"
    TestConfig.HR_LETTER_DIR = tmp_path / "hr_letters"
    TestConfig.EMPLOYEE_DOC_DIR = tmp_path / "employee_docs"
    application = create_app(TestConfig)
    application.config["UPLOAD_DIR"] = Path(tmp_path / "uploads")
    application.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    application.config["APPLICATION_PDF_DIR"] = Path(tmp_path / "application_pdfs")
    application.config["APPLICATION_PDF_DIR"].mkdir(parents=True, exist_ok=True)
    application.config["HR_LETTER_DIR"] = Path(tmp_path / "hr_letters")
    application.config["HR_LETTER_DIR"].mkdir(parents=True, exist_ok=True)
    application.config["EMPLOYEE_DOC_DIR"] = Path(tmp_path / "employee_docs")
    application.config["EMPLOYEE_DOC_DIR"].mkdir(parents=True, exist_ok=True)
    with application.app_context():
        db.create_all()
        seed_defaults()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(client):
    client.post(
        "/recruitment/admin/login",
        data={"email": "admin@jtcsxpert.com", "password": "TestAdmin!234"},
        follow_redirects=True,
    )
    return client


def pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def sample_form(**overrides) -> dict:
    data = {
        "name": "Ravi Sharma",
        "father_name": "Suresh Sharma",
        "dob": "1998-05-12",
        "gender": "Male",
        "mobile": "9876543210",
        "email": "ravi.sharma@example.com",
        "address": "Nainital Road, Haldwani",
        "city": "Haldwani",
        "state": "Uttarakhand",
        "pin_code": "263139",
        "highest_qualification": "Graduate",
        "last_qualification": "B.Com",
        "university_board": "Kumaun University",
        "passing_year": "2019",
        "percentage_cgpa": "72%",
        "sales_experience_years": "0",
        "sales_experience_months": "0",
        "communication_skills": "Advanced",
        "computer_knowledge": "Intermediate",
        "ms_excel_knowledge": "Intermediate",
        "crm_erp_knowledge": "Beginner",
        "digital_marketing_knowledge": "Beginner",
        "expected_salary": "25000",
        "notice_period": "Immediate",
        "current_employment_status": "Fresher",
        "willing_to_work_haldwani": "yes",
        "willing_to_travel": "yes",
        "source": "JTCS Xpert Website",
        "about_candidate": "I am a motivated graduate looking to start a sales career.",
        "suitability_answer": "I communicate well and want to represent JTCS services.",
        "declaration": "yes",
        "visitor_id": "VTEST001",
        "session_id": "STEST001",
    }
    data.update(overrides)
    return data


def resume_file():
    return (io.BytesIO(pdf_bytes()), "resume.pdf", "application/pdf")
