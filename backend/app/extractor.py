
import re
from datetime import datetime

from app.schemas import InvoiceData, LineItem


def clean_text(text):
    text = text.replace("\xa0", " ")
    text = text.replace("₹", " INR ")
    return re.sub(r"[ \t]+", " ", text)


def find_field(text, labels, value_pattern):
    label_pattern = "|".join(labels)
    pattern = (
        rf"(?im)^\s*(?:{label_pattern})\s*[:#-]?\s*"
        rf"(?:\n\s*)?({value_pattern})"
    )
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def parse_amount(value):
    if not value:
        return None

    value = value.replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d{1,2})?", value)

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def extract_amount(text, labels):
    if isinstance(labels, str):
        labels = [labels]

    label_pattern = "|".join(labels)

    pattern = (
        rf"(?im)^\s*(?:{label_pattern})\s*[:\-]?\s*"
        rf"(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        rf"([-+]?\d[\d,]*(?:\.\d{{1,2}})?)"
    )

    match = re.search(pattern, text)

    if match:
        return parse_amount(match.group(1))

    pattern = (
        rf"(?im)^\s*(?:{label_pattern})\s*[:\-]?\s*$"
        rf"\s*(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
        rf"([-+]?\d[\d,]*(?:\.\d{{1,2}})?)"
    )

    match = re.search(pattern, text)

    if match:
        return parse_amount(match.group(1))

    return None


def extract_date(text):
    raw_date = find_field(
        text,
        [r"Invoice\s*Date", r"Bill\s*Date", r"Date\s*of\s*Issue"],
        r"\d{1,2}[-/. ](?:\d{1,2}|[A-Za-z]{3,9})[-/. ]\d{2,4}"
    )

    if not raw_date:
        return None

    formats = [
        "%d-%b-%Y", "%d/%b/%Y",
        "%d-%B-%Y", "%d/%B/%Y",
        "%d-%m-%Y", "%d/%m/%Y",
        "%d.%m.%Y", "%d-%m-%y",
        "%d/%m/%y", "%Y-%m-%d",
        "%Y/%m/%d"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(raw_date, fmt).date().isoformat()
        except ValueError:
            continue

    return raw_date


def extract_line_items(lines):
    items = []

    for i, line in enumerate(lines):
        if not re.search(r"description|particulars|item", line, re.I):
            continue

        if not re.search(r"quantity|qty", line, re.I):
            continue

        if not re.search(r"amount|total", line, re.I):
            continue

        for row in lines[i + 1:]:
            if re.match(
                r"(?i)^\s*(subtotal|tax|gst|grand total|invoice total)",
                row
            ):
                break

            values = re.findall(r"-?\d[\d,]*(?:\.\d{1,2})?", row)

            if len(values) < 3:
                continue

            try:
                amount = parse_amount(values[-1])
                unit_price = parse_amount(values[-2])
                quantity = parse_amount(values[-3])

                description = row
                for value in values[-3:]:
                    description = description.replace(value, "", 1)

                description = description.strip(" |:-")

                if amount is not None and quantity is not None:
                    items.append(
                        LineItem(
                            description=description or "Invoice item",
                            quantity=quantity,
                            unit_price=unit_price or 0,
                            amount=amount
                        )
                    )
            except (ValueError, TypeError):
                continue

        if items:
            break

    return items


def extract_invoice_data(text):
    text = clean_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    vendor_name = None

    ignored = re.compile(
        r"(?i)^(tax invoice|invoice|bill|original|duplicate|copy)$"
    )

    for line in lines[:10]:
        if not ignored.match(line) and not re.search(
            r"invoice\s*(number|no|#|date)", line, re.I
        ):
            vendor_name = line
            break

    invoice_number = find_field(
        text,
        [
            r"Invoice\s*(?:Number|No\.?|#)",
            r"Bill\s*(?:Number|No\.?|#)",
            r"Document\s*(?:Number|No\.?)"
        ],
        r"[A-Z0-9][A-Z0-9/-]*"
    )

    invoice_date = extract_date(text)

    po_reference = find_field(
        text,
        [
            r"Purchase\s*Order(?:\s*(?:Number|No\.?|#))?",
            r"PO\s*(?:Reference|Number|No\.?|#)",
            r"Order\s*Reference",
            r"Order\s*Ref"
        ],
        r"[A-Z0-9][A-Z0-9/-]*"
    )

    subtotal = extract_amount(text, [r"Sub\s*Total", r"Subtotal"])
    tax = extract_amount(text, [r"GST(?:\s*Amount)?", r"Tax(?:\s*Amount)?", r"VAT"])
    total = extract_amount(
        text,
        [
            r"Grand\s*Total",
            r"Invoice\s*Total",
            r"Total\s*Due",
            r"Amount\s*Payable",
            r"Net\s*Payable",
            r"Total"
        ]
    )

    currency = "UNKNOWN"

    currency_patterns = [
        (r"\bINR\b|₹|\bRs\.?", "INR"),
        (r"\bUSD\b|\$", "USD"),
        (r"\bEUR\b|€", "EUR"),
        (r"\bGBP\b|£", "GBP"),
        (r"\bJPY\b|¥", "JPY")
    ]

    for pattern, code in currency_patterns:
        if re.search(pattern, text, re.I):
            currency = code
            break

    line_items = extract_line_items(lines)

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
