"""Idempotent HR schema, master seeds, letter templates, and MenuMaster tree."""

from __future__ import annotations

from sqlalchemy import text

from app.extensions import db
from app.models.hr import HrLetterTemplate
from app.models.menu_master import MenuMaster
from app.whats_new import publish_whats_new

_READY = False
ADMIN_ROLES = "Administrator,Admin"

_TABLE_SQL: tuple[str, ...] = (
    """
    IF OBJECT_ID(N'dbo.HrDepartment', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrDepartment (
            DepartmentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            Name NVARCHAR(120) NOT NULL,
            IsActive BIT NOT NULL CONSTRAINT DF_HrDepartment_IsActive DEFAULT (1),
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_HrDepartment_Created DEFAULT (SYSUTCDATETIME())
        );
        CREATE UNIQUE INDEX UX_HrDepartment_Name ON dbo.HrDepartment (Name);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrDesignation', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrDesignation (
            DesignationID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            Name NVARCHAR(120) NOT NULL,
            IsActive BIT NOT NULL CONSTRAINT DF_HrDesignation_IsActive DEFAULT (1),
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_HrDesignation_Created DEFAULT (SYSUTCDATETIME())
        );
        CREATE UNIQUE INDEX UX_HrDesignation_Name ON dbo.HrDesignation (Name);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrEmploymentType', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrEmploymentType (
            EmploymentTypeID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            Name NVARCHAR(80) NOT NULL,
            IsActive BIT NOT NULL CONSTRAINT DF_HrEmploymentType_IsActive DEFAULT (1),
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_HrEmploymentType_Created DEFAULT (SYSUTCDATETIME())
        );
        CREATE UNIQUE INDEX UX_HrEmploymentType_Name ON dbo.HrEmploymentType (Name);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrWorkLocation', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrWorkLocation (
            WorkLocationID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            Name NVARCHAR(120) NOT NULL,
            IsActive BIT NOT NULL CONSTRAINT DF_HrWorkLocation_IsActive DEFAULT (1),
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_HrWorkLocation_Created DEFAULT (SYSUTCDATETIME())
        );
        CREATE UNIQUE INDEX UX_HrWorkLocation_Name ON dbo.HrWorkLocation (Name);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrEmployeeNumberSequence', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrEmployeeNumberSequence (
            SequenceID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            Prefix NVARCHAR(10) NOT NULL CONSTRAINT DF_HrEmpSeq_Prefix DEFAULT (N'EMP'),
            Year INT NOT NULL,
            LastNumber INT NOT NULL CONSTRAINT DF_HrEmpSeq_Last DEFAULT (0)
        );
        CREATE UNIQUE INDEX UX_HrEmpSeq_Year ON dbo.HrEmployeeNumberSequence (Prefix, Year);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrApplicationState', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrApplicationState (
            ApplicationID INT NOT NULL PRIMARY KEY,
            ApplicationNumber NVARCHAR(50) NULL,
            OverlayStatus NVARCHAR(50) NOT NULL,
            UpdatedDate DATETIME2 NOT NULL CONSTRAINT DF_HrAppState_Updated DEFAULT (SYSUTCDATETIME()),
            UpdatedBy NVARCHAR(150) NULL
        );
        CREATE INDEX IX_HrAppState_Status ON dbo.HrApplicationState (OverlayStatus);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrEmployee', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrEmployee (
            EmployeeID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            EmployeeCode NVARCHAR(30) NOT NULL,
            ApplicationID INT NULL,
            ApplicationNumber NVARCHAR(50) NULL,
            CandidateID INT NULL,
            Name NVARCHAR(200) NOT NULL,
            FatherName NVARCHAR(200) NULL,
            DateOfBirth DATE NULL,
            Gender NVARCHAR(20) NULL,
            Mobile NVARCHAR(30) NULL,
            Email NVARCHAR(200) NULL,
            Address NVARCHAR(500) NULL,
            City NVARCHAR(100) NULL,
            State NVARCHAR(100) NULL,
            PinCode NVARCHAR(20) NULL,
            JoiningDate DATE NULL,
            DepartmentID INT NULL,
            DesignationID INT NULL,
            ReportingManager NVARCHAR(200) NULL,
            EmploymentTypeID INT NULL,
            WorkLocationID INT NULL,
            ProbationPeriod NVARCHAR(80) NULL,
            ProbationEndDate DATE NULL,
            EmploymentStatus NVARCHAR(40) NOT NULL CONSTRAINT DF_HrEmployee_Status DEFAULT (N'Active'),
            SalaryCtc DECIMAL(18,2) NULL,
            SalaryFrequency NVARCHAR(30) NULL,
            HighestQualification NVARCHAR(200) NULL,
            LastQualification NVARCHAR(200) NULL,
            Degree NVARCHAR(200) NULL,
            UniversityBoard NVARCHAR(200) NULL,
            PassingYear NVARCHAR(20) NULL,
            PercentageCgpa NVARCHAR(40) NULL,
            TotalExperience NVARCHAR(80) NULL,
            SalesExperience NVARCHAR(80) NULL,
            PreviousCompany NVARCHAR(200) NULL,
            PreviousDesignation NVARCHAR(200) NULL,
            PreviousResponsibilities NVARCHAR(MAX) NULL,
            OtherExperience NVARCHAR(MAX) NULL,
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_HrEmployee_Created DEFAULT (SYSUTCDATETIME()),
            UpdatedDate DATETIME2 NULL,
            CreatedBy NVARCHAR(150) NULL,
            UpdatedBy NVARCHAR(150) NULL
        );
        CREATE UNIQUE INDEX UX_HrEmployee_Code ON dbo.HrEmployee (EmployeeCode);
        CREATE UNIQUE INDEX UX_HrEmployee_ApplicationID
            ON dbo.HrEmployee (ApplicationID) WHERE ApplicationID IS NOT NULL;
        CREATE INDEX IX_HrEmployee_AppNo ON dbo.HrEmployee (ApplicationNumber);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrInterview', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrInterview (
            InterviewID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            ApplicationID INT NOT NULL,
            ApplicationNumber NVARCHAR(50) NULL,
            CandidateName NVARCHAR(200) NULL,
            InterviewDate DATE NULL,
            InterviewTime NVARCHAR(20) NULL,
            InterviewMode NVARCHAR(40) NULL,
            Interviewer NVARCHAR(200) NULL,
            InterviewLocation NVARCHAR(200) NULL,
            MeetingLink NVARCHAR(500) NULL,
            InterviewNotes NVARCHAR(MAX) NULL,
            InterviewResult NVARCHAR(40) NOT NULL CONSTRAINT DF_HrInterview_Result DEFAULT (N'Pending'),
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_HrInterview_Created DEFAULT (SYSUTCDATETIME()),
            UpdatedDate DATETIME2 NULL,
            CreatedBy NVARCHAR(150) NULL,
            UpdatedBy NVARCHAR(150) NULL
        );
        CREATE INDEX IX_HrInterview_App ON dbo.HrInterview (ApplicationID, InterviewDate);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrOfferLetter', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrOfferLetter (
            OfferID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            EmployeeID INT NOT NULL,
            ApplicationID INT NULL,
            ApplicationNumber NVARCHAR(50) NULL,
            OfferNumber NVARCHAR(40) NOT NULL,
            Version INT NOT NULL CONSTRAINT DF_HrOffer_Version DEFAULT (1),
            OfferDate DATE NULL,
            JoiningDate DATE NULL,
            SalaryCtc DECIMAL(18,2) NULL,
            ProbationPeriod NVARCHAR(80) NULL,
            OfferStatus NVARCHAR(30) NOT NULL CONSTRAINT DF_HrOffer_Status DEFAULT (N'Pending'),
            StoredName NVARCHAR(255) NULL,
            OriginalName NVARCHAR(255) NULL,
            GeneratedAt DATETIME2 NOT NULL CONSTRAINT DF_HrOffer_Generated DEFAULT (SYSUTCDATETIME()),
            GeneratedBy NVARCHAR(150) NULL,
            AcceptedAt DATETIME2 NULL,
            EmailedAt DATETIME2 NULL,
            EmailedTo NVARCHAR(200) NULL,
            EmailStatus NVARCHAR(40) NULL
        );
        CREATE INDEX IX_HrOffer_Employee ON dbo.HrOfferLetter (EmployeeID, OfferStatus);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrAppointmentLetter', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrAppointmentLetter (
            AppointmentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            EmployeeID INT NOT NULL,
            ApplicationID INT NULL,
            ApplicationNumber NVARCHAR(50) NULL,
            AppointmentNumber NVARCHAR(40) NOT NULL,
            Version INT NOT NULL CONSTRAINT DF_HrAppt_Version DEFAULT (1),
            AppointmentDate DATE NULL,
            JoiningDate DATE NULL,
            StoredName NVARCHAR(255) NULL,
            OriginalName NVARCHAR(255) NULL,
            IssuedAt DATETIME2 NOT NULL CONSTRAINT DF_HrAppt_Issued DEFAULT (SYSUTCDATETIME()),
            IssuedBy NVARCHAR(150) NULL,
            EmailedAt DATETIME2 NULL,
            EmailedTo NVARCHAR(200) NULL,
            EmailStatus NVARCHAR(40) NULL
        );
        CREATE INDEX IX_HrAppt_Employee ON dbo.HrAppointmentLetter (EmployeeID);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrLetterTemplate', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrLetterTemplate (
            TemplateID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            LetterType NVARCHAR(40) NOT NULL,
            SectionKey NVARCHAR(80) NOT NULL,
            Title NVARCHAR(200) NOT NULL,
            Body NVARCHAR(MAX) NOT NULL,
            SortOrder INT NOT NULL CONSTRAINT DF_HrTpl_Sort DEFAULT (0),
            IsActive BIT NOT NULL CONSTRAINT DF_HrTpl_Active DEFAULT (1)
        );
        CREATE UNIQUE INDEX UX_HrTpl_TypeKey ON dbo.HrLetterTemplate (LetterType, SectionKey);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.HrEmployeeDocument', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.HrEmployeeDocument (
            DocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            EmployeeID INT NOT NULL,
            ApplicationID INT NULL,
            DocumentType NVARCHAR(80) NOT NULL,
            OriginalName NVARCHAR(255) NOT NULL,
            StoredName NVARCHAR(255) NOT NULL,
            MimeType NVARCHAR(120) NULL,
            FileSizeBytes INT NULL,
            UploadedBy NVARCHAR(150) NULL,
            UploadedAt DATETIME2 NOT NULL CONSTRAINT DF_HrDoc_Uploaded DEFAULT (SYSUTCDATETIME())
        );
        CREATE INDEX IX_HrDoc_Employee ON dbo.HrEmployeeDocument (EmployeeID, DocumentType);
    END;
    """,
)

