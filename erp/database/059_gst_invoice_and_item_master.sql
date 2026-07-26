/*
    Item Master + GST Invoice tables
    Accounting menu: remove Journal/Ledger/Trial Balance; add Generate Invoice + Reports
    Masters menu: add Item Master
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.ItemMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ItemMaster (
        ItemID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        ItemCode NVARCHAR(40) NOT NULL,
        ItemName NVARCHAR(200) NOT NULL,
        Description NVARCHAR(500) NULL,
        HsnSac NVARCHAR(20) NULL,
        HsnSacType NVARCHAR(10) NOT NULL CONSTRAINT DF_ItemMaster_HsnSacType DEFAULT (N'SAC'),
        Unit NVARCHAR(30) NOT NULL CONSTRAINT DF_ItemMaster_Unit DEFAULT (N'NOS'),
        DefaultRate DECIMAL(18, 2) NOT NULL CONSTRAINT DF_ItemMaster_DefaultRate DEFAULT (0),
        GstRatePercent DECIMAL(5, 2) NOT NULL CONSTRAINT DF_ItemMaster_GstRate DEFAULT (18),
        OrderNo INT NOT NULL CONSTRAINT DF_ItemMaster_OrderNo DEFAULT (100),
        IsActive BIT NOT NULL CONSTRAINT DF_ItemMaster_IsActive DEFAULT (1),
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_ItemMaster_CreatedAt DEFAULT (SYSUTCDATETIME()),
        UpdatedAt DATETIME2 NULL,
        CONSTRAINT UX_ItemMaster_Code UNIQUE (ItemCode)
    );
END;
GO

IF OBJECT_ID(N'dbo.GstInvoice', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.GstInvoice (
        InvoiceID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        InvoiceNo NVARCHAR(40) NOT NULL,
        InvoiceDate DATE NOT NULL,
        CustomerID INT NULL,
        CustomerName NVARCHAR(200) NOT NULL,
        ContactPerson NVARCHAR(150) NULL,
        BillingAddress NVARCHAR(500) NULL,
        CustomerGSTIN NVARCHAR(20) NULL,
        ContactMobile NVARCHAR(20) NULL,
        ContactEmail NVARCHAR(150) NULL,
        PlaceOfSupply NVARCHAR(100) NULL,
        PlaceOfSupplyCode NVARCHAR(5) NULL,
        ReverseCharge BIT NOT NULL CONSTRAINT DF_GstInvoice_RCM DEFAULT (0),
        TaxType NVARCHAR(10) NOT NULL CONSTRAINT DF_GstInvoice_TaxType DEFAULT (N'IGST'),
        ListPrice DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_ListPrice DEFAULT (0),
        DiscountAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_Discount DEFAULT (0),
        TaxableValue DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_Taxable DEFAULT (0),
        CgstRate DECIMAL(5, 2) NOT NULL CONSTRAINT DF_GstInvoice_CgstRate DEFAULT (0),
        CgstAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_CgstAmt DEFAULT (0),
        SgstRate DECIMAL(5, 2) NOT NULL CONSTRAINT DF_GstInvoice_SgstRate DEFAULT (0),
        SgstAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_SgstAmt DEFAULT (0),
        IgstRate DECIMAL(5, 2) NOT NULL CONSTRAINT DF_GstInvoice_IgstRate DEFAULT (0),
        IgstAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_IgstAmt DEFAULT (0),
        InvoiceValue DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_Value DEFAULT (0),
        AmountInWords NVARCHAR(500) NULL,
        Notes NVARCHAR(500) NULL,
        CreatedBy NVARCHAR(100) NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_GstInvoice_CreatedAt DEFAULT (SYSUTCDATETIME()),
        UpdatedAt DATETIME2 NULL,
        CONSTRAINT UX_GstInvoice_No UNIQUE (InvoiceNo)
    );
END;
GO

IF OBJECT_ID(N'dbo.GstInvoiceLine', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.GstInvoiceLine (
        LineID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        InvoiceID INT NOT NULL,
        SrNo INT NOT NULL,
        ItemID INT NULL,
        Particulars NVARCHAR(300) NOT NULL,
        HsnSac NVARCHAR(20) NULL,
        Unit NVARCHAR(30) NULL,
        Qty DECIMAL(18, 3) NOT NULL CONSTRAINT DF_GstInvoiceLine_Qty DEFAULT (1),
        Rate DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoiceLine_Rate DEFAULT (0),
        DiscountAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoiceLine_Discount DEFAULT (0),
        TaxableValue DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoiceLine_Taxable DEFAULT (0),
        GstRatePercent DECIMAL(5, 2) NOT NULL CONSTRAINT DF_GstInvoiceLine_GstRate DEFAULT (0),
        CONSTRAINT FK_GstInvoiceLine_Invoice FOREIGN KEY (InvoiceID)
            REFERENCES dbo.GstInvoice (InvoiceID) ON DELETE CASCADE
    );
    CREATE INDEX IX_GstInvoiceLine_InvoiceID ON dbo.GstInvoiceLine (InvoiceID);
END;
GO

DECLARE @AccountingID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster
    WHERE MenuName = N'Accounting' AND ParentMenuID IS NULL ORDER BY MenuID
);

IF @AccountingID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET IsActive = 0
    WHERE ParentMenuID = @AccountingID
      AND MenuName IN (N'Journal Entry', N'Ledger View', N'Trial Balance');

    IF EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @AccountingID AND MenuName = N'Generate Invoice'
    )
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/accounting/invoice',
            MenuIcon = N'bi-receipt',
            DisplayOrder = 1,
            Description = N'Generate GST tax invoice',
            IsActive = 1
        WHERE ParentMenuID = @AccountingID AND MenuName = N'Generate Invoice';
    ELSE
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
        )
        VALUES (
            @AccountingID, N'Generate Invoice', N'bi-receipt', N'/accounting/invoice',
            1, N'Generate GST tax invoice', 1, NULL
        );

    IF EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @AccountingID AND MenuName = N'Reports'
    )
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/accounting/reports',
            MenuIcon = N'bi-bar-chart-line',
            DisplayOrder = 2,
            Description = N'Accounting invoice reports',
            IsActive = 1
        WHERE ParentMenuID = @AccountingID AND MenuName = N'Reports';
    ELSE
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
        )
        VALUES (
            @AccountingID, N'Reports', N'bi-bar-chart-line', N'/accounting/reports',
            2, N'Accounting invoice reports', 1, NULL
        );
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster
    WHERE MenuName = N'Masters' AND ParentMenuID IS NULL ORDER BY MenuID
);

IF @MastersID IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @MastersID AND MenuName = N'Item Master'
    )
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/masters/item',
            MenuIcon = N'bi-box-seam',
            DisplayOrder = 19,
            Description = N'GST item master (HSN/SAC, rates)',
            IsActive = 1
        WHERE ParentMenuID = @MastersID AND MenuName = N'Item Master';
    ELSE
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
        )
        VALUES (
            @MastersID, N'Item Master', N'bi-box-seam', N'/masters/item',
            19, N'GST item master (HSN/SAC, rates)', 1, NULL
        );
END;
GO

PRINT '059_gst_invoice_and_item_master.sql completed.';
GO
