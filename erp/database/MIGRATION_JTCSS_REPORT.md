# JTCSS Migration Report

- **Started:** 2026-07-05T16:03:45.190535
- **Finished:** 2026-07-05T16:03:46.235022
- **Server:** `JTCS\JTCS`
- **Source database:** `JTCS` (unchanged, read-only)
- **Target database:** `JTCSS`
- **Verified DB_NAME():** `JTCSS`

## Connection String

`mssql+pyodbc:///?odbc_connect=DRIVER%3D%7BODBC+Driver+17+for+SQL+Server%7D%3BSERVER%3DJTCS%5CJTCS%3BDATABASE%3DJTCSS%3BTrusted_Connection%3Dyes%3B`

## Total Tables Created (15)

- `AuthToken`
- `CompanyProfile`
- `CustomerMaster`
- `JtcsBankAccountMaster`
- `JtcsBankTransaction`
- `JTCSDailyTransaction`
- `JTCSDailyTransactionPayment`
- `MenuMaster`
- `PasswordResetOTP`
- `PaymentModeMaster`
- `StampMaster`
- `StampOcrImage`
- `TransactionTypeMaster`
- `Users`
- `WorkTypeMaster`

## Master Data Import

**Total master tables imported:** 8  
**Total master records imported:** 802

| Table | Rows Imported | Status |
|-------|---------------|--------|
| JtcsBankAccountMaster | 6 | OK |
| CustomerMaster | 700 | OK |
| WorkTypeMaster | 5 | OK |
| TransactionTypeMaster | 4 | OK |
| Users | 11 | OK |
| CompanyProfile | 1 | OK |
| PaymentModeMaster | 9 | OK |
| MenuMaster | 66 | OK |

## Transaction Tables (must be empty)

- `JtcsBankTransaction`: **0** rows
- `JTCSDailyTransaction`: **0** rows
- `JTCSDailyTransactionPayment`: **0** rows
- `StampMaster`: **0** rows
- `StampOcrImage`: **0** rows
- `AuthToken`: **0** rows
- `PasswordResetOTP`: **0** rows

## Accounting Rule (permanent)

- Business work → `JTCSDailyTransaction`
- Money movement → `JtcsBankTransaction`
- All modules post through these two tables only