_MASTER_SEEDS = (
    ("HrDepartment", "Name", ("Sales", "Accounts", "IT", "Administration", "HR", "Operations")),
    (
        "HrDesignation",
        "Name",
        (
            "Sales Executive",
            "Senior Sales Executive",
            "Accountant",
            "IT Executive",
            "Software Developer",
            "Manager",
        ),
    ),
    ("HrEmploymentType", "Name", ("Full Time", "Part Time", "Contract", "Intern", "Other")),
    ("HrWorkLocation", "Name", ("Haldwani", "Remote", "Other")),
)

DEFAULT_TEMPLATES: tuple[tuple[str, str, str, str, int], ...] = (
    (
        "offer",
        "intro",
        "Introduction",
        "Dear {{employee_name}},\n\nWe are pleased to offer you employment with JTCS Xpert "
        "for the position of {{designation}} in the {{department}} department.",
        10,
    ),
    (
        "offer",
        "position",
        "Position and Joining",
        "Application Number: {{application_number}}\nEmployee Code: {{employee_code}}\n"
        "Designation: {{designation}}\nDepartment: {{department}}\n"
        "Work Location: {{work_location}}\nDate of Joining: {{joining_date}}",
        20,
    ),
    (
        "offer",
        "compensation",
        "Compensation",
        "Your Cost to Company (CTC) will be {{salary_ctc}}. This offer is subject to "
        "the compensation structure communicated separately, if any.",
        30,
    ),
    (
        "offer",
        "probation",
        "Probation",
        "You will be on probation for {{probation_period}}. Confirmation of employment "
        "will depend on satisfactory performance during the probation period.",
        40,
    ),
    (
        "offer",
        "terms",
        "Employment Terms",
        "This offer is subject to verification of documents and information provided "
        "in your application. You will report to {{reporting_manager}}. "
        "Detailed terms will be set out in the appointment letter after you accept this offer.",
        50,
    ),
    (
        "offer",
        "acceptance",
        "Acceptance",
        "Please confirm acceptance of this offer by the stated timeline. "
        "If you have questions, contact the HR team of JTCS Xpert.",
        60,
    ),
    (
        "appointment",
        "intro",
        "Appointment",
        "Dear {{employee_name}},\n\nFollowing acceptance of your offer, we are pleased to "
        "appoint you as {{designation}} in the {{department}} department of JTCS Xpert.",
        10,
    ),
    (
        "appointment",
        "identity",
        "Employment Particulars",
        "Employee Name: {{employee_name}}\nEmployee Code: {{employee_code}}\n"
        "Application Number: {{application_number}}\nDesignation: {{designation}}\n"
        "Department: {{department}}\nDate of Joining: {{joining_date}}\n"
        "Work Location: {{work_location}}\nEmployment Type: {{employment_type}}\n"
        "Reporting Manager: {{reporting_manager}}",
        20,
    ),
    (
        "appointment",
        "compensation",
        "Compensation",
        "Your Cost to Company (CTC) is {{salary_ctc}}. Statutory deductions, if applicable, "
        "will be made as required by law.",
        30,
    ),
    (
        "appointment",
        "probation",
        "Probation Period",
        "Your probation period is {{probation_period}}. During probation, either party may "
        "end employment as per the notice terms stated below.",
        40,
    ),
    (
        "appointment",
        "working",
        "Working Conditions",
        "Your place of work is {{work_location}}. Working hours, weekly offs, and holidays "
        "will follow company policy as amended from time to time.",
        50,
    ),
    (
        "appointment",
        "notice",
        "Notice Period",
        "Either party may terminate employment by giving the notice period specified in "
        "company policy, or payment in lieu thereof, subject to applicable law.",
        60,
    ),
    (
        "appointment",
        "confidentiality",
        "Confidentiality",
        "You shall keep confidential all business, client, and technical information of "
        "JTCS Xpert and shall not disclose it except as required for your duties or by law.",
        70,
    ),
    (
        "appointment",
        "conduct",
        "Code of Conduct",
        "You shall follow the JTCS Xpert code of conduct, professional ethics, and lawful "
        "instructions of the management.",
        80,
    ),
    (
        "appointment",
        "policies",
        "Company Policies",
        "You shall abide by HR, IT, and operational policies of JTCS Xpert as published "
        "and updated by the company.",
        90,
    ),
    (
        "appointment",
        "statutory",
        "Statutory Benefits",
        "Applicable statutory benefits will be extended as required by law and company policy. "
        "Eligibility depends on applicable statutes and your employment category.",
        100,
    ),
    (
        "appointment",
        "acceptance",
        "Acceptance",
        "Please sign and return a copy of this appointment letter to acknowledge that you "
        "have read, understood, and accepted these terms.",
        110,
    ),
)

