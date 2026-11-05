
from app.database import Base, engine, SessionLocal
from app.models import Vendor, PurchaseOrder

# Create database tables
Base.metadata.create_all(bind=engine)

db = SessionLocal()

try:
    # Create or retrieve vendor
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
        db.commit()
        db.refresh(vendor)

    # Purchase order records
    purchase_orders = [
        {
            "po_number": "PO-5021",
            "total_amount": 200000.0,
            "tolerance_percent": 3.0
        },
        {
            "po_number": "PO-5022",
            "total_amount": 100000.0,
            "tolerance_percent": 3.0
        }
    ]

    for po_data in purchase_orders:
        existing_po = db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number == po_data["po_number"]
        ).first()

        if not existing_po:
            po = PurchaseOrder(
                po_number=po_data["po_number"],
                vendor_id=vendor.id,
                total_amount=po_data["total_amount"],
                invoiced_amount=0.0,
                currency="INR",
                tolerance_percent=po_data["tolerance_percent"]
            )
            db.add(po)

    db.commit()

    print("Database seeded successfully!")
    print("Vendor: ABC Technologies Pvt. Ltd.")
    print("PO-5021: INR 200,000")
    print("PO-5022: INR 100,000")

except Exception as error:
    db.rollback()
    print("Database seeding failed:", error)

finally:
    db.close()
