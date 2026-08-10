/*
    GST Followup — merge GSTR-1 Filed + GSTR-3B Filed into single "Return Filed"
    Idempotent. Does not alter ITR / DSC / TDS stages.
*/
SET NOCOUNT ON;
GO

DECLARE @ReturnFiledID INT;
DECLARE @OldGstr1ID INT;
DECLARE @OldGstr3bID INT;

SELECT TOP 1 @ReturnFiledID = StageID
FROM dbo.FollowupWorkflowStage
WHERE ModuleCode = N'GST' AND StageCode = N'return_filed'
ORDER BY StageID;

SELECT TOP 1 @OldGstr1ID = StageID
FROM dbo.FollowupWorkflowStage
WHERE ModuleCode = N'GST' AND StageCode = N'gstr1_filed'
ORDER BY StageID;

SELECT TOP 1 @OldGstr3bID = StageID
FROM dbo.FollowupWorkflowStage
WHERE ModuleCode = N'GST' AND StageCode = N'gstr3b_filed'
ORDER BY StageID;

IF @ReturnFiledID IS NULL
BEGIN
    INSERT INTO dbo.FollowupWorkflowStage (
        ModuleCode, StageCode, StageName, DisplayOrder, ActiveStatus
    )
    VALUES (N'GST', N'return_filed', N'Return Filed', 2, 1);
    SET @ReturnFiledID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.FollowupWorkflowStage
    SET StageName = N'Return Filed',
        DisplayOrder = 2,
        ActiveStatus = 1
    WHERE StageID = @ReturnFiledID;
END;

-- Entries that had either old filed stage → ensure Return Filed is linked.
IF @ReturnFiledID IS NOT NULL AND (@OldGstr1ID IS NOT NULL OR @OldGstr3bID IS NOT NULL)
BEGIN
    ;WITH migrated AS (
        SELECT
            es.EntryID,
            MAX(es.CompletedDate) AS CompletedDate
        FROM dbo.FollowupEntryStage es
        WHERE es.StageID IN (@OldGstr1ID, @OldGstr3bID)
        GROUP BY es.EntryID
    )
    INSERT INTO dbo.FollowupEntryStage (EntryID, StageID, CompletedDate)
    SELECT m.EntryID, @ReturnFiledID, m.CompletedDate
    FROM migrated m
    WHERE NOT EXISTS (
        SELECT 1
        FROM dbo.FollowupEntryStage x
        WHERE x.EntryID = m.EntryID
          AND x.StageID = @ReturnFiledID
    );
END;

-- Drop old stage links from entries.
IF @OldGstr1ID IS NOT NULL OR @OldGstr3bID IS NOT NULL
BEGIN
    DELETE FROM dbo.FollowupEntryStage
    WHERE StageID IN (@OldGstr1ID, @OldGstr3bID);
END;

-- Deactivate legacy stages (keep rows for history / safety).
UPDATE dbo.FollowupWorkflowStage
SET ActiveStatus = 0,
    StageName = CASE StageCode
        WHEN N'gstr1_filed' THEN N'GSTR-1 Filed (merged)'
        WHEN N'gstr3b_filed' THEN N'GSTR-3B Filed (merged)'
        ELSE StageName
    END
WHERE ModuleCode = N'GST'
  AND StageCode IN (N'gstr1_filed', N'gstr3b_filed');

-- Normalize active GST stage order.
UPDATE dbo.FollowupWorkflowStage SET DisplayOrder = 1, ActiveStatus = 1
WHERE ModuleCode = N'GST' AND StageCode = N'documents_received';

UPDATE dbo.FollowupWorkflowStage SET DisplayOrder = 2, ActiveStatus = 1
WHERE ModuleCode = N'GST' AND StageCode = N'return_filed';

UPDATE dbo.FollowupWorkflowStage SET DisplayOrder = 3, ActiveStatus = 1
WHERE ModuleCode = N'GST' AND StageCode = N'tally_bill_generated';

UPDATE dbo.FollowupWorkflowStage SET DisplayOrder = 4, ActiveStatus = 1
WHERE ModuleCode = N'GST' AND StageCode = N'payment_received';

PRINT '098_gst_followup_return_filed.sql completed.';
GO
