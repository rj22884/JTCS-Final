/*
    JTCS ERP — HR module (recruitment through appointment)

    Schema is created idempotently by app.services.hr_schema.ensure_hr_schema()
    on application startup. This file documents the ERP SQL Server tables.

    Existing website applications remain in the recruitment SQLite store
    (job_applications / candidates). This script does NOT create a replacement
    application table and does NOT delete or migrate those rows.
*/
SET NOCOUNT ON;
GO
-- Tables: HrDepartment, HrDesignation, HrEmploymentType, HrWorkLocation,
--         HrEmployeeNumberSequence, HrApplicationState, HrEmployee,
--         HrInterview, HrOfferLetter, HrAppointmentLetter,
--         HrLetterTemplate, HrEmployeeDocument
-- Menu: top-level HR and child items (Administrator,Admin)
-- Run via ERP startup; re-running ensure_hr_schema is safe.
GO
