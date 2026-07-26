/*
    Inspect Users table for duplicate emails, legacy accounts, and registration conflicts.
    Run on JTCS database before cleanup.
*/
SET NOCOUNT ON;

PRINT '=== All user accounts ===';
SELECT
    UserID,
    FullName,
    EmailID,
    LOWER(EmailID) AS EmailNormalized,
    Role,
    UserStatus,
    IsActive,
    EmailVerified,
    AdminApproved,
    CreatedDate,
    ModifiedDate,
    LastLoginDate
FROM dbo.Users
ORDER BY UserID;

PRINT '=== Duplicate emails (case-insensitive) ===';
SELECT
    LOWER(EmailID) AS EmailNormalized,
    COUNT(*) AS DuplicateCount,
    STRING_AGG(CAST(UserID AS NVARCHAR(20)), N', ') AS UserIDs
FROM dbo.Users
GROUP BY LOWER(EmailID)
HAVING COUNT(*) > 1;

PRINT '=== Legacy / demo-style accounts ===';
SELECT UserID, FullName, EmailID, Role, UserStatus, CreatedDate
FROM dbo.Users
WHERE EmailID LIKE N'%@jtcs.local%'
   OR EmailID LIKE N'%demo%'
   OR FullName LIKE N'%Demo%';

PRINT '=== Administrator accounts ===';
SELECT UserID, FullName, EmailID, Role, UserStatus, CreatedDate
FROM dbo.Users
WHERE Role IN (N'Administrator', N'Admin')
ORDER BY CreatedDate;

PRINT '=== Pending registrations ===';
SELECT UserID, FullName, EmailID, UserStatus, EmailVerified, AdminApproved, CreatedDate
FROM dbo.Users
WHERE UserStatus = N'Pending'
ORDER BY CreatedDate DESC;

PRINT '=== Specific email lookup: itax.haldwani@gmail.com ===';
SELECT UserID, FullName, EmailID, Role, UserStatus, IsActive, EmailVerified, AdminApproved, CreatedDate
FROM dbo.Users
WHERE LOWER(EmailID) = LOWER(N'itax.haldwani@gmail.com');

GO
