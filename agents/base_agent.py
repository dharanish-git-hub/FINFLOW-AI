"""
Base class and structured Pydantic schemas for FinFlow AI Agents.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class InvoiceItemSchema(BaseModel):
    description: str = Field(default="", description="Description of the goods or services")
    quantity: float = Field(default=1.0, description="Quantity billed")
    unit_price: float = Field(default=0.0, description="Unit price per item")
    amount: float = Field(default=0.0, description="Total extended line item amount/price")

    @property
    def total_price(self) -> float:
        """Alias for backward compatibility with database and existing services."""
        return self.amount if self.amount else (self.quantity * self.unit_price)


class InvoiceExtractionResult(BaseModel):
    invoice_number: str = Field(default="", description="Unique invoice identifier")
    vendor_name: str = Field(default="", description="Name of the invoicing vendor")
    vendor_address: Optional[str] = Field(default="", description="Vendor address")
    vendor_tax_id: Optional[str] = Field(default="", description="Vendor EIN/Tax ID")
    purchase_order_number: Optional[str] = Field(default="", description="Referenced Purchase Order number")
    invoice_date: str = Field(default="", description="Date the invoice was generated (YYYY-MM-DD)")
    due_date: Optional[str] = Field(default="", description="Payment due date (YYYY-MM-DD)")
    currency: str = Field(default="USD", description="Currency symbol or 3-letter code")
    line_items: List[InvoiceItemSchema] = Field(default_factory=list, description="Itemized invoice items")
    subtotal: float = Field(default=0.0, description="Sum of line items before tax")
    tax_amount: float = Field(default=0.0, description="Tax or VAT amount")
    total_amount: float = Field(default=0.0, description="Final total balance due")
    payment_terms: Optional[str] = Field(default="Net 30", description="Payment terms")
    bank_account: Optional[str] = Field(default="", description="Vendor bank or remittance detail")
    confidence_score: float = Field(default=0.95, description="Extraction confidence score from 0 to 1")

    @property
    def po_number(self) -> Optional[str]:
        """Alias for purchase_order_number for backward compatibility."""
        return self.purchase_order_number


class VerificationResult(BaseModel):
    vendor_verified: bool
    vendor_id: Optional[str] = None
    vendor_status: str = "UNKNOWN"
    po_matched: bool = False
    po_number: Optional[str] = None
    po_total: Optional[float] = None
    amount_mismatch: bool = False
    discrepancy_amount: float = 0.0
    line_item_matches: List[dict] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


class FinancialIntelligenceResult(BaseModel):
    is_duplicate: bool = False
    duplicate_invoice_id: Optional[int] = None
    tax_error: bool = False
    calculated_tax: float = 0.0
    tax_discrepancy: float = 0.0
    math_error: bool = False
    is_suspicious: bool = False
    anomaly_flags: List[str] = Field(default_factory=list)
    risk_score: float = 0.0  # 0.0 (Clean) to 1.0 (Critical Risk)


class AgentAuditLog(BaseModel):
    agent_name: str
    action: str
    level: str = "INFO"
    message: str
    payload: Optional[dict] = None
