from datetime import date

from flask import (
    Blueprint,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.decorators import login_required, require_delete_reauth
from app.services.bank_master_service import BankMasterService
from app.services.gst_invoice_pdf_service import GstInvoicePdfService
from app.services.gst_invoice_service import GstInvoiceService
from app.services.followup_service import tax_period_options
from app.services.item_master_service import ItemMasterService
from app.services.menu_service import MenuService
from app.utils.db_session import map_db_exception

# Invoice line review fields for SAC (Service) items
_SERVICE_QUARTERS = (
    "Q1-Apr-May-Jun",
    "Q2-Jul-Aug-Sep",
    "Q3-Oct-Nov-Dec",
    "Q4-Jan-Feb-Mar",
)
_QUARTER_MONTHS = {
    "Q1-Apr-May-Jun": ["April", "May", "June"],
    "Q2-Jul-Aug-Sep": ["July", "August", "September"],
    "Q3-Oct-Nov-Dec": ["October", "November", "December"],
    "Q4-Jan-Feb-Mar": ["January", "February", "March"],
}

bp = Blueprint("accounting_invoice", __name__, url_prefix="/accounting")


def _ensure_menus() -> None:
    from sqlalchemy import text

    from app.extensions import db

    db.session.execute(
        text(
            """
            DECLARE @AccountingID INT;
            SELECT TOP 1 @AccountingID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Accounting' AND ParentMenuID IS NULL
            ORDER BY MenuID;

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
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @AccountingID, N'Generate Invoice', N'bi-receipt',
                        N'/accounting/invoice', 1, N'Generate GST tax invoice', 1, NULL
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
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @AccountingID, N'Reports', N'bi-bar-chart-line',
                        N'/accounting/reports', 2, N'Accounting invoice reports', 1, NULL
                    );
            END
            """
        )
    )
    db.session.commit()


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


@bp.route("/invoice", methods=["GET"], strict_slashes=False)
@login_required
def invoice_index():
    try:
        _ensure_menus()
    except Exception:
        from app.extensions import db

        db.session.rollback()
    svc = GstInvoiceService()
    items = ItemMasterService().list_active_for_dropdown()
    payment_banks = BankMasterService().list_payment_accounts()
    return render_template(
        "accounting/invoice.html",
        page_title="Generate Invoice",
        breadcrumb=MenuService().get_breadcrumb("/accounting/invoice", session.get("role")),
        next_invoice_no=svc.next_invoice_no(invoice_kind=GstInvoiceService.INVOICE_KIND_NON_GST),
        company=svc.company_profile(),
        items=items,
        payment_banks=payment_banks,
        today=date.today().isoformat(),
        tax_periods=tax_period_options(),
        service_quarters=_SERVICE_QUARTERS,
        quarter_months=_QUARTER_MONTHS,
    )


@bp.route("/reports", methods=["GET"], strict_slashes=False)
@login_required
def reports_index():
    try:
        _ensure_menus()
    except Exception:
        from app.extensions import db

        db.session.rollback()
    return render_template(
        "accounting/reports.html",
        page_title="Accounting Reports",
        breadcrumb=MenuService().get_breadcrumb("/accounting/reports", session.get("role")),
    )


@bp.route("/api/payment-banks", methods=["GET"], strict_slashes=False)
@login_required
def api_payment_banks():
    try:
        rows = BankMasterService().list_payment_accounts()
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/customers", methods=["GET"], strict_slashes=False)
@login_required
def api_customers():
    q = (request.args.get("q") or "").strip() or None
    try:
        rows = GstInvoiceService().search_customers(q)
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/customers/<int:customer_id>", methods=["GET"], strict_slashes=False)
@login_required
def api_customer_detail(customer_id: int):
    try:
        detail = GstInvoiceService()._load_customer(customer_id)
        if not detail:
            return jsonify({"ok": False, "error": "Customer not found."}), 404
        return jsonify({"ok": True, "record": detail})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/invoices", methods=["GET"], strict_slashes=False)
@login_required
def api_list_invoices():
    search = (request.args.get("search") or "").strip() or None
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))
    try:
        rows = GstInvoiceService().list_records(
            search=search, date_from=date_from, date_to=date_to
        )
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/invoices/<int:invoice_id>", methods=["GET"], strict_slashes=False)
@login_required
def api_get_invoice(invoice_id: int):
    try:
        data = GstInvoiceService().get_record_with_nav(invoice_id)
        return jsonify({"ok": True, **data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/invoices/preview", methods=["POST"], strict_slashes=False)
@login_required
def api_preview_invoice():
    payload = request.get_json(silent=True) or {}
    try:
        totals = GstInvoiceService().preview_totals(payload)
        return jsonify({"ok": True, "totals": totals})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/invoices", methods=["POST"], strict_slashes=False)
@login_required
def api_create_invoice():
    payload = request.get_json(silent=True) or {}
    try:
        record = GstInvoiceService().create_record(
            payload, created_by=session.get("username") or session.get("user_name")
        )
        return jsonify(
            {
                "ok": True,
                "record": record,
                "message": "Invoice created successfully.",
                "pdf_url": url_for(
                    "accounting_invoice.download_pdf", invoice_id=record["invoice_id"]
                ),
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/invoices/<int:invoice_id>", methods=["POST"], strict_slashes=False)
@login_required
def api_update_invoice(invoice_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        record = GstInvoiceService().update_record(invoice_id, payload)
        return jsonify(
            {
                "ok": True,
                "record": record,
                "message": "Invoice updated successfully.",
                "pdf_url": url_for(
                    "accounting_invoice.download_pdf", invoice_id=record["invoice_id"]
                ),
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/invoices/navigate", methods=["GET"], strict_slashes=False)
@login_required
def api_navigate_invoice():
    direction = (request.args.get("direction") or "").strip()
    current_raw = (request.args.get("current_id") or "").strip()
    current_id = int(current_raw) if current_raw.isdigit() else None
    try:
        data = GstInvoiceService().navigate(current_id=current_id, direction=direction)
        return jsonify({"ok": True, **data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/invoices/next-no", methods=["GET"], strict_slashes=False)
@login_required
def api_next_invoice_no():
    inv_date = _parse_date(request.args.get("date")) or date.today()
    kind = (request.args.get("kind") or request.args.get("invoice_kind") or "NON_GST").strip()
    try:
        svc = GstInvoiceService()
        invoice_kind = svc.normalize_invoice_kind(kind)
        return jsonify(
            {
                "ok": True,
                "invoice_no": svc.next_invoice_no(inv_date, invoice_kind=invoice_kind),
                "invoice_kind": invoice_kind,
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/invoices/<int:invoice_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def api_delete_invoice(invoice_id: int):
    try:
        message = GstInvoiceService().delete_record(invoice_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/invoice/<int:invoice_id>/preview-html", methods=["GET"], strict_slashes=False)
@login_required
def preview_html(invoice_id: int):
    """Same-page HTML invoice preview (JSON: {ok, html})."""
    try:
        svc = GstInvoiceService()
        pdf_svc = GstInvoicePdfService()
        invoice = svc.get_record(invoice_id)
        company = svc.company_profile()
        qr_data_uri = pdf_svc.upi_qr_data_uri(invoice)
        logo_url = url_for("static", filename="img/jtcs_invoice_logo.png")
        html = render_template(
            "accounting/_invoice_preview_html.html",
            invoice=invoice,
            company=company,
            qr_data_uri=qr_data_uri,
            logo_url=logo_url,
        )
        return jsonify(
            {
                "ok": True,
                "html": html,
                "invoice_no": invoice.get("invoice_no") or "",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/invoice/<int:invoice_id>/pdf", methods=["GET"], strict_slashes=False)
@login_required
def download_pdf(invoice_id: int):
    inline = (request.args.get("inline") or "").strip().lower() in {"1", "true", "yes"}
    try:
        content, filename = GstInvoicePdfService().build_pdf(invoice_id)
        disposition = "inline" if inline else "attachment"
        return Response(
            content,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'{disposition}; filename="{filename}"',
            },
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/invoices/preview-pdf", methods=["POST"], strict_slashes=False)
@login_required
def api_preview_pdf():
    """PDF preview/print from current form values (includes unsaved edits)."""
    payload = request.get_json(silent=True) or {}
    try:
        content, filename = GstInvoicePdfService().build_pdf_from_payload(payload)
        return Response(
            content,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))
