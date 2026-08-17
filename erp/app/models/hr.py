"""HR module models — employees, interviews, letters, and masters."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class HrDepartment(db.Model):
    __tablename__ = "HrDepartment"

    DepartmentID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Name: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class HrDesignation(db.Model):
    __tablename__ = "HrDesignation"

    DesignationID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Name: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class HrEmploymentType(db.Model):
    __tablename__ = "HrEmploymentType"

    EmploymentTypeID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Name: Mapped[str] = mapped_column(Unicode(80), nullable=False)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class HrWorkLocation(db.Model):
    __tablename__ = "HrWorkLocation"

    WorkLocationID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Name: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class HrEmployeeNumberSequence(db.Model):
    __tablename__ = "HrEmployeeNumberSequence"

    SequenceID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Prefix: Mapped[str] = mapped_column(Unicode(10), nullable=False, default="EMP")
    Year: Mapped[int] = mapped_column(Integer, nullable=False)
    LastNumber: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class HrApplicationState(db.Model):
    """ERP overlay for recruitment status. Does not replace website job_applications."""

    __tablename__ = "HrApplicationState"

    # Natural key = website application id (not SQL Server IDENTITY).
    ApplicationID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    ApplicationNumber: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    OverlayStatus: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    UpdatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    UpdatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)


class HrEmployee(db.Model):
    __tablename__ = "HrEmployee"

    EmployeeID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    EmployeeCode: Mapped[str] = mapped_column(Unicode(30), nullable=False, unique=True)
    ApplicationID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ApplicationNumber: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    CandidateID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    Name: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    FatherName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    DateOfBirth: Mapped[date | None] = mapped_column(Date, nullable=True)
    Gender: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Mobile: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    Email: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    Address: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    City: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    State: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    PinCode: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    JoiningDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    DepartmentID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    DesignationID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ReportingManager: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    EmploymentTypeID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    WorkLocationID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ProbationPeriod: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ProbationEndDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    EmploymentStatus: Mapped[str] = mapped_column(Unicode(40), nullable=False, default="Active")
    SalaryCtc: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    SalaryFrequency: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    HighestQualification: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    LastQualification: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    Degree: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    UniversityBoard: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    PassingYear: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    PercentageCgpa: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    TotalExperience: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    SalesExperience: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    PreviousCompany: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    PreviousDesignation: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    PreviousResponsibilities: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    OtherExperience: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    UpdatedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    UpdatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)


class HrInterview(db.Model):
    __tablename__ = "HrInterview"

    InterviewID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ApplicationID: Mapped[int] = mapped_column(Integer, nullable=False)
    ApplicationNumber: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    CandidateName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    InterviewDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    InterviewTime: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    InterviewMode: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    Interviewer: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    InterviewLocation: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    MeetingLink: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    InterviewNotes: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    InterviewResult: Mapped[str] = mapped_column(Unicode(40), nullable=False, default="Pending")
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    UpdatedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    UpdatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)


class HrOfferLetter(db.Model):
    __tablename__ = "HrOfferLetter"

    OfferID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    EmployeeID: Mapped[int] = mapped_column(Integer, nullable=False)
    ApplicationID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ApplicationNumber: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    OfferNumber: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    Version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    OfferDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    JoiningDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    SalaryCtc: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    ProbationPeriod: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    OfferStatus: Mapped[str] = mapped_column(Unicode(30), nullable=False, default="Pending")
    StoredName: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    OriginalName: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    GeneratedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    GeneratedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    AcceptedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    EmailedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    EmailedTo: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    EmailStatus: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)


class HrAppointmentLetter(db.Model):
    __tablename__ = "HrAppointmentLetter"

    AppointmentID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    EmployeeID: Mapped[int] = mapped_column(Integer, nullable=False)
    ApplicationID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ApplicationNumber: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    AppointmentNumber: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    Version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    AppointmentDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    JoiningDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    StoredName: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    OriginalName: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    IssuedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    IssuedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    EmailedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    EmailedTo: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    EmailStatus: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)


class HrLetterTemplate(db.Model):
    __tablename__ = "HrLetterTemplate"

    TemplateID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    LetterType: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    SectionKey: Mapped[str] = mapped_column(Unicode(80), nullable=False)
    Title: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    Body: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    SortOrder: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class HrEmployeeDocument(db.Model):
    __tablename__ = "HrEmployeeDocument"

    DocumentID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    EmployeeID: Mapped[int] = mapped_column(Integer, nullable=False)
    ApplicationID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    DocumentType: Mapped[str] = mapped_column(Unicode(80), nullable=False)
    OriginalName: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    StoredName: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    MimeType: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    FileSizeBytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    UploadedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    UploadedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
