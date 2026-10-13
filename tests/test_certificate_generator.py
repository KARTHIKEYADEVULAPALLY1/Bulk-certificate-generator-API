import tempfile
from pathlib import Path
import pytest
from app.services.certificate_generator import generate_certificate
from app.core.exceptions import CertificateGenerationError

def test_generate_certificate_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "job-123" / "cert-456.pdf"
        
        result = generate_certificate(
            recipient_name="John Doe",
            course_name="FastAPI Mastery",
            issue_date="2026-10-07",
            output_path=output_path
        )
        
        # Verify file is created and returned
        assert result.exists()
        assert result == output_path
        
        # Verify file is not empty
        assert result.stat().st_size > 0
        
        # Verify it has the PDF header
        with open(result, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-"

def test_generate_certificate_long_name():
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "job-123" / "cert-789.pdf"
        # Create a name that is exceptionally long to trigger the font shrinking logic
        long_name = "Wolfeschlegelsteinhausenbergerdorff " * 5
        
        result = generate_certificate(
            recipient_name=long_name,
            course_name="FastAPI Mastery",
            issue_date="2026-10-07",
            output_path=output_path
        )
        
        assert result.exists()
        with open(result, "rb") as f:
            assert f.read(5) == b"%PDF-"
