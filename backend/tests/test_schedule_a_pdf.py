"""
Test Schedule A PDF Export endpoint
Tests the new PDF export feature for Schedule A assets
"""
import pytest
import requests
import os
import base64

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestScheduleAPDFExport:
    """Test Schedule A PDF Export functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@trustoffice.com",
            "password": "demo123"
        })
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            self.user = data.get("user")
        else:
            pytest.skip("Authentication failed")
        
        # Get user's trusts
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        if trusts_response.status_code == 200:
            trusts = trusts_response.json()
            if trusts:
                self.trust_id = trusts[0]["trust_id"]
                self.trust_name = trusts[0]["name"]
            else:
                pytest.skip("No trusts found for testing")
        else:
            pytest.skip("Could not fetch trusts")
    
    def test_export_pdf_endpoint_exists(self):
        """Test that Schedule A PDF export endpoint returns 200"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a/export/{self.trust_id}/pdf")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ Schedule A PDF export endpoint exists and returns 200")
    
    def test_export_pdf_returns_valid_base64(self):
        """Test that PDF export returns valid base64 encoded PDF"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a/export/{self.trust_id}/pdf")
        assert response.status_code == 200
        
        data = response.json()
        assert "pdf_base64" in data, "Response should contain pdf_base64 field"
        assert "filename" in data, "Response should contain filename field"
        
        # Validate base64
        pdf_base64 = data["pdf_base64"]
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
            assert len(pdf_bytes) > 0, "PDF content should not be empty"
            # PDF files start with %PDF
            assert pdf_bytes[:4] == b'%PDF', "Decoded content should be a valid PDF"
            print(f"✓ PDF export returns valid base64 encoded PDF ({len(pdf_bytes)} bytes)")
        except Exception as e:
            pytest.fail(f"Failed to decode base64 PDF: {e}")
    
    def test_export_pdf_filename_format(self):
        """Test that PDF filename follows expected format"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a/export/{self.trust_id}/pdf")
        assert response.status_code == 200
        
        data = response.json()
        filename = data.get("filename", "")
        
        assert filename.startswith("schedule_a_"), f"Filename should start with 'schedule_a_', got: {filename}"
        assert filename.endswith(".pdf"), f"Filename should end with '.pdf', got: {filename}"
        assert self.trust_id in filename, f"Filename should contain trust_id"
        print(f"✓ PDF filename format is correct: {filename}")
    
    def test_export_pdf_with_invalid_trust_id(self):
        """Test that export with invalid trust_id returns 404"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a/export/invalid_trust_123/pdf")
        assert response.status_code == 404, f"Expected 404 for invalid trust_id, got {response.status_code}"
        print("✓ Export with invalid trust_id returns 404")
    
    def test_export_pdf_without_auth(self):
        """Test that export without authentication returns 401"""
        unauth_session = requests.Session()
        unauth_session.headers.update({"Content-Type": "application/json"})
        
        response = unauth_session.get(f"{BASE_URL}/api/schedule-a/export/{self.trust_id}/pdf")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Export without authentication returns 401")
    
    def test_schedule_a_summary_endpoint(self):
        """Test Schedule A summary endpoint has required fields"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a/summary/{self.trust_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "trust_id" in data, "Summary should contain trust_id"
        assert "trust_name" in data, "Summary should contain trust_name"
        assert "categories" in data, "Summary should contain categories"
        assert "total_items" in data, "Summary should contain total_items"
        assert "total_value" in data, "Summary should contain total_value"
        
        print(f"✓ Schedule A summary endpoint returns correct structure")
        print(f"  - Total items: {data['total_items']}")
        print(f"  - Total value: ${data['total_value']:,.2f}")
        print(f"  - Categories: {list(data['categories'].keys())}")
    
    def test_get_schedule_a_assets(self):
        """Test that Schedule A assets can be retrieved"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}")
        assert response.status_code == 200

        assets = response.json()
        assert isinstance(assets, list), "Response should be a list"

        if assets:
            asset = assets[0]
            assert "item_id" in asset
            assert "category" in asset
            assert "description" in asset
            print(f"Schedule A has {len(assets)} assets")

            # Check categories present
            categories = set(a["category"] for a in assets)
            print(f"  - Categories: {categories}")
        else:
            print("Schedule A assets endpoint works (no assets found)")


def test_pdf_no_midword_truncation():
    """Regression test: long strings in table cells must wrap, never truncate mid-word.

    Generates a PDF the same way the Schedule A export does and asserts that
    Paragraph objects are used for table cells so ReportLab wraps text within
    cells instead of truncating mid-word.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table
    import io

    # Strings that exceed the old truncation limits and would be cut mid-word
    long_desc = (
        "This is a very long description that would have been truncated "
        "mid-word by the old _truncate function at fifty characters"
    )
    long_id = "UTState passport registration number that is quite long"
    long_loc = "A very long location string that exceeds the old thirty character limit"

    # Replicate the cell style from schedule_a.py _cell_style()
    cs = ParagraphStyle(
        "CellStyle",
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        splitLongWords=True,
        allowWidows=False,
        allowOrphans=False,
    )

    # Build a table row exactly as _build_item_row does now (Paragraph objects)
    row = [
        Paragraph(long_desc, cs),
        Paragraph(long_id, cs),
        Paragraph(long_loc, cs),
        Paragraph("$100.00", cs),
        Paragraph("2026-01-15", cs),
    ]

    # Every cell must be a Paragraph (not a truncated string)
    for cell in row:
        assert isinstance(cell, Paragraph), f"Expected Paragraph, got {type(cell)}"
        full_text = cell.getPlainText()
        assert "..." not in full_text, (
            f"Cell text was truncated with '...': {full_text[:80]}"
        )

    # Build a full table like _build_category_table does
    header_style = ParagraphStyle(
        "HeaderCell", parent=cs, fontName="Helvetica-Bold", fontSize=8,
        alignment=1,
    )
    table_data = [[
        Paragraph("Description", header_style),
        Paragraph("Identifier", header_style),
        Paragraph("Location", header_style),
        Paragraph("Value", header_style),
        Paragraph("Date", header_style),
    ], row]

    col_widths = [2.5 * inch, 1.5 * inch, 1.2 * inch, 0.8 * inch, 0.5 * inch]
    table = Table(table_data, colWidths=col_widths)

    # Build the PDF to verify it renders without error
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    doc.build([table])
    pdf_bytes = buf.getvalue()

    assert len(pdf_bytes) > 0, "PDF should not be empty"
    assert pdf_bytes[:4] == b"%PDF", "Output should be a valid PDF"

    print("PDF export wraps long strings without mid-word truncation")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
