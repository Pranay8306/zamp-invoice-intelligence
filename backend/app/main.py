

import os
import uuid
from pathlib import Path

import pymupdf
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.extractor import extract_invoice_data
from app.database import Base, engine, SessionLocal
from app.models import Invoice
from app.reconciliation import evaluate_invoice

app = FastAPI(
    title="Zamp Invoice Intelligence",
    description="Invoice Processing and Reconciliation System",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 15 * 1024 * 1024

TESSERACT_PATH = Path(r"C:\Program Files\Tesseract-OCR")

if TESSERACT_PATH.exists():
    os.environ["PATH"] = (
        str(TESSERACT_PATH) + os.pathsep + os.environ.get("PATH", "")
    )


@app.get("/")
def home():
    return {
        "message": "Zamp Invoice Intelligence API is running!"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "invoice-processing-backend"
    }


@app.post("/api/invoices/upload")
async def upload_invoice(file: UploadFile = File(...)):

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted."
        )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File size exceeds the 15 MB limit."
        )

    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a valid PDF."
        )

    invoice_id = str(uuid.uuid4())
    saved_filename = f"{invoice_id}.pdf"
    saved_path = UPLOAD_DIR / saved_filename
    saved_path.write_bytes(content)

    db = SessionLocal()
    document = None

    try:
        document = pymupdf.open(
            stream=content,
            filetype="pdf"
        )

        if document.needs_pass:
            raise HTTPException(
                status_code=400,
                detail="Password-protected PDFs are not supported."
            )

        extracted_pages = []
        extraction_methods = []
        warnings = []

        for page_number, page in enumerate(document, start=1):

            native_text = page.get_text("text").strip()

            if len(native_text) >= 40:
                extracted_pages.append(native_text)
                extraction_methods.append("text")
                continue

            try:
                text_page = page.get_textpage_ocr(
                    language="eng",
                    dpi=250,
                    full=True
                )

                ocr_text = page.get_text(
                    "text",
                    textpage=text_page
                ).strip()

                if len(ocr_text) > len(native_text):
                    extracted_pages.append(ocr_text)
                    extraction_methods.append("ocr")
                else:
                    extracted_pages.append(native_text)
                    extraction_methods.append("text")

            except Exception as error:
                extracted_pages.append(native_text)
                extraction_methods.append("text")
                warnings.append(
                    f"OCR failed on page {page_number}: {str(error)}"
                )

        document.close()
        document = None

        extracted_text = "\n\n".join(extracted_pages)

        if "ocr" in extraction_methods and "text" in extraction_methods:
            method = "mixed"
        elif "ocr" in extraction_methods:
            method = "ocr"
        elif any(extracted_pages):
            method = "text"
        else:
            method = "none"

        invoice_data = extract_invoice_data(extracted_text)

        # Include PDF extraction warnings in the decision process.
        if warnings:
            invoice_data.extraction_warnings.extend(warnings)

        # Run business reconciliation.
        decision = evaluate_invoice(db, invoice_data)

        # Persist the invoice and its decision.
        invoice_record = Invoice(
            invoice_id=invoice_id,
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

        return {
            "invoice_id": invoice_id,
            "original_filename": file.filename,
            "pages": len(extracted_pages),
            "extraction_method": method,
            "extracted_text": extracted_text,
            "invoice_data": invoice_data.model_dump(),
            "decision": decision,
            "saved_to_database": True
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=f"Could not process invoice: {str(error)}"
        )

    finally:
        if document is not None:
            document.close()
        db.close()


@app.get("/api/invoices")
def get_invoices():

    db = SessionLocal()

    try:
        invoices = db.query(Invoice).order_by(
            Invoice.created_at.desc()
        ).all()

        return [
            {
                "invoice_id": invoice.invoice_id,
                "invoice_number": invoice.invoice_number,
                "vendor_name": invoice.vendor_name,
                "po_reference": invoice.po_reference,
                "total": invoice.total,
                "status": invoice.status,
                "decision_reason": invoice.decision_reason,
                "file_name": invoice.file_name,
                "created_at": invoice.created_at.isoformat()
                if invoice.created_at else None
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
        approved = sum(1 for i in invoices if i.status == "APPROVED")
        rejected = sum(1 for i in invoices if i.status == "REJECTED")
        review = sum(
            1 for i in invoices if i.status == "MANUAL_REVIEW"
        )

        return {
            "total_invoices": total,
            "approved": approved,
            "rejected": rejected,
            "manual_review": review,
            "approval_rate": round(
                approved / total * 100, 2
            ) if total else 0
        }

    finally:
        db.close()
