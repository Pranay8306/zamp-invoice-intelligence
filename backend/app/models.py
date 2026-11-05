
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    legal_name = Column(String, nullable=False)
    aliases = Column(Text, default="")
    gstin = Column(String, unique=True, nullable=True)
    approved = Column(Boolean, default=True)

    purchase_orders = relationship("PurchaseOrder", back_populates="vendor")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    po_number = Column(String, unique=True, nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    total_amount = Column(Float, nullable=False)
    invoiced_amount = Column(Float, default=0.0)
    currency = Column(String, default="INR")
    tolerance_percent = Column(Float, default=3.0)

    vendor = relationship("Vendor", back_populates="purchase_orders")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(String, unique=True, nullable=False)
    invoice_number = Column(String, nullable=True)
    vendor_name = Column(String, nullable=True)
    po_reference = Column(String, nullable=True)
    invoice_date = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    subtotal = Column(Float, nullable=True)
    tax = Column(Float, nullable=True)
    total = Column(Float, nullable=True)
    status = Column(String, default="PROCESSING")
    decision_reason = Column(Text, default="")
    file_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
