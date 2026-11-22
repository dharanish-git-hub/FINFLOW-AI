"""
Generates realistic sample PDF invoices for FinFlow AI testing scenarios:
1. Valid Clean Invoice (Matches PO-2026-001)
2. PO Mismatch Invoice (Different quantities/unit price against PO-2026-002)
3. Tax Calculation Error Invoice (Subtotal + Wrong Tax != Total)
4. Unverified/Fraudulent Vendor Invoice (Vendor not in database)
"""

import os
from typing import Tuple, Dict, Any
import pymupdf as fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB limit


def extract_text_with_diagnostics(pdf_bytes: bytes, filename: str = "document.pdf") -> Dict[str, Any]:
    """
    Extracts text from PDF with full diagnostics:
    - Validates file size and structure
    - Detects empty, corrupted or password-protected PDFs
    - Preserves page boundaries: '--- Page N ---'
    - Detects scanned documents where text is absent
    """
    if not pdf_bytes:
        return {
            "success": False,
            "error_type": "EMPTY_FILE",
            "message": "Uploaded file is 0 bytes (empty document).",
            "text": "",
            "pages": 0,
            "is_scanned": False,
        }

    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        return {
            "success": False,
            "error_type": "FILE_TOO_LARGE",
            "message": f"File size exceeds the 20MB limit ({len(pdf_bytes) / (1024*1024):.2f} MB).",
            "text": "",
            "pages": 0,
            "is_scanned": False,
        }

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return {
            "success": False,
            "error_type": "CORRUPTED_FILE",
            "message": f"Invalid or corrupted PDF file: {str(e)}",
            "text": "",
            "pages": 0,
            "is_scanned": False,
        }

    if doc.is_encrypted:
        doc.close()
        return {
            "success": False,
            "error_type": "PASSWORD_PROTECTED",
            "message": "The PDF document is password-protected/encrypted. Please unlock the file before uploading.",
            "text": "",
            "pages": 0,
            "is_scanned": False,
        }

    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        return {
            "success": False,
            "error_type": "NO_PAGES",
            "message": "The PDF document contains 0 pages.",
            "text": "",
            "pages": 0,
            "is_scanned": False,
        }

    page_texts = []
    total_text_length = 0

    for idx, page in enumerate(doc):
        text = page.get_text() or ""
        total_text_length += len(text.strip())
        page_texts.append(f"--- Page {idx + 1} ---\n{text.strip()}")

    doc.close()

    full_text = "\n\n".join(page_texts).strip()

    # Detect scanned documents (almost no characters across multiple pages)
    # If average characters per page is less than 30, it is a scanned image or empty
    is_scanned = (total_text_length / total_pages) < 30

    if is_scanned:
        return {
            "success": False,
            "error_type": "SCANNED_DOCUMENT",
            "message": "Scanned document detected: No extractable text found in this PDF. OCR is required to process this document. FinFlow AI does not fabricate data from non-extractable scans.",
            "text": "",
            "pages": total_pages,
            "is_scanned": True,
        }

    return {
        "success": True,
        "error_type": None,
        "message": f"Successfully extracted text from {total_pages} page(s).",
        "text": full_text,
        "pages": total_pages,
        "is_scanned": False,
    }


