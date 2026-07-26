/*
    Remove legacy demo accounts — never recreate these in seed scripts.
*/
SET NOCOUNT ON;

BEGIN TRANSACTION;

DECLARE @DemoEmails TABLE (Email NVARCHAR(254));
INSERT INTO @DemoEmails (Email) VALUES
    (N'manager@jtcs.local'),
    (N'operator@jtcs.local'),
    (N'viewer@jtcs.local');

DELETE FROM dbo.PasswordResetOTP
WHERE UserID IN (SELECT UserID FROM dbo.Users WHERE EmailID IN (SELECT Email FROM @DemoEmails));

DELETE FROM dbo.AuthToken
WHERE UserID IN (SELECT UserID FROM dbo.Users WHERE EmailID IN (SELECT Email FROM @DemoEmails))
   OR Email IN (SELECT Email FROM @DemoEmails);

DELETE FROM dbo.Users
WHERE EmailID IN (SELECT Email FROM @DemoEmails);

DELETE FROM dbo.AuthToken
WHERE Email LIKE N'%@jtcs.local%';

DELETE FROM dbo.Users
WHERE EmailID LIKE N'%@jtcs.local%'
  AND Role IN (N'Admin', N'Administrator', N'Operator', N'Viewer', N'Manager');

IF @@ROWCOUNT > 0
    PRINT 'Removed legacy demo / @jtcs.local user account(s).';
ELSE
    PRINT 'No legacy demo accounts found to remove.';

COMMIT TRANSACTION;
GO
