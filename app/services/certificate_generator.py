from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from app.core.exceptions import CertificateGenerationError

def generate_certificate(recipient_name: str, course_name: str, issue_date: str, output_path: str | Path) -> Path:
    """
    Generates a PDF certificate for a recipient.
    """
    output_path = Path(output_path)
    
    # Ensure parent directories exist
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise CertificateGenerationError(f"Could not create directory for {output_path}: {e}")

    # Extract certificate ID from the filename (assuming {certificate_id}.pdf)
    certificate_id = output_path.stem

    try:
        width, height = landscape(A4)
        c = canvas.Canvas(str(output_path), pagesize=landscape(A4))

        # Margins and Border
        margin = 40
        c.setLineWidth(4)
        c.rect(margin, margin, width - 2 * margin, height - 2 * margin)

        # Title
        c.setFont("Helvetica-Bold", 40)
        c.drawCentredString(width / 2.0, height - 140, "Certificate of Completion")

        # Subtitle
        c.setFont("Helvetica", 18)
        c.drawCentredString(width / 2.0, height - 200, "This is to certify that")

        # Recipient Name - Dynamically shrink font if it's too long
        max_name_width = width - 4 * margin
        name_font_size = 50
        c.setFont("Helvetica-Bold", name_font_size)
        
        while stringWidth(recipient_name, "Helvetica-Bold", name_font_size) > max_name_width and name_font_size > 12:
            name_font_size -= 2
            c.setFont("Helvetica-Bold", name_font_size)
            
        c.drawCentredString(width / 2.0, height - 280, recipient_name)

        # Course prefix
        c.setFont("Helvetica", 18)
        c.drawCentredString(width / 2.0, height - 340, "has successfully completed the course:")

        # Course Name
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(width / 2.0, height - 390, course_name)

        # Date
        c.setFont("Helvetica", 14)
        c.drawCentredString(width / 2.0, height - 450, f"Date: {issue_date}")

        # Footer (Certificate ID)
        c.setFont("Helvetica", 10)
        c.drawCentredString(width / 2.0, margin + 20, f"Certificate ID: {certificate_id}")

        c.showPage()
        c.save()
        
        return output_path
    except Exception as e:
        # Cleanup partial file if generation failed
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception:
                pass
        raise CertificateGenerationError(f"Failed to generate certificate: {e}")