_MENU_TREE: tuple[tuple[str | None, str, str, str | None, int, str], ...] = (
    (None, "HR", "bi-people", None, 16, "Human resources — recruitment to appointment"),
    ("HR", "Dashboard", "bi-house", "/hr/dashboard", 1, "HR dashboard and recruitment funnel"),
    ("HR", "Recruitment", "bi-briefcase", None, 2, "Recruitment workspace"),
    ("Recruitment", "Job Openings", "bi-megaphone", "/hr/jobs", 1, "Open job listings"),
    ("Recruitment", "Applications", "bi-file-earmark-text", "/hr/applications", 2, "Existing job applications"),
    ("Recruitment", "Recruitment Pipeline", "bi-kanban", "/hr/pipeline", 3, "Application pipeline"),
    ("Recruitment", "Interviews", "bi-calendar-check", "/hr/interviews", 4, "Interview schedule"),
    ("Recruitment", "Selected Candidates", "bi-person-check", "/hr/selected", 5, "Selected candidates"),
    ("HR", "Employees", "bi-person-badge", None, 3, "Employee master"),
    ("Employees", "Employee Master", "bi-person-vcard", "/hr/employees", 1, "Employee records"),
    ("Employees", "Employee Directory", "bi-people", "/hr/employees/directory", 2, "Employee directory"),
    ("Employees", "Employee Documents", "bi-folder2-open", "/hr/employees/documents", 3, "Employee documents"),
    ("Employees", "Employee Timeline", "bi-clock-history", "/hr/employees/timeline", 4, "Employee timeline"),
    ("Employees", "Probation Tracker", "bi-hourglass-split", "/hr/employees/probation", 5, "Probation tracking"),
    ("HR", "Letters", "bi-envelope-paper", None, 4, "HR letters"),
    ("Letters", "Offer Letters", "bi-file-earmark-check", "/hr/letters/offers", 1, "Offer letters"),
    ("Letters", "Appointment Letters", "bi-file-earmark-ruled", "/hr/letters/appointments", 2, "Appointment letters"),
    ("Letters", "Letter Templates", "bi-sliders", "/hr/letters/templates", 3, "Configurable letter templates"),
    ("HR", "HR Masters", "bi-gear", None, 5, "HR master data"),
    ("HR Masters", "Department", "bi-building", "/hr/masters/departments", 1, "Department master"),
    ("HR Masters", "Designation", "bi-award", "/hr/masters/designations", 2, "Designation master"),
    ("HR Masters", "Employment Type", "bi-briefcase", "/hr/masters/employment-types", 3, "Employment type master"),
    ("HR Masters", "Work Location", "bi-geo-alt", "/hr/masters/work-locations", 4, "Work location master"),
    ("HR", "Reports", "bi-graph-up", None, 6, "HR reports"),
    ("Reports", "Recruitment Report", "bi-bar-chart", "/hr/reports/recruitment", 1, "Recruitment report"),
    ("Reports", "Employee Report", "bi-person-lines-fill", "/hr/reports/employees", 2, "Employee report"),
    ("Reports", "Interview Report", "bi-clipboard-data", "/hr/reports/interviews", 3, "Interview report"),
    ("Reports", "Offer & Appointment Report", "bi-file-earmark-spreadsheet", "/hr/reports/letters", 4, "Offer and appointment report"),
    ("HR", "HR Actions", "bi-bell", "/hr/actions", 7, "Pending HR actions"),
)


