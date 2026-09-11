"""JTCS ERP Help catalog — documentation only. Does not change business calculations."""

from __future__ import annotations

from dataclasses import dataclass


GROUPS: tuple[tuple[str, str, str], ...] = (
    ("start", "Getting started", "bi-compass"),
    ("dashboard", "Dashboard", "bi-speedometer2"),
    ("activities", "Activities", "bi-lightning-charge"),
    ("reports", "Reports and Analysis", "bi-graph-up"),
    ("statements", "Financial statements", "bi-journal-richtext"),
    ("masters", "Masters", "bi-database"),
    ("accounting", "Accounting", "bi-journal-bookmark"),
    ("crm", "CRM", "bi-people"),
    ("public", "Public Report", "bi-postcard"),
    ("hr", "HR", "bi-person-badge"),
    ("admin", "Admin Role", "bi-archive"),
)


@dataclass(frozen=True)
class HelpStep:
    title: str
    body: str


@dataclass(frozen=True)
class HelpFormula:
    name: str
    expression: str
    note: str = ""


@dataclass(frozen=True)
class HelpShot:
    caption: str
    title: str
    ribbon: tuple[str, ...] = ()
    fields: tuple[tuple[str, str], ...] = ()
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    highlights: tuple[str, ...] = ()
    image: str | None = None


@dataclass(frozen=True)
class HelpTopic:
    slug: str
    title: str
    icon: str
    group: str
    menu_path: str
    summary: str
    open_url: str | None = None
    audience: str = "All signed-in users"
    steps: tuple[HelpStep, ...] = ()
    shots: tuple[HelpShot, ...] = ()
    formulas: tuple[HelpFormula, ...] = ()
    tips: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    keywords: str = ""


def _s(title: str, body: str) -> HelpStep:
    return HelpStep(title, body)


def _f(name: str, expression: str, note: str = "") -> HelpFormula:
    return HelpFormula(name, expression, note)


def _shot(
    caption: str,
    title: str,
    *,
    ribbon: tuple[str, ...] = (),
    fields: tuple[tuple[str, str], ...] = (),
    columns: tuple[str, ...] = (),
    rows: tuple[tuple[str, ...], ...] = (),
    highlights: tuple[str, ...] = (),
    image: str | None = None,
) -> HelpShot:
    return HelpShot(
        caption=caption,
        title=title,
        ribbon=ribbon,
        fields=fields,
        columns=columns,
        rows=rows,
        highlights=highlights,
        image=image,
    )


def _t(
    slug: str,
    title: str,
    icon: str,
    group: str,
    menu_path: str,
    summary: str,
    *,
    url: str | None = None,
    audience: str = "All signed-in users",
    steps: tuple[HelpStep, ...] = (),
    shots: tuple[HelpShot, ...] = (),
    formulas: tuple[HelpFormula, ...] = (),
    tips: tuple[str, ...] = (),
    related: tuple[str, ...] = (),
    keywords: str = "",
) -> HelpTopic:
    return HelpTopic(
        slug=slug,
        title=title,
        icon=icon,
        group=group,
        menu_path=menu_path,
        summary=summary,
        open_url=url,
        audience=audience,
        steps=steps,
        shots=shots,
        formulas=formulas,
        tips=tips,
        related=related,
        keywords=keywords or f"{title} {menu_path} {summary}",
    )


# ---------------------------------------------------------------------------
# Topics — one article per ribbon menu / calculation family
# ---------------------------------------------------------------------------

