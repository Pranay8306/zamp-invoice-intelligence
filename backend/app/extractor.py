
import re
from datetime import datetime

from app.schemas import InvoiceData, LineItem



def extract_amount(text, label):
    pattern = rf"(?im)^\s*(?:{label})\s*:?\s*\n?\s*(?:INR|₹)?\s*([\d,]+\.\d{{2}})"

    match = re.search(pattern, text)

    if match:
        return float(match.group(1).replace(",", ""))

    return None


def extract_invoice_data(text):

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    vendor_name = lines[0] if lines else None

    invoice_number = None
    invoice_date = None
    po_reference = None

    
    number_match = re.search(
        r"(?im)^\s*Invoice\s*Number\s*:?\s*(?:\n\s*)?([A-Z0-9][A-Z0-9/-]*)\s*$",
        text
    )

    if number_match:
        invoice_number = number_match.group(1).strip()


    date_match = re.search(
        r"Invoice\s*Date\s*:?\s*\n?\s*(\d{1,2}[-/][A-Za-z0-9]+[-/]\d{4})",
        text,
        re.IGNORECASE
    )

    if date_match:
        raw_date = date_match.group(1)

        for date_format in (
            "%d-%b-%Y",
            "%d/%b/%Y",
            "%d-%m-%Y",
            "%d/%m/%Y"
        ):
            try:
                invoice_date = datetime.strptime(
                    raw_date, date_format
                ).date().isoformat()
                break
            except ValueError:
                continue

        if invoice_date is None:
            invoice_date = raw_date

    po_match = re.search(
        r"Purchase\s*Order\s*:?\s*\n?\s*([A-Z0-9/-]+)",
        text,
        re.IGNORECASE
    )

    if po_match:
        po_reference = po_match.group(1).strip()

    subtotal = extract_amount(text, "Subtotal")
    tax = extract_amount(text, "GST|Tax")
    total = extract_amount(text, "TOTAL")

    currency = "INR" if re.search(r"\bINR\b|₹", text) else "UNKNOWN"

    line_items = []

    try:
        start = next(
            i for i, line in enumerate(lines)
            if line.lower() == "description"
        )

        end = next(
            i for i in range(start + 1, len(lines))
            if lines[i].lower() == "subtotal"
        )

        item_lines = lines[start + 4:end]

        i = 0

        while i + 3 < len(item_lines):

            description = item_lines[i]
            quantity_text = item_lines[i + 1]
            unit_price_text = item_lines[i + 2]
            amount_text = item_lines[i + 3]

            try:
                quantity = float(quantity_text.replace(",", ""))
                unit_price = float(unit_price_text.replace(",", ""))
                amount = float(amount_text.replace(",", ""))

                line_items.append(
                    LineItem(
                        description=description,
                        quantity=quantity,
                        unit_price=unit_price,
                        amount=amount
                    )
                )

                i += 4

            except ValueError:
                i += 1

    except StopIteration:
        pass

    missing_fields = []

    required_fields = {
        "vendor_name": vendor_name,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "po_reference": po_reference,
        "total": total
    }

    for field, value in required_fields.items():
        if value is None:
            missing_fields.append(field)

    warnings = []

    if currency == "UNKNOWN":
        warnings.append("Currency could not be identified.")

    if subtotal is not None and tax is not None and total is not None:
        if abs((subtotal + tax) - total) > 0.01:
            warnings.append(
                "Subtotal plus tax does not equal invoice total."
            )

    if not line_items:
        warnings.append("No line items could be extracted.")

    return InvoiceData(
        vendor_name=vendor_name,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        po_reference=po_reference,
        currency=currency,
        subtotal=subtotal,
        tax=tax,
        total=total,
        line_items=line_items,
        missing_fields=missing_fields,
        extraction_warnings=warnings
    )