def _seed_masters() -> None:
    for table, column, values in _MASTER_SEEDS:
        for value in values:
            db.session.execute(
                text(
                    f"""
                    IF NOT EXISTS (
                        SELECT 1 FROM dbo.{table}
                        WHERE LOWER(LTRIM(RTRIM({column}))) = LOWER(LTRIM(RTRIM(:name)))
                    )
                    INSERT INTO dbo.{table} ({column}, IsActive)
                    VALUES (:name, 1);
                    """
                ),
                {"name": value},
            )


def _seed_templates() -> None:
    existing = db.session.query(HrLetterTemplate.TemplateID).limit(1).first()
    if existing:
        return
    for letter_type, section_key, title, body, sort_order in DEFAULT_TEMPLATES:
        db.session.add(
            HrLetterTemplate(
                LetterType=letter_type,
                SectionKey=section_key,
                Title=title,
                Body=body,
                SortOrder=sort_order,
                IsActive=True,
            )
        )


def _upsert_menu(
    *,
    parent_id: int | None,
    name: str,
    icon: str,
    url: str | None,
    order: int,
    description: str,
    background: str | None = None,
) -> int:
    row = None
    if url:
        row = MenuMaster.query.filter(MenuMaster.MenuURL == url).first()
    if row is None:
        q = MenuMaster.query.filter(MenuMaster.MenuName == name)
        if parent_id is None:
            q = q.filter(MenuMaster.ParentMenuID.is_(None))
        else:
            q = q.filter(MenuMaster.ParentMenuID == parent_id)
        row = q.first()
    if row is None:
        row = MenuMaster(
            ParentMenuID=parent_id,
            MenuName=name,
            MenuIcon=icon,
            MenuURL=url,
            DisplayOrder=order,
            Description=description,
            IsActive=True,
            RoleName=ADMIN_ROLES,
            BackgroundColor=background,
        )
        db.session.add(row)
        db.session.flush()
    else:
        row.ParentMenuID = parent_id
        row.MenuName = name
        row.MenuIcon = icon or row.MenuIcon
        row.MenuURL = url
        row.DisplayOrder = order
        row.Description = description
        row.IsActive = True
        row.RoleName = ADMIN_ROLES
        if background:
            row.BackgroundColor = background
        db.session.flush()
    return int(row.MenuID)


def _ensure_menus() -> None:
    ids: dict[str, int] = {}
    for parent_name, name, icon, url, order, description in _MENU_TREE:
        parent_id = ids.get(parent_name) if parent_name else None
        bg = "#1E5A7A" if parent_name is None else None
        menu_id = _upsert_menu(
            parent_id=parent_id,
            name=name,
            icon=icon,
            url=url,
            order=order,
            description=description,
            background=bg,
        )
        ids[name] = menu_id


def ensure_hr_schema() -> None:
    global _READY
    if _READY:
        return
    for statement in _TABLE_SQL:
        db.session.execute(text(statement))
    db.session.commit()
    _seed_masters()
    _seed_templates()
    _ensure_menus()
    db.session.commit()
    try:
        publish_whats_new(
            "feature:hr_module",
            "HR Module",
            detail="HR menu — recruitment, employees, offer and appointment letters.",
            url="/hr/dashboard",
            badge="New",
        )
    except Exception:
        db.session.rollback()
    _READY = True