TOPICS: tuple[HelpTopic, ...] = (
    _t(
        "using-help",
        "How to use Help",
        "bi-question-circle",
        "start",
        "Admin Role → Help",
        "Help is available to every signed-in user. Each topic matches a ribbon menu and explains the screen, the working steps, and the calculations used on that screen.",
        url="/help",
        steps=(
            _s("Open Help", "Choose Admin Role in the top ribbon, then Help. The same library opens at /help."),
            _s("Find a topic", "Use the search box on the left, or browse by module (Activities, Reports, Masters, and so on)."),
            _s("Follow the figures", "Each article shows illustrated screen frames (Figure 1, Figure 2…). Drop a PNG named {slug}-1.png into static/img/help/ to replace a frame with a live screenshot."),
            _s("Open the live screen", "Use Open this screen at the top of an article to jump to the real module without leaving the documented path."),
        ),
        shots=(
            _shot(
                "Figure 1 — Help home with module groups and search",
                "JTCS Help",
                ribbon=("Admin Role", "Help"),
                fields=(("Search", "ledger closing balance"),),
                columns=("Topic", "Menu"),
                rows=(
                    ("Ledger Report", "Reports and Analysis"),
                    ("Balance Sheet", "Financial Statements"),
                    ("Stamp Activity", "Activities"),
                ),
                highlights=("Search finds menus and formulas", "Every ribbon item has a topic"),
            ),
        ),
        tips=(
            "Help never changes invoices, ledgers, or reports — it only documents them.",
            "Administrator tools in Admin Role stay hidden from non-admin users; Help remains visible.",
        ),
        related=("ribbon-navigation", "calculations-index"),
    ),
    _t(
        "ribbon-navigation",
        "Ribbon, menus, and roles",
        "bi-menu-button-wide",
        "start",
        "Top ribbon",
        "The green/blue bar under the company header is the main menu. Hover a name to open its children. Your role decides which items appear — except Help, which is granted to all signed-in users.",
        url="/dashboard",
        steps=(
            _s("Top-level modules", "Typical ribbon: Admin Role, Dashboard, Activities, Reports and Analysis, Masters, Accounting, CRM, Public Report, HR."),
            _s("Admin Role", "Administrators see backups, users, utility, and other tools. Every user still sees Help here."),
            _s("Hidden legacy modules", "Old top menus such as ITR, GST, TDS, Payroll, and Stock are kept out of the ribbon. Their work now lives under Activities, Followup, or Reports."),
        ),
        shots=(
            _shot(
                "Figure 1 — Top ribbon with Admin Role flyout showing Help",
                "JTCS ERP",
                ribbon=("Admin Role", "Dashboard", "Activities", "Reports and Analysis", "Masters"),
                columns=("Admin Role", ""),
                rows=(("Help", "All users"), ("Data Backup", "Admin / Manager / Operator / Viewer"), ("Users", "Administrator")),
                highlights=("Help is first under Admin Role", "Other admin tools stay role-restricted"),
            ),
        ),
        related=("using-help", "dashboard"),
        keywords="menu ribbon navigation admin role roles",
    ),
    _t(
        "signing-in",
        "Sign in and server authentication",
        "bi-box-arrow-in-right",
        "start",
        "Sign in",
        "Staff sign in with a user id and password. Some deployments also require Server User authentication before the ERP workspace opens.",
        url="/auth/login",
        steps=(
            _s("Application login", "Enter user id and password on the sign-in page. Use Forgot password / Forgot user id if your administrator enabled email OTP."),
            _s("Server User gate", "If the server gate appears, complete Server User authentication. This protects the database host, not the ERP menu rights."),
            _s("Customer portal", "Clients use a separate /customer login. That portal is not the staff ribbon."),
        ),
        shots=(
            _shot(
                "Figure 1 — Staff sign-in card",
                "Sign in",
                fields=(("User ID", "operator01"), ("Password", "••••••••")),
                highlights=("Use Forgot password for OTP reset", "Server User is a second gate on some PCs"),
            ),
        ),
        related=("using-help", "users-admin"),
    ),
    _t(
        "dashboard",
        "Dashboard",
        "bi-speedometer2",
        "dashboard",
        "Dashboard",
        "The home workspace summarises today's cash and bank activity, recent daily transactions, and health alerts. Cards open the related ledger or activity without posting new entries.",
        url="/dashboard",
        steps=(
            _s("Read Today's Activity", "The top card shows today's transaction count with Cash and Bank figures from recent daily transactions."),
            _s("Open a metric", "Click Cash or Bank on the today card to inspect the underlying rows."),
            _s("Watch health banners", "System Health or Integration Health banners appear only when a check fails. Administrators follow the link to Mission Control or Integration Settings."),
        ),
        shots=(
            _shot(
                "Figure 1 — Dashboard today summary and cash / bank metrics",
                "Dashboard",
                ribbon=("Dashboard",),
                fields=(("System date", "09 Sep 2026"), ("Today's txns", "12")),
                columns=("Metric", "Amount"),
                rows=(("Cash", "1,25,000.00"), ("Bank", "8,40,220.50")),
                highlights=("Figures are summaries, not a posting screen", "Click a metric to view detail"),
            ),
        ),
        formulas=(
            _f("Bank / cash running", "Asset books: Opening + Debit − Credit. Liability / OD books: Opening + Credit − Debit."),
        ),
        related=("ledger-report", "bank-cash-transactions", "calculations-index"),
        keywords="dashboard cash bank today activity",
    ),
    _t(
        "stamp-activity",
        "Stamp Activity",
        "bi-file-earmark-ruled",
        "activities",
        "Activities → Stamp Activity",
        "Uttarakhand e-Stamp working screen: mobile gate, certificate capture (manual or OCR), duty vs sale amounts, payment mode, and the period summary.",
        url="/shcil/stamp-activity",
        steps=(
            _s("Start with mobile", "Enter the 10-digit mobile and Continue. The gate identifies the customer before certificate entry."),
            _s("Capture the certificate", "Enter certificate number, certificate date, stamp duty, and sale amount — or use OCR where enabled."),
            _s("Complete the sale line", "Set transaction date, customer, payment mode, and save. Daily # is assigned by the activity."),
            _s("Read Period Summary", "The panel above the grid totals duty and sale for the selected period. It does not post a second voucher."),
        ),
        shots=(
            _shot(
                "Figure 1 — Mobile gate and period summary",
                "Stamp Activity",
                ribbon=("Activities", "Stamp Activity"),
                fields=(("Mobile", "9876543210"), ("Period", "This month")),
                columns=("Duty ₹", "Sale ₹", "Certificates"),
                rows=(("2,40,000.00", "2,52,000.00", "18"),),
                highlights=("Mobile is required before entry", "Period summary follows saved rows"),
            ),
            _shot(
                "Figure 2 — Certificate grid after save",
                "Stamp Activity Records",
                columns=("Certificate", "Cert Date", "Duty ₹", "Sale ₹", "Customer", "Payment"),
                rows=(
                    ("UK123456", "09-09-2026", "10,000.00", "10,500.00", "Sharma", "UPI"),
                    ("UK123457", "09-09-2026", "5,000.00", "5,250.00", "Verma", "Cash"),
                ),
                highlights=("Duty is stamp duty; Sale is the billed amount", "Sort any column from the header"),
            ),
        ),
        formulas=(
            _f("Stamp line", "Each row stores Stamp duty amount and Sale amount separately."),
            _f("Period totals", "Sum of duty and sum of sale for rows in the selected period (not a ledger running balance)."),
        ),
        tips=("Use Stamp Exception under Reports to reconcile SHCIL certificates against activity.",),
        related=("stamp-reports", "stamp-exception", "ecourt-activity"),
        keywords="stamp estamp shcil certificate duty sale ocr",
    ),
    _t(
        "ecourt-activity",
        "eCourt Activity",
        "bi-file-earmark-text",
        "activities",
        "Activities → eCourt Activity",
        "SHCIL e-Court fee receipts: import or enter stationery sales, match receipt numbers, and review exceptions.",
        url="/shcil/ecourt-activity",
        steps=(
            _s("Open the activity", "Activities → eCourt Activity."),
            _s("Import or enter receipts", "Load the SHCIL receipt file or key a stationery sale. Receipt number must stay unique."),
            _s("Check stationery", "Confirm the stationery number and sale amount before save."),
            _s("Exceptions", "Unmatched or duplicate receipts appear on e-Court Exception under Reports and Analysis."),
        ),
        shots=(
            _shot(
                "Figure 1 — e-Court receipt working grid",
                "eCourt Activity",
                ribbon=("Activities", "eCourt Activity"),
                columns=("Receipt No", "Date", "Stationery", "Amount", "Status"),
                rows=(("EC-90811", "09-09-2026", "ST-441", "120.00", "Matched"),),
                highlights=("Receipt number is unique", "Exceptions are reviewed on the report, not here"),
            ),
        ),
        related=("ecourt-exception", "stamp-activity"),
        keywords="ecourt e-court stationery shcil receipt",
    ),
    _t(
        "itr-followup",
        "ITR Followup",
        "bi-list-check",
        "activities",
        "Activities → ITR Followup",
        "Track Income-tax return work by customer and tax period: documents, filing, Tally bill, and payment stages.",
        url="/itr/followup",
        steps=(
            _s("Select period and customer", "Set work date, tax period (assessment year), and customer (PAN is taken from Customer Master)."),
            _s("Advance stages", "Mark Documents Received → ITR Filed → Tally Bill Generated → Payment Received. Unverified holds a reason."),
            _s("Billing", "When Tally bill is generated, bill number and date feed customer outstanding and ledgers."),
        ),
        shots=(
            _shot(
                "Figure 1 — ITR followup grid with workflow stages",
                "ITR Followup",
                ribbon=("Activities", "ITR Followup"),
                fields=(("Tax period", "AY 2026-27"), ("Customer", "Sharma Enterprises")),
                columns=("Customer", "Return", "Stage", "Bill No"),
                rows=(("Sharma Enterprises", "ITR-3", "ITR Filed", "—"),),
                highlights=("Stages come from Followup Master", "Bill links to customer ledger"),
            ),
        ),
        formulas=(
            _f("Customer billed", "Followup bills add to the customer's billed total used in outstanding and ledger closing."),
        ),
        related=("followup-masters", "gst-followup", "customer-master", "outstanding"),
        keywords="itr followup income tax filing tally bill",
    ),
    _t(
        "dsc-followup",
        "DSC Followup",
        "bi-shield-check",
        "activities",
        "Activities → DSC Followup",
        "Digital Signature Certificate pipeline: documents, application, KYC, download, bill, and payment. IDSign status can be synced where configured.",
        url="/dsc/followup",
        steps=(
            _s("Create the entry", "Choose customer, tax/work period, and DSC type (new or renewal)."),
            _s("Walk the stages", "Documents → Application → KYC → Download Status → Tally Bill → Payment."),
            _s("Sync download (optional)", "Use sync-status where IDSign integration is enabled."),
        ),
        shots=(
            _shot(
                "Figure 1 — DSC followup stages",
                "DSC Followup",
                ribbon=("Activities", "DSC Followup"),
                columns=("Customer", "KYC", "Download", "Bill"),
                rows=(("Verma & Co", "Done", "Pending", "—"),),
            ),
        ),
        related=("gst-followup", "followup-masters", "dsc-orders"),
        keywords="dsc digital signature kyc idsign",
    ),
    _t(
        "gst-followup",
        "GST Followup",
        "bi-receipt",
        "activities",
        "Activities → GST Followup",
        "GST return work by tax period: documents received, return filed, Tally bill, payment.",
        url="/gst/followup",
        steps=(
            _s("Choose tax period", "Use the GST period (month/quarter) required for that customer."),
            _s("Mark Return Filed", "After the portal filing, mark the stage so the grid reflects completion."),
            _s("Bill and collect", "Tally Bill Generated and Payment Received update customer outstanding."),
        ),
        shots=(
            _shot(
                "Figure 1 — GST followup by period",
                "GST Followup",
                fields=(("Tax period", "Aug-2026"),),
                columns=("Customer", "Return", "Stage"),
                rows=(("ABC Traders", "GSTR-1", "Return Filed"),),
            ),
        ),
        related=("itr-followup", "tds-followup", "invoices"),
        keywords="gst gstr followup return",
    ),
    _t(
        "tds-followup",
        "TDS Followup",
        "bi-percent",
        "activities",
        "Activities → TDS Followup",
        "TDS return and payment followup. Customer create-on-the-fly is not used on this module — pick an existing customer.",
        url="/tds/followup",
        steps=(
            _s("Select form and quarter", "Use the TDS form/quarter fields on the entry."),
            _s("Complete KYC and bill stages", "Documents → KYC → Tally Bill → Payment."),
        ),
        shots=(
            _shot(
                "Figure 1 — TDS followup",
                "TDS Followup",
                columns=("Customer", "Form", "Quarter", "Stage"),
                rows=(("XYZ Pvt Ltd", "24Q", "Q1", "Documents Received"),),
            ),
        ),
        related=("gst-followup", "followup-masters"),
        keywords="tds 24q 26q followup",
    ),
    _t(
        "income-expense",
        "Income / Expense activity",
        "bi-cash-stack",
        "activities",
        "Activities → Income / Expense",
        "Day-to-day other income and expense vouchers with work/category heads, bank or cash, and (for miscellaneous work) a short workflow: Work Done → Tally Bill → Payment.",
        url="/others/income-expense",
        steps=(
            _s("Choose income or expense", "The same screen posts both directions using Work/Category Master heads."),
            _s("Enter the voucher", "Work date, head, amount, bank/cash, and remarks. Multi-line detail is available where configured."),
            _s("Misc. workflow", "For miscellaneous jobs, tick Work Done, then Tally Bill Generated, then Payment."),
        ),
        shots=(
            _shot(
                "Figure 1 — Income / Expense voucher",
                "Income / Expense",
                ribbon=("Activities", "Income / Expense"),
                fields=(("Type", "Income"), ("Head", "Consultancy"), ("Amount", "15,000.00"), ("Mode", "Bank")),
                highlights=("Heads come from Work/Category Master", "Amount posts to bank/cash and P&L heads"),
            ),
        ),
        formulas=(
            _f("Income voucher", "Increases the income head and the selected bank/cash book."),
            _f("Expense voucher", "Increases the expense head and decreases the selected bank/cash book."),
        ),
        related=("work-category-master", "printing-scanning", "profit-loss"),
        keywords="income expense others voucher work category",
    ),
    _t(
        "printing-scanning",
        "Printing and Scanning",
        "bi-printer",
        "activities",
        "Activities → Printing and Scanning",
        "Income and expense activity for printing/scanning jobs, billed against Printing Scan master bill numbers.",
        url="/others/income/printing-scanning",
        steps=(
            _s("Open income or expense path", "Use the Printing and Scanning activity under Activities (income and expense are separate URLs)."),
            _s("Enter bill and work", "Bill number is unique. Choose work head, date, and amount."),
        ),
        shots=(
            _shot(
                "Figure 1 — Printing / scanning bill",
                "Printing and Scanning",
                fields=(("Bill No", "PS-1022"), ("Work", "Colour print"), ("Amount", "850.00")),
            ),
        ),
        related=("income-expense", "work-category-master"),
        keywords="printing scanning photocopy bill",
    ),
    _t(
        "bank-cash-transactions",
        "Bank / Cash transactions (contra)",
        "bi-arrow-left-right",
        "activities",
        "Activities → Bank / Cash",
        "Contra between two bank or cash accounts: one account is credited (money out) and the other is debited (money in) for the same amount.",
        url="/others/bank-cash-transactions",
        steps=(
            _s("New contra", "Pick work date, purpose, credit account (source), debit account (destination), and amount. Accounts must differ."),
            _s("Save", "The system writes a paired bank transaction (out + in) and a voucher number."),
        ),
        shots=(
            _shot(
                "Figure 1 — Contra voucher",
                "Bank / Cash Transactions",
                ribbon=("Activities", "Bank / Cash"),
                fields=(
                    ("Credit (from)", "HDFC Current"),
                    ("Debit (to)", "Cash"),
                    ("Amount", "25,000.00"),
                    ("Purpose", "Cash withdrawal"),
                ),
                highlights=("Same amount on both legs", "Does not affect P&L — only books of account"),
            ),
        ),
        formulas=(
            _f("Contra", "Amount(out) = Amount(in). Source book credit; destination book debit."),
        ),
        related=("bank-master", "ledger-report", "cash-book"),
        keywords="contra bank cash transfer voucher",
    ),
    _t(
        "reports-hub",
        "Reports hub",
        "bi-file-earmark-bar-graph",
        "reports",
        "Reports and Analysis",
        "Operational reports (collection, cash/bank book, stamp, outstanding) live under Reports and Analysis together with Ledger Report and Financial Statements.",
        url="/reports/",
        steps=(
            _s("Pick a report card", "Open Reports and Analysis or /reports/ and choose a card."),
            _s("Set the date filter", "Most reports use From / To (or start/end). Totals always follow that range."),
        ),
        shots=(
            _shot(
                "Figure 1 — Report cards",
                "Reports",
                ribbon=("Reports and Analysis",),
                columns=("Report", "Use"),
                rows=(
                    ("Daily Collection", "Debit receipts by date"),
                    ("Stamp Collection", "SHCIL wallet movement"),
                    ("Outstanding", "Customer balances"),
                ),
            ),
        ),
        related=("ledger-report", "financial-statements", "stamp-reports"),
        keywords="reports hub collection cash book",
    ),
    _t(
        "daily-collection",
        "Daily Collection",
        "bi-calendar-day",
        "reports",
        "Reports and Analysis → Daily Collection",
        "Day-wise total of bank/cash receipts (debit amounts greater than zero) in the filter period.",
        url="/reports/daily-collection",
        steps=(
            _s("Set dates", "Choose start and end date, then view or print."),
        ),
        formulas=(
            _f("Daily collection", "For each date: SUM(Debit) where Debit > 0 on JtcsBankTransaction."),
        ),
        related=("cash-book", "payment-mode"),
        keywords="daily collection receipts",
    ),
    _t(
        "cash-book",
        "Cash Book",
        "bi-cash",
        "reports",
        "Reports and Analysis → Cash Book",
        "Cash-account movements in the date range, built from bank transactions flagged as cash.",
        url="/reports/cash-book",
        formulas=(
            _f("Cash closing", "Opening (cash book) + period Debit − period Credit for cash accounts."),
        ),
        related=("bank-book", "ledger-report"),
        keywords="cash book",
    ),
    _t(
        "bank-book",
        "Bank Book",
        "bi-bank",
        "reports",
        "Reports and Analysis → Bank Book",
        "Bank-account movements in the date range.",
        url="/reports/bank-book",
        formulas=(
            _f("Bank closing (asset)", "Opening + Debit − Credit."),
            _f("Bank OD / liability", "Opening + Credit − Debit."),
        ),
        related=("cash-book", "ledger-report", "calculations-index"),
        keywords="bank book od",
    ),
    _t(
        "income-report",
        "Income Report",
        "bi-graph-up-arrow",
        "reports",
        "Reports and Analysis → Income Report",
        "Income totals grouped by work type / category for the selected dates.",
        url="/reports/income",
        related=("expense-report", "work-wise", "profit-loss"),
        keywords="income report work type",
    ),
    _t(
        "expense-report",
        "Expense Report",
        "bi-graph-down-arrow",
        "reports",
        "Reports and Analysis → Expense Report",
        "Expense totals grouped by work type / category for the selected dates.",
        url="/reports/expense",
        related=("income-report", "profit-loss"),
        keywords="expense report",
    ),
    _t(
        "work-wise",
        "Work Wise Report",
        "bi-diagram-3",
        "reports",
        "Reports and Analysis → Work Wise Report",
        "Combined income/expense totals by work head.",
        url="/reports/work-wise",
        related=("income-report", "work-category-master"),
        keywords="work wise report",
    ),
    _t(
        "customer-ledger-report",
        "Customer Ledger (report)",
        "bi-person-lines-fill",
        "reports",
        "Reports and Analysis → Customer Ledger",
        "Customer-wise billed vs received for the filter period. For the full Tally-style ledger preview use Ledger Report.",
        url="/reports/customer-ledger",
        formulas=(
            _f("Customer closing", "Opening + billed (debit) − received (credit) in the period."),
        ),
        related=("ledger-report", "outstanding", "customer-master"),
        keywords="customer ledger outstanding billed received",
    ),
    _t(
        "payment-mode",
        "Payment Mode Report",
        "bi-wallet2",
        "reports",
        "Reports and Analysis → Payment Mode",
        "Receipts grouped by payment mode (cash, UPI, bank, etc.).",
        url="/reports/payment-mode",
        related=("daily-collection", "stamp-reports"),
        keywords="payment mode upi cash",
    ),
    _t(
        "cash-flow-report",
        "Cash Flow (operational report)",
        "bi-currency-exchange",
        "reports",
        "Reports and Analysis → Cash Flow",
        "Operational cash movement summary for the date range. The Tally-style Cash Flow statement is a separate Financial Statements report.",
        url="/reports/cash-flow",
        related=("cash-flow-fs", "bank-balance"),
        keywords="cash flow report",
    ),
    _t(
        "bank-balance",
        "Bank Balance",
        "bi-piggy-bank",
        "reports",
        "Reports and Analysis → Bank Balance",
        "Snapshot of book balances per bank account as at the filter end date.",
        url="/reports/bank-balance",
        formulas=(
            _f("Balance as at To date", "Opening (as on opening-balance date) + movements from that date through To date."),
        ),
        related=("ledger-report", "bank-master"),
        keywords="bank balance snapshot",
    ),
    _t(
        "outstanding",
        "Outstanding",
        "bi-exclamation-circle",
        "reports",
        "Reports and Analysis → Outstanding",
        "Customer balances still due: billed less received, including followup bills and opening balances.",
        url="/reports/outstanding",
        formulas=(
            _f("Outstanding", "Customer opening + billed (invoices / followup bills) − receipts."),
        ),
        related=("customer-ledger-report", "invoices", "itr-followup"),
        keywords="outstanding receivable",
    ),
    _t(
        "stamp-reports",
        "Stamp reports",
        "bi-postage",
        "reports",
        "Reports and Analysis → Stamp reports",
        "Stamp Register, Daily Stamp Sale, Stamp Collection, customer-wise, certificate-wise, date-wise, and payment-mode stamp reports all read Stamp Activity rows.",
        url="/reports/stamp-collection",
        steps=(
            _s("Stamp Collection", "Shows SHCIL wallet movement. Opening balance can be saved on that screen (opening date + amount)."),
            _s("Daily Stamp Sale", "Certificates sold by day with duty and sale totals."),
            _s("Certificate / customer / date / payment", "The same activity rows sliced by that dimension."),
        ),
        shots=(
            _shot(
                "Figure 1 — Stamp Collection opening and period movement",
                "Stamp Collection",
                fields=(("Opening balance", "50,000.00"), ("Opening date", "01-04-2026")),
                columns=("Receipts", "Sales", "Closing"),
                rows=(("1,20,000.00", "95,000.00", "75,000.00"),),
                highlights=("Save opening on this report only", "Sales come from Stamp Activity"),
            ),
        ),
        formulas=(
            _f("Stamp collection closing", "Opening (as on opening date) + receipts into the SHCIL wallet − stamp sales in the period."),
        ),
        related=("stamp-activity", "stamp-exception"),
        keywords="stamp collection register daily sale certificate",
    ),
    _t(
        "stamp-exception",
        "Stamp Exception",
        "bi-file-earmark-spreadsheet",
        "reports",
        "Reports and Analysis → Stamp Exception",
        "Reconcile SHCIL stamp certificates against Stamp Activity. Import the certificate file and review unmatched rows.",
        url="/exceptional-report/stamp-certificate",
        steps=(
            _s("Import the SHCIL file", "Upload the certificate extract."),
            _s("Review exceptions", "Certificates missing in activity (or duplicates) are listed for correction on Stamp Activity."),
        ),
        shots=(
            _shot(
                "Figure 1 — Certificate reconciliation",
                "Stamp Exception",
                columns=("Certificate", "SHCIL duty", "Activity", "Status"),
                rows=(("UK123456", "10,000.00", "10,000.00", "Matched"), ("UK000111", "2,000.00", "—", "Missing")),
            ),
        ),
        related=("stamp-activity", "ecourt-exception"),
        keywords="stamp exception reconciliation shcil",
    ),
    _t(
        "ecourt-exception",
        "e-Court Exception",
        "bi-journal-check",
        "reports",
        "Reports and Analysis → e-Court Exception",
        "Exception list for e-Court receipts that did not match stationery sales.",
        url="/exceptional-report/ecourt-exception",
        related=("ecourt-activity", "stamp-exception"),
        keywords="ecourt exception",
    ),
    _t(
        "ledger-report",
        "Ledger Report",
        "bi-journal-text",
        "reports",
        "Reports and Analysis → Ledger Report",
        "Search and preview bank, customer, work/category, and item ledgers. Apply From / To, then Refresh. Preview, PDF, and Excel share the same figures.",
        url="/Reports_and_analysis/ledger_report",
        steps=(
            _s("Search the ledger", "Type a bank, customer, item, or account name. Select the row."),
            _s("Set From and To", "The grid lists transactions in that window. Click Refresh after changing dates."),
            _s("Read the footer", "Total Credit and Total Debit are the sum of transactions in the From–To window. Closing Balance is the book balance as of To Date (opening plus all movements through To Date)."),
        ),
        shots=(
            _shot(
                "Figure 1 — Ledger preview footer after a date filter",
                "Ledger Preview — HDFC Current",
                ribbon=("Reports and Analysis", "Ledger Report"),
                fields=(("From", "01-04-2026"), ("To", "09-09-2026")),
                columns=("Date", "Particulars", "Debit", "Credit", "Balance"),
                rows=(
                    ("01-04-2026", "Opening", "", "", "2,00,000.00 Dr"),
                    ("09-09-2026", "Receipt Sharma", "15,000.00", "", "2,15,000.00 Dr"),
                    ("09-09-2026", "Contra to Cash", "", "25,000.00", "1,90,000.00 Dr"),
                ),
                highlights=(
                    "Total Debit / Total Credit = period transaction sums only",
                    "Closing Balance as of To Date includes opening",
                ),
            ),
        ),
        formulas=(
            _f("Total Debit (period)", "Sum of debit amounts of transactions with date from From Date through To Date (not opening)."),
            _f("Total Credit (period)", "Sum of credit amounts of transactions in the same From–To window (not opening)."),
            _f("Closing Balance as of To Date", "Running book balance on To Date: opening as at the ledger opening date + all movements dated on or before To Date."),
            _f("Asset / expense / customer running", "Balance = Opening + Debit − Credit."),
            _f("Liability / income / bank OD running", "Balance = Opening + Credit − Debit."),
        ),
        tips=(
            "Changing From/To and pressing Refresh recalculates period totals and closing.",
            "This screen does not post entries; it only previews books.",
        ),
        related=("financial-statements", "calculations-index", "bank-master"),
        keywords="ledger preview total credit total debit closing balance from to",
    ),
    _t(
        "financial-statements",
        "Financial Statements",
        "bi-journal-richtext",
        "statements",
        "Reports and Analysis → Financial Statements",
        "Tally-style statements: Balance Sheet, Profit & Loss, Trial Balance, Trading Account, Cash Flow, Fund Flow, Depreciation Chart, Schedule of Fixed Assets, and Ratio Analysis. All share one From / To filter.",
        url="/Reports_and_analysis/financial-statements",
        steps=(
            _s("Open the hub", "Reports and Analysis → Financial Statements. The left list switches reports without leaving the page."),
            _s("Set From and To", "From is the period start (also used as opening cut-off). To is the closing date. Click Refresh."),
            _s("Horizontal or Vertical", "Horizontal is Tally-style two-pane. Vertical stacks one column."),
            _s("Drill down", "Click a ledger to open the same Ledger Preview used on Ledger Report."),
            _s("Export", "Print, PDF, and Excel use the figures currently on screen."),
        ),
        shots=(
            _shot(
                "Figure 1 — Financial Statements toolbar and report list",
                "Financial Statements",
                ribbon=("Reports and Analysis", "Financial Statements"),
                fields=(("From", "01-04-2026"), ("To", "09-09-2026"), ("View", "Horizontal")),
                columns=("Report", ""),
                rows=(
                    ("Balance Sheet", ""),
                    ("Profit & Loss", ""),
                    ("Trial Balance", ""),
                    ("Depreciation Chart", ""),
                ),
                highlights=("One date pair drives every statement", "Refresh after changing dates"),
            ),
        ),
        related=(
            "balance-sheet",
            "profit-loss",
            "trial-balance",
            "depreciation-chart",
            "ledger-report",
            "calculations-index",
        ),
        keywords="financial statements tally from to horizontal vertical",
    ),
    _t(
        "balance-sheet",
        "Balance Sheet",
        "bi-layout-split",
        "statements",
        "Reports and Analysis → Financial Statements → Balance Sheet",
        "Assets versus Liabilities and Capital as at To Date. Closing figures include period movements and (for fixed assets) current-year depreciation.",
        url="/Reports_and_analysis/financial-statements/balance-sheet",
        steps=(
            _s("Read the two sides", "Assets on one pane; Liabilities and Capital on the other (horizontal view)."),
            _s("Check the total", "The two sides must agree. A difference means a ledger still needs grouping or an unposted opening."),
        ),
        shots=(
            _shot(
                "Figure 1 — Balance Sheet (horizontal)",
                "Balance Sheet",
                columns=("Liabilities", "Amount", "Assets", "Amount"),
                rows=(
                    ("Capital", "10,00,000.00", "Bank accounts", "4,20,000.00"),
                    ("Sundry creditors", "80,000.00", "Sundry debtors", "3,10,000.00"),
                    ("", "", "Fixed assets (WDV)", "3,50,000.00"),
                ),
                highlights=("As at To Date", "Fixed assets show written-down value after current-year depreciation"),
            ),
        ),
        formulas=(
            _f("Balance sheet identity", "Assets = Liabilities + Capital (including current-year profit from P&L)."),
            _f("Ledger closing on BS", "Same closing rule as Ledger Report for each account, as at To Date."),
        ),
        related=("profit-loss", "trial-balance", "fixed-assets-schedule", "calculations-index"),
        keywords="balance sheet assets liabilities capital",
    ),
    _t(
        "profit-loss",
        "Profit & Loss",
        "bi-graph-up",
        "statements",
        "Reports and Analysis → Financial Statements → Profit & Loss",
        "Income and expense for the From–To period. Current-year depreciation on Item Master fixed assets is charged here and reduces WDV on the Balance Sheet.",
        url="/Reports_and_analysis/financial-statements/profit-loss",
        formulas=(
            _f("Net profit", "Period income − period expense (including current-year WDV depreciation)."),
            _f("Depreciation charge", "See Depreciation Chart — the same current-year amount is posted to the P&L depreciation head."),
        ),
        related=("trading-account", "depreciation-chart", "income-expense"),
        keywords="profit loss pnl income expense depreciation",
    ),
    _t(
        "trial-balance",
        "Trial Balance",
        "bi-scales",
        "statements",
        "Reports and Analysis → Financial Statements → Trial Balance",
        "Every ledger with opening, period debit, period credit, and closing. Debit and credit columns must tally.",
        url="/Reports_and_analysis/financial-statements/trial-balance",
        shots=(
            _shot(
                "Figure 1 — Trial Balance columns",
                "Trial Balance",
                columns=("Ledger", "Opening", "Debit", "Credit", "Closing"),
                rows=(("HDFC Current", "2,00,000 Dr", "50,000.00", "25,000.00", "2,25,000 Dr"),),
                highlights=("Period debit/credit are From–To movements", "Closing is as at To Date"),
            ),
        ),
        formulas=(
            _f("TB check", "Sum of closing Debit balances = sum of closing Credit balances."),
        ),
        related=("balance-sheet", "ledger-report", "calculations-index"),
        keywords="trial balance debit credit tally",
    ),
    _t(
        "trading-account",
        "Trading Account",
        "bi-cart",
        "statements",
        "Reports and Analysis → Financial Statements → Trading Account",
        "Gross profit view: opening stock, purchases, direct expenses versus sales and closing stock — using Chart of Account groups mapped as trading heads.",
        url="/Reports_and_analysis/financial-statements/trading-account",
        formulas=(
            _f("Gross profit", "Trading credits (sales, closing stock) − trading debits (opening stock, purchases, direct expenses)."),
        ),
        related=("profit-loss", "chart-of-group"),
        keywords="trading account gross profit stock",
    ),
    _t(
        "cash-flow-fs",
        "Cash Flow (statement)",
        "bi-cash-stack",
        "statements",
        "Reports and Analysis → Financial Statements → Cash Flow",
        "Tally-style cash flow classified from ledger movements in the period. Distinct from the operational Cash Flow report under Reports.",
        url="/Reports_and_analysis/financial-statements/cash-flow",
        related=("cash-flow-report", "fund-flow"),
        keywords="cash flow statement financial",
    ),
    _t(
        "fund-flow",
        "Fund Flow",
        "bi-arrow-left-right",
        "statements",
        "Reports and Analysis → Financial Statements → Fund Flow",
        "Sources and applications of funds between From and To dates.",
        url="/Reports_and_analysis/financial-statements/fund-flow",
        related=("cash-flow-fs", "balance-sheet"),
        keywords="fund flow sources applications",
    ),
    _t(
        "depreciation-chart",
        "Depreciation Chart",
        "bi-percent",
        "statements",
        "Reports and Analysis → Financial Statements → Depreciation Chart",
        "Income-tax WDV chart for Item Master fixed assets. Rates are entered on Item Master (no Sync button). The chart computes current-year depreciation in memory when you open the report — it does not rewrite masters on load.",
        url="/Reports_and_analysis/financial-statements/depreciation-chart",
        steps=(
            _s("Maintain the asset", "Masters → Item Master: mark the item as a fixed asset, set purchase/put-to-use date, opening WDV, and depreciation rate %."),
            _s("Open the chart", "Financial Statements → Depreciation Chart. Set To date (financial year as-of)."),
            _s("Read current year", "Current-year depreciation follows Appendix I WDV halves (1 Apr–30 Sep and 1 Oct–31 Mar)."),
        ),
        shots=(
            _shot(
                "Figure 1 — Depreciation Chart rows",
                "Depreciation Chart",
                columns=("Asset", "Rate %", "WDV opening", "Current year", "Accumulated"),
                rows=(("Office car", "15.00", "8,00,000.00", "60,000.00", "2,40,000.00"),),
                highlights=("Rate is typed on Item Master", "Put-to-use after 30 Sep uses half-year treatment"),
            ),
        ),
        formulas=(
            _f("Annual WDV charge", "Annual = Opening WDV × Rate ÷ 100 (capped so it cannot exceed WDV)."),
            _f("First half (as-of on/before 30 Sep)", "Current year = Annual ÷ 2, unless put-to-use is in the second half (then nil in H1)."),
            _f("Second half", "If put-to-use is on/after 1 Oct, first-year charge is 50% of annual, spread across remaining days of the FY as implemented on the chart."),
            _f("P&L and BS", "Current-year amount is added to the depreciation expense head and deducted from the asset WDV on the Balance Sheet."),
        ),
        tips=("Land value / investment appreciation is separate — see Item Master.",),
        related=("item-master", "fixed-assets-schedule", "profit-loss", "calculations-index"),
        keywords="depreciation wdv appendix i half year item master rate",
    ),
    _t(
        "fixed-assets-schedule",
        "Schedule of Fixed Assets",
        "bi-building",
        "statements",
        "Reports and Analysis → Financial Statements → Schedule of Fixed Assets",
        "Asset-wise opening WDV, additions, current-year depreciation, and closing WDV for the financial year ending on To Date.",
        url="/Reports_and_analysis/financial-statements/fixed-assets-schedule",
        formulas=(
            _f("Closing WDV", "Opening WDV + additions − current-year depreciation (and disposals if recorded)."),
        ),
        related=("depreciation-chart", "item-master"),
        keywords="fixed assets schedule wdv",
    ),
    _t(
        "ratio-analysis",
        "Ratio Analysis",
        "bi-pie-chart",
        "statements",
        "Reports and Analysis → Financial Statements → Ratio Analysis",
        "Liquidity, solvency, and profitability ratios computed from the same ledger closing used on Balance Sheet and P&L for the selected dates.",
        url="/Reports_and_analysis/financial-statements/ratio-analysis",
        formulas=(
            _f("Current ratio", "Current assets ÷ current liabilities (from BS group closings)."),
            _f("Net profit ratio", "Net profit ÷ revenue (from P&L closings)."),
        ),
        related=("balance-sheet", "profit-loss"),
        keywords="ratio analysis current ratio np",
    ),
    _t(
        "calculations-index",
        "Calculations used in JTCS",
        "bi-calculator",
        "statements",
        "Help → Calculations",
        "Single place that documents every major formula used by ledgers, statements, depreciation, stamp, invoices, and outstanding. The software itself is not changed by this page.",
        url="/help/calculations-index",
        formulas=(
            _f("Asset / Expense / Customer books", "Closing = Opening + Debit − Credit."),
            _f("Liability / Capital / Income / Bank OD", "Closing = Opening + Credit − Debit."),
            _f("Ledger Total Debit / Total Credit", "Sum of transaction debit/credit in the From–To window only (opening is excluded)."),
            _f("Ledger Closing as of To Date", "Opening + all movements with date ≤ To Date."),
            _f("Bank movements vs opening date", "Transactions before Bank Opening Balance Date are not added on top of that opening."),
            _f("Customer outstanding", "Opening + billed (invoices + followup bills) − receipts."),
            _f("Contra", "Two bank lines, same amount, opposite debit/credit."),
            _f("Stamp collection", "Wallet opening + receipts − stamp sales."),
            _f("WDV depreciation", "Annual = WDV × Rate%. First half of FY typically 50% of annual; put-to-use in H2 uses half-year rule."),
            _f("Balance Sheet", "Assets = Liabilities + Capital including current-year P&L."),
            _f("Trial Balance", "Total closing Debit = total closing Credit."),
            _f("GST on invoices", "Tax = Taxable value × GST rate (CGST/SGST or IGST as on the voucher)."),
        ),
        tips=("Open the topic for a menu to see the same formula next to its screen figures.",),
        related=(
            "ledger-report",
            "financial-statements",
            "depreciation-chart",
            "invoices",
            "stamp-reports",
            "outstanding",
        ),
        keywords="formula calculation closing opening debit credit wdv gst",
    ),
)


