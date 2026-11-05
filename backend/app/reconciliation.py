
from rapidfuzz import fuzz

from app.models import Vendor, PurchaseOrder, Invoice


def normalize(value):
    if not value:
        return ""
    return " ".join(value.lower().strip().split())


def find_vendor(db, vendor_name):
    vendors = db.query(Vendor).all()

    best_vendor = None
    best_score = 0

    for vendor in vendors:
        names = [vendor.legal_name]

        if vendor.aliases:
            names.extend(vendor.aliases.split(";"))

        for name in names:
            score = fuzz.token_sort_ratio(
                normalize(vendor_name),
                normalize(name)
            )

            if score > best_score:
                best_score = score
                best_vendor = vendor

    if best_score >= 85:
        return best_vendor, best_score

    return None, best_score


def evaluate_invoice(db, invoice_data):

    reasons = []
    warnings = []

    data = invoice_data

    # 1. Required field validation
    if data.missing_fields:
        reasons.append(
            "Missing required fields: "
            + ", ".join(data.missing_fields)
        )

    if data.extraction_warnings:
        warnings.extend(data.extraction_warnings)

    if warnings:
        reasons.extend(warnings)

    if data.total is None or data.subtotal is None:
        reasons.append("Invoice financial amounts could not be extracted.")

    if reasons:
        return {
            "status": "MANUAL_REVIEW",
            "reasons": reasons,
            "matched_vendor": None,
            "matched_po": None
        }

    # 2. Vendor verification
    vendor, score = find_vendor(db, data.vendor_name)

    if not vendor:
        return {
            "status": "MANUAL_REVIEW",
            "reasons": [
                f"Vendor could not be confidently matched. Best match score: {score}%."
            ],
            "matched_vendor": None,
            "matched_po": None
        }

    if not vendor.approved:
        return {
            "status": "REJECTED",
            "reasons": [
                f"Vendor '{vendor.legal_name}' is not approved."
            ],
            "matched_vendor": vendor.legal_name,
            "matched_po": None
        }

    # 3. Duplicate invoice detection
    existing_invoices = db.query(Invoice).filter(
        Invoice.invoice_number == data.invoice_number
    ).all()

    for existing in existing_invoices:
        if normalize(existing.vendor_name) == normalize(vendor.legal_name):
            return {
                "status": "REJECTED",
                "reasons": [
                    f"Duplicate invoice detected: {data.invoice_number}."
                ],
                "matched_vendor": vendor.legal_name,
                "matched_po": None
            }

    # 4. Purchase order lookup
    purchase_order = db.query(PurchaseOrder).filter(
        PurchaseOrder.po_number == data.po_reference
    ).first()

    if not purchase_order:
        return {
            "status": "MANUAL_REVIEW",
            "reasons": [
                f"Purchase order {data.po_reference} was not found."
            ],
            "matched_vendor": vendor.legal_name,
            "matched_po": None
        }

    # 5. PO vendor matching
    if purchase_order.vendor_id != vendor.id:
        return {
            "status": "REJECTED",
            "reasons": [
                "Purchase order belongs to a different vendor."
            ],
            "matched_vendor": vendor.legal_name,
            "matched_po": purchase_order.po_number
        }

    # 6. Currency validation
    if data.currency != purchase_order.currency:
        return {
            "status": "MANUAL_REVIEW",
            "reasons": [
                f"Currency mismatch: invoice uses {data.currency}, "
                f"but PO uses {purchase_order.currency}."
            ],
            "matched_vendor": vendor.legal_name,
            "matched_po": purchase_order.po_number
        }

    # 7. Cumulative PO balance validation
    po_amount = purchase_order.total_amount
    already_invoiced = purchase_order.invoiced_amount or 0.0
    current_amount = data.subtotal

    tolerance = po_amount * (
        purchase_order.tolerance_percent / 100
    )

    permitted_amount = po_amount + tolerance
    projected_total = already_invoiced + current_amount

    if projected_total > permitted_amount:
        return {
            "status": "REJECTED",
            "reasons": [
                f"PO limit exceeded. PO value: {po_amount:.2f}, "
                f"already invoiced: {already_invoiced:.2f}, "
                f"current invoice: {current_amount:.2f}, "
                f"permitted maximum including tolerance: {permitted_amount:.2f}."
            ],
            "matched_vendor": vendor.legal_name,
            "matched_po": purchase_order.po_number,
            "po_amount": po_amount,
            "already_invoiced": already_invoiced,
            "projected_total": projected_total,
            "permitted_amount": permitted_amount
        }

    # 8. Approve and update PO balance
    purchase_order.invoiced_amount = projected_total
    db.commit()

    return {
        "status": "APPROVED",
        "reasons": [
            "Vendor verified successfully.",
            "Purchase order matched successfully.",
            "No duplicate invoice detected.",
            "Currency matches the purchase order.",
            "Invoice is within the permitted PO limit."
        ],
        "matched_vendor": vendor.legal_name,
        "matched_po": purchase_order.po_number,
        "po_amount": po_amount,
        "already_invoiced": already_invoiced,
        "projected_total": projected_total,
        "permitted_amount": permitted_amount
    }