def create_invoice_pdf(
    file_path: str,
    invoice_number: str,
    vendor_name: str,
    vendor_address: str,
    vendor_tax_id: str,
    po_number: str,
    invoice_date: str,
    due_date: str,
    line_items: list,
    subtotal: float,
    tax_amount: float,
    total_amount: float,
    payment_terms: str = "Net 30",
    bank_account: str = "US-ACH-121000358-992384"
):
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    doc = SimpleDocTemplate(
        file_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A')
    )
    bold_style = ParagraphStyle(
        'BoldMeta',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        fontName='Helvetica-Bold'
    )
    normal_style = ParagraphStyle(
        'NormalMeta',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155')
    )

    story = []

    # Header section
    header_data = [
        [
            Paragraph(f"<b>{vendor_name}</b><br/>{vendor_address}<br/>Tax ID: {vendor_tax_id}", normal_style),
            Paragraph(f"<font size=18 color='#1E293B'><b>INVOICE</b></font><br/><b>Invoice #:</b> {invoice_number}<br/><b>Date:</b> {invoice_date}<br/><b>Due Date:</b> {due_date}", normal_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[320, 220])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))

    # Bill To & PO info
    bill_data = [
        [
            Paragraph("<b>BILLED TO:</b><br/>FinFlow Enterprise Operations<br/>100 Wall Street, Suite 500<br/>New York, NY 10005", normal_style),
            Paragraph(f"<b>PURCHASE ORDER:</b> {po_number}<br/><b>Payment Terms:</b> {payment_terms}<br/><b>Remittance:</b> {bank_account}", normal_style)
        ]
    ]
    bill_table = Table(bill_data, colWidths=[320, 220])
    bill_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(bill_table)
    story.append(Spacer(1, 15))

    # Line Items Table
    table_rows = [
        [
            Paragraph("<b>Description</b>", bold_style),
            Paragraph("<b>Qty</b>", bold_style),
            Paragraph("<b>Unit Price</b>", bold_style),
            Paragraph("<b>Amount</b>", bold_style)
        ]
    ]
    for desc, qty, price, amt in line_items:
        table_rows.append([
            Paragraph(desc, normal_style),
            f"{qty}",
            f"${price:,.2f}",
            f"${amt:,.2f}"
        ])

    items_table = Table(table_rows, colWidths=[280, 50, 100, 110])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 15))

    # Summary Totals
    totals_data = [
        ["", "Subtotal:", f"${subtotal:,.2f}"],
        ["", "Tax / VAT (8%):", f"${tax_amount:,.2f}"],
        ["", "Total Due:", f"${total_amount:,.2f}"],
    ]
    totals_table = Table(totals_data, colWidths=[330, 100, 110])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (1, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (1, -1), (-1, -1), 10),
        ('LINEABOVE', (1, -1), (-1, -1), 1, colors.HexColor('#0F172A')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(totals_table)

    # Footer note
    story.append(Spacer(1, 25))
    footer_p = Paragraph("<font color='#64748B' size=8>This is an automated invoice document generated for enterprise procurement verification. Please route remittance notifications to accounts payable.</font>", normal_style)
    story.append(footer_p)

    doc.build(story)
    return file_path


def generate_all_sample_invoices(output_dir="sample_data"):
    os.makedirs(output_dir, exist_ok=True)
    generated = []

    # 1. Clean Valid Invoice (Matches PO-2026-001)
    p1 = os.path.join(output_dir, "invoice_valid_apex.pdf")
    create_invoice_pdf(
        file_path=p1,
        invoice_number="INV-2026-801",
        vendor_name="Apex Cloud Services Inc.",
        vendor_address="100 Silicon Way, San Jose, CA 95113",
        vendor_tax_id="US-EIN-94-3829101",
        po_number="PO-2026-001",
        invoice_date="2026-11-15",
        due_date="2026-12-15",
        line_items=[
            ("Cloud Compute Enterprise Tier (Monthly)", 1, 8000.00, 8000.00),
            ("Dedicated High-Speed Interconnect", 1, 3500.00, 3500.00),
            ("Priority Support SLA", 1, 1000.00, 1000.00),
        ],
        subtotal=12500.00,
        tax_amount=1000.00,
        total_amount=13500.00,
    )
    generated.append(p1)

    # 2. PO Mismatch Invoice (Matches PO-2026-002, but billed $1,500/unit instead of $1,200)
    p2 = os.path.join(output_dir, "invoice_mismatch_logistics.pdf")
    create_invoice_pdf(
        file_path=p2,
        invoice_number="INV-2026-902",
        vendor_name="Global Logistics & Freight LLC",
        vendor_address="450 Cargo Blvd, Chicago, IL 60601",
        vendor_tax_id="US-EIN-12-8849102",
        po_number="PO-2026-002",
        invoice_date="2026-11-16",
        due_date="2026-12-16",
        line_items=[
            ("Interstate Freight - 4 Containers (Surplus Fuel Surcharge)", 4, 1500.00, 6000.00),
        ],
        subtotal=6000.00,
        tax_amount=480.00,
        total_amount=6480.00, # PO expects $4,800 + $384 = $5,184
    )
    generated.append(p2)

    # 3. Tax Math Error Invoice (CyberShield PO-2026-003, Subtotal $24,000, Tax says $1,200 instead of $1,920, Total wrong)
    p3 = os.path.join(output_dir, "invoice_tax_error_cybershield.pdf")
    create_invoice_pdf(
        file_path=p3,
        invoice_number="INV-2026-303",
        vendor_name="CyberShield Security Corp",
        vendor_address="700 Defense Pkwy, Arlington, VA 22202",
        vendor_tax_id="US-EIN-88-2940192",
        po_number="PO-2026-003",
        invoice_date="2026-11-17",
        due_date="2026-12-17",
        line_items=[
            ("SOC 2 Type II Continuous Audit Tool License (Annual)", 1, 20000.00, 20000.00),
            ("Penetration Testing & Red Teaming Pack", 1, 4000.00, 4000.00),
        ],
        subtotal=24000.00,
        tax_amount=1200.00, # Deliberate math error (should be $1,920 at 8% or subtotal + tax mismatch)
        total_amount=25920.00, # Total doesn't equal subtotal + tax listed ($24,000 + $1,200 = $25,200)
    )
    generated.append(p3)

    # 4. Unknown / Blacklisted Vendor (Suspicious Shell Entity)
    p4 = os.path.join(output_dir, "invoice_unknown_shell.pdf")
    create_invoice_pdf(
        file_path=p4,
        invoice_number="INV-FRAUD-999",
        vendor_name="Unknown Off-Shore Consultancy Ltd.",
        vendor_address="PO Box 881, Grand Cayman",
        vendor_tax_id="US-EIN-00-0000000",
        po_number="PO-NONEXISTENT-999",
        invoice_date="2026-11-18",
        due_date="2026-11-20", # Immediate due date
        line_items=[
            ("Strategic Offshore Advisory Retainer", 1, 18500.00, 18500.00),
        ],
        subtotal=18500.00,
        tax_amount=0.00,
        total_amount=18500.00,
        bank_account="KY-WIRE-009923-00192"
    )
    generated.append(p4)

    return generated


if __name__ == "__main__":
    files = generate_all_sample_invoices()
    print(f"Generated {len(files)} sample invoice PDFs in sample_data/")