def get_groups() -> tuple[tuple[str, str, str], ...]:
    return GROUPS


def get_topics() -> tuple[HelpTopic, ...]:
    from app.services.help_topics_more import MORE_TOPICS

    return TOPICS + MORE_TOPICS


def get_topic(slug: str) -> HelpTopic | None:
    needle = (slug or "").strip().lower()
    for topic in get_topics():
        if topic.slug == needle:
            return topic
    return None


def topics_by_group() -> list[tuple[str, str, str, list[HelpTopic]]]:
    grouped: dict[str, list[HelpTopic]] = {key: [] for key, _title, _icon in GROUPS}
    extra: list[HelpTopic] = []
    for topic in get_topics():
        if topic.group in grouped:
            grouped[topic.group].append(topic)
        else:
            extra.append(topic)
    out: list[tuple[str, str, str, list[HelpTopic]]] = []
    for key, title, icon in GROUPS:
        out.append((key, title, icon, grouped[key]))
    if extra:
        out.append(("other", "Other", "bi-three-dots", extra))
    return out


def search_topics(query: str) -> list[HelpTopic]:
    q = (query or "").strip().lower()
    if not q:
        return list(get_topics())
    hits: list[HelpTopic] = []
    for topic in get_topics():
        blob = " ".join(
            [
                topic.slug,
                topic.title,
                topic.menu_path,
                topic.summary,
                topic.keywords,
                " ".join(f.name + " " + f.expression for f in topic.formulas),
            ]
        ).lower()
        if q in blob:
            hits.append(topic)
    return hits
