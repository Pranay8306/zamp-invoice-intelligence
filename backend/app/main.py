
import os
import uuid
from pathlib import Path

import pymupdf
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.extractor import extract_invoice_data
from app.database import Base, engine, SessionLocal
from app.models import Invoice, Vendor, PurchaseOrder
from app.reconciliation import evaluate_invoice


app = FastAPI(title="Zamp Invoice Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://zamp-invoice-intelligence.vercel.app",
        "http://localhost:5173"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 15 * 1024 * 1024

TESSERACT_PATH = Path(r"C:\Program Files\Tesseract-OCR")

if TESSERACT_PATH.exists():
    os.environ["PATH"] += os.pathsep + str(TESSERACT_PATH)


def initialize_reference_data():
    db = SessionLocal()

    try:
        vendor = db.query(Vendor).filter(
            Vendor.gstin == "36AABCA1234F1Z5"
        ).first()

        if not vendor:
            vendor = Vendor(
                legal_name="ABC Technologies Pvt. Ltd.",
                aliases="ABC TECHNOLOGIES PVT. LTD.;ABC Technologies",
                gstin="36AABCA1234F1Z5",
                approved=True
            )
            db.add(vendor)
            db.flush()

        po1 = db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number == "PO-5021"
        ).first()

        if not po1:
            db.add(
                PurchaseOrder(
                    po_number="PO-5021",
                    vendor_id=vendor.id,
                    total_amount=200000,
                    tolerance_percent=3,
                    currency="INR",
                    invoiced_amount=0
                )
            )

        po2 = db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number == "PO-5022"
        ).first()

        if not po2:
            db.add(
                PurchaseOrder(
                    po_number="PO-5022",
                    vendor_id=vendor.id,
                    total_amount=100000,
                    tolerance_percent=3,
                    currency="INR",
                    invoiced_amount=0
                )
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


initialize_reference_data()


@app.get("/")
def root():
    return {"message": "Zamp Invoice Intelligence API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/api/invoices/upload")
async def upload_invoice(file: UploadFile = File(...)):
    db = SessionLocal()

    try:
        processing_trace = []

        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported."
            )

        file_bytes = await file.read()

        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="File size exceeds the 15 MB limit."
            )

        if not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF file."
            )

        processing_trace.append({
            "stage": "PDF validation",
            "status": "completed",
            "detail": "PDF format, file signature and file size validated."
        })

        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}.pdf"

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        try:
            document = pymupdf.open(file_path)

            if document.is_encrypted:
                raise HTTPException(
                    status_code=400,
                    detail="Password-protected PDFs are not supported."
                )

            page_count = len(document)
            extracted_pages = []
            extraction_methods = []
            warnings = []

            for page_number, page in enumerate(document):
                page_text = page.get_text("text")

                if len(page_text.strip()) >= 40:
                    extracted_pages.append(page_text)
                    extraction_methods.append("text")

                else:
                    try:
                        import pytesseract
                        from PIL import Image

                        pix = page.get_pixmap(
                            matrix=pymupdf.Matrix(2.5, 2.5)
                        )

                        image = Image.frombytes(
                            "RGB",
                            [pix.width, pix.height],
                            pix.samples
                        )

                        ocr_text = pytesseract.image_to_string(image)

                        extracted_pages.append(ocr_text)
                        extraction_methods.append("ocr")

                    except Exception as e:
                        extracted_pages.append("")
                        extraction_methods.append("failed")
                        warnings.append(
                            f"OCR failed on page {page_number + 1}: {str(e)}"
                        )

            document.close()

        except HTTPException:
            raise

        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read PDF: {str(e)}"
            )

        extracted_text = "\n".join(extracted_pages)

        if "ocr" in extraction_methods and "text" in extraction_methods:
            method = "mixed"
        elif "ocr" in extraction_methods:
            method = "ocr"
        elif "text" in extraction_methods:
            method = "text"
        else:
            method = "none"

        processing_trace.append({
            "stage": "Text extraction",
            "status": "completed",
            "detail": f"Processed {page_count} page(s) using {method.upper()} extraction.",
            "warnings": warnings
        })

        invoice_data = extract_invoice_data(extracted_text)
        invoice_data.extraction_warnings.extend(warnings)

        found_fields = [
            name for name, value in {
                "Vendor": invoice_data.vendor_name,
                "Invoice number": invoice_data.invoice_number,
                "Invoice date": invoice_data.invoice_date,
                "PO reference": invoice_data.po_reference,
                "Subtotal": invoice_data.subtotal,
                "Tax": invoice_data.tax,
                "Total": invoice_data.total
            }.items()
            if value is not None
        ]

        processing_trace.append({
            "stage": "Invoice data extraction",
            "status": "completed",
            "detail": f"Extracted {len(found_fields)} of 7 key fields.",
            "checks": [f"Found: {field}" for field in found_fields],
            "warnings": invoice_data.extraction_warnings
        })

        decision = evaluate_invoice(db, invoice_data)

        processing_trace.append({
            "stage": "Vendor and PO reconciliation",
            "status": "completed",
            "detail": f"Reconciliation produced a {decision['status']} decision.",
            "checks": decision["reasons"]
        })

        invoice_record = Invoice(
            invoice_id=str(uuid.uuid4()),
            invoice_number=invoice_data.invoice_number,
            vendor_name=invoice_data.vendor_name,
            po_reference=invoice_data.po_reference,
            invoice_date=invoice_data.invoice_date,
            currency=invoice_data.currency,
            subtotal=invoice_data.subtotal,
            tax=invoice_data.tax,
            total=invoice_data.total,
            status=decision["status"],
            decision_reason="; ".join(decision["reasons"]),
            file_name=file.filename
        )

        db.add(invoice_record)
        db.commit()
        db.refresh(invoice_record)

        processing_trace.append({
            "stage": "Database storage",
            "status": "completed",
            "detail": "Invoice record and reconciliation outcome saved successfully."
        })

        return {
            "invoice_id": invoice_record.invoice_id,
            "original_filename": file.filename,
            "pages": page_count,
            "extraction_method": method,
            "extracted_text": extracted_text,
            "invoice_data": invoice_data.model_dump(),
            "decision": decision,
            "saved_to_database": True,
            "processing_trace": processing_trace
        }

    finally:
        db.close()


@app.get("/api/invoices")
def get_invoices():
    db = SessionLocal()

    try:
        invoices = db.query(Invoice).order_by(
            Invoice.id.desc()
        ).all()

        return [
            {
                "invoice_id": invoice.invoice_id,
                "file_name": invoice.file_name,
                "vendor_name": invoice.vendor_name,
                "invoice_number": invoice.invoice_number,
                "po_reference": invoice.po_reference,
                "total": invoice.total,
                "status": invoice.status
            }
            for invoice in invoices
        ]

    finally:
        db.close()


@app.get("/api/dashboard")
def get_dashboard():
    db = SessionLocal()

    try:
        invoices = db.query(Invoice).all()

        total = len(invoices)

        approved = sum(
            1 for invoice in invoices
            if invoice.status == "APPROVED"
        )

        rejected = sum(
            1 for invoice in invoices
            if invoice.status == "REJECTED"
        )

        manual_review = sum(
            1 for invoice in invoices
            if invoice.status == "MANUAL_REVIEW"
        )

        approval_rate = (
            round((approved / total) * 100, 2)
            if total else 0
        )

        return {
            "total_invoices": total,
            "approved": approved,
            "rejected": rejected,
            "manual_review": manual_review,
            "approval_rate": approval_rate
        }

    finally:
        db.close()
