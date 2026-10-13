import math
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from app.core.exceptions import CertificateGenerationError


def _draw_polygon(
    c: canvas.Canvas,
    points: list[tuple[float, float]],
    fill_color: colors.Color | None = None,
    stroke_color: colors.Color | None = None,
    line_width: float = 1.0,
) -> None:
    """Draws a closed polygon on the canvas with optional fill and stroke."""
    c.saveState()
    if stroke_color is not None:
        c.setStrokeColor(stroke_color)
        c.setLineWidth(line_width)
    if fill_color is not None:
        c.setFillColor(fill_color)
    p = c.beginPath()
    p.moveTo(points[0][0], points[0][1])
    for pt in points[1:]:
        p.lineTo(pt[0], pt[1])
    p.close()
    c.drawPath(p, fill=1 if fill_color is not None else 0, stroke=1 if stroke_color is not None else 0)
    c.restoreState()


def _draw_star(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    r_outer: float,
    r_inner: float,
    points: int = 5,
    fill_color: colors.Color | None = None,
    stroke_color: colors.Color | None = None,
    line_width: float = 0.5,
) -> None:
    """Draws a geometric star centered at (cx, cy)."""
    angle = math.pi / points
    pts = []
    start_angle = math.pi / 2
    for i in range(2 * points):
        r = r_outer if i % 2 == 0 else r_inner
        a = start_angle + i * angle
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    _draw_polygon(c, pts, fill_color=fill_color, stroke_color=stroke_color, line_width=line_width)


def _draw_diamond(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    size: float,
    fill_color: colors.Color | None = None,
    stroke_color: colors.Color | None = None,
    line_width: float = 0.5,
) -> None:
    """Draws a decorative diamond centered at (cx, cy)."""
    pts = [(cx, cy + size), (cx + size, cy), (cx, cy - size), (cx - size, cy)]
    _draw_polygon(c, pts, fill_color=fill_color, stroke_color=stroke_color, line_width=line_width)


def generate_certificate(
    recipient_name: str,
    course_name: str | None = None,
    issue_date: str = "",
    output_path: str | Path | None = None,
    course_title: str | None = None,
    certificate_id: str | None = None,
    **kwargs,
) -> Path:
    """
    Generates a professional, portfolio-grade PDF certificate with classic styling.
    Supports both `course_title` and `course_name`, `certificate_id`, and dynamic font fitting.
    """
    # Resolve course title and certificate ID
    resolved_course_title = course_title if course_title is not None else (course_name or "")
    
    if output_path is not None:
        output_path = Path(output_path)
    else:
        fallback_stem = certificate_id or "certificate"
        output_path = Path(f"{fallback_stem}.pdf")

    # Extract certificate ID from parameter or fallback to output filename stem
    effective_cert_id = certificate_id or output_path.stem

    # Ensure parent directories exist
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise CertificateGenerationError(f"Could not create directory for {output_path}: {e}")

    try:
        # 1. Page Setup: Landscape letter
        page_size = landscape(letter)
        width, height = page_size
        center_x = width / 2.0
        c = canvas.Canvas(str(output_path), pagesize=page_size)

        # Palette: Deep Navy, Antique Gold, Bronze, Slate/Charcoal
        color_navy = colors.HexColor("#102A45")
        color_gold = colors.HexColor("#C5A059")
        color_bronze = colors.HexColor("#B8860B")
        color_deep_bronze = colors.HexColor("#8C6818")
        color_slate_dark = colors.HexColor("#0F172A")
        color_slate_muted = colors.HexColor("#475569")
        color_slate_light = colors.HexColor("#64748B")
        color_rule = colors.HexColor("#94A3B8")
        color_gold_tint = colors.HexColor("#E2D1B3")

        # 2. Borders & Corner Styling
        # Outer double-line border
        c.saveState()
        c.setStrokeColor(color_navy)
        c.setLineWidth(3.0)
        c.rect(28, 28, width - 56, height - 56)

        c.setStrokeColor(color_gold)
        c.setLineWidth(1.0)
        c.rect(36, 36, width - 72, height - 72)

        # Hairline inner accent border
        c.setStrokeColor(color_gold_tint)
        c.setLineWidth(0.5)
        c.rect(40, 40, width - 80, height - 80)
        c.restoreState()

        # Ornamental corner diamonds
        for cx, cy in [(48, 48), (width - 48, 48), (48, height - 48), (width - 48, height - 48)]:
            _draw_diamond(c, cx, cy, size=4.0, fill_color=color_gold, stroke_color=color_bronze)

        # 3. Top Decorative Motif
        motif_y = 532
        _draw_diamond(c, center_x, motif_y, size=4.0, fill_color=color_gold, stroke_color=color_bronze)
        _draw_diamond(c, center_x - 16, motif_y, size=2.5, fill_color=color_gold, stroke_color=color_bronze)
        _draw_diamond(c, center_x + 16, motif_y, size=2.5, fill_color=color_gold, stroke_color=color_bronze)
        c.saveState()
        c.setStrokeColor(color_gold)
        c.setLineWidth(0.75)
        c.line(center_x - 110, motif_y, center_x - 26, motif_y)
        c.line(center_x + 26, motif_y, center_x + 110, motif_y)
        c.restoreState()

        # 4. Header: 'Certificate of Achievement'
        c.setFont("Helvetica-Bold", 34)
        c.setFillColor(color_navy)
        c.drawCentredString(center_x, 488, "Certificate of Achievement")

        # Title underline flourish
        flourish_y = 474
        c.saveState()
        c.setStrokeColor(color_gold)
        c.setLineWidth(0.75)
        c.line(center_x - 80, flourish_y, center_x - 10, flourish_y)
        c.line(center_x + 10, flourish_y, center_x + 80, flourish_y)
        c.restoreState()
        _draw_diamond(c, center_x, flourish_y, size=3.0, fill_color=color_gold, stroke_color=color_bronze)

        # 5. Subtitle
        c.setFont("Helvetica-Oblique", 13)
        c.setFillColor(color_slate_muted)
        c.drawCentredString(center_x, 442, "In honor of your outstanding performance we hereby present")

        # 6. Recipient Name: Prominently rendered with dynamic font scaling
        max_name_width = width - 180
        name_font_size = 38
        c.setFont("Helvetica-Bold", name_font_size)
        while stringWidth(recipient_name, "Helvetica-Bold", name_font_size) > max_name_width and name_font_size > 12:
            name_font_size -= 1
            c.setFont("Helvetica-Bold", name_font_size)

        c.setFillColor(color_slate_dark)
        c.drawCentredString(center_x, 384, recipient_name)

        # Clean horizontal rule positioned under recipient name
        name_width = stringWidth(recipient_name, "Helvetica-Bold", name_font_size)
        rule_width = min(max(name_width + 80, 300), 540)
        rule_y = 368
        c.saveState()
        c.setStrokeColor(color_gold)
        c.setLineWidth(1.25)
        c.line(center_x - rule_width / 2.0, rule_y, center_x + rule_width / 2.0, rule_y)
        c.restoreState()
        _draw_diamond(c, center_x, rule_y, size=3.5, fill_color=color_gold, stroke_color=color_bronze)

        # 7. Course & Context
        c.setFont("Helvetica", 13)
        c.setFillColor(color_slate_muted)
        c.drawCentredString(center_x, 332, "with this certificate of recognition for your excellence")

        # Dynamic Course Title
        max_course_width = width - 180
        course_font_size = 22
        c.setFont("Helvetica-Bold", course_font_size)
        while stringWidth(resolved_course_title, "Helvetica-Bold", course_font_size) > max_course_width and course_font_size > 12:
            course_font_size -= 1
            c.setFont("Helvetica-Bold", course_font_size)

        c.setFillColor(color_navy)
        c.drawCentredString(center_x, 294, resolved_course_title)

        # Issue Date under course context (if provided)
        if issue_date:
            c.setFont("Helvetica-Oblique", 12)
            c.setFillColor(color_slate_light)
            c.drawCentredString(center_x, 264, f"Issued on {issue_date}")

        # 8. Footer & Signatures
        line_y = 125
        # Left signature/date block: 'Date'
        c.saveState()
        c.setStrokeColor(color_rule)
        c.setLineWidth(1.0)
        c.line(100, line_y, 270, line_y)
        c.restoreState()
        if issue_date:
            c.setFont("Helvetica", 11)
            c.setFillColor(color_slate_dark)
            c.drawCentredString(185, line_y + 10, str(issue_date))
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(color_slate_light)
        c.drawCentredString(185, line_y - 16, "DATE")

        # Right signature block: 'Signature'
        c.saveState()
        c.setStrokeColor(color_rule)
        c.setLineWidth(1.0)
        c.line(width - 270, line_y, width - 100, line_y)

        # Stylized calligraphic signature flourish above line
        c.setStrokeColor(color_navy)
        c.setLineWidth(1.2)
        sig_p = c.beginPath()
        sig_p.moveTo(width - 240, line_y + 9)
        sig_p.curveTo(width - 220, line_y + 25, width - 205, line_y + 3, width - 185, line_y + 17)
        sig_p.curveTo(width - 175, line_y + 24, width - 165, line_y + 7, width - 145, line_y + 13)
        c.drawPath(sig_p, stroke=1, fill=0)
        c.restoreState()

        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(color_slate_light)
        c.drawCentredString(width - 185, line_y - 16, "SIGNATURE")

        # 9. Bottom Center Emblem / Badge Placeholder
        center_y = 130
        badge_r = 36.0

        # Ribbon tails behind seal
        _draw_polygon(
            c,
            [(383, 108), (370, 68), (379, 76), (388, 68), (391, 108)],
            fill_color=color_bronze,
            stroke_color=color_deep_bronze,
            line_width=0.75,
        )
        _draw_polygon(
            c,
            [(401, 108), (404, 68), (413, 76), (422, 68), (409, 108)],
            fill_color=color_bronze,
            stroke_color=color_deep_bronze,
            line_width=0.75,
        )

        # Concentric seal circles
        c.saveState()
        # Outer rim
        c.setFillColor(colors.HexColor("#FDFBF7"))
        c.setStrokeColor(color_bronze)
        c.setLineWidth(2.0)
        c.circle(center_x, center_y, badge_r, stroke=1, fill=1)

        # Dotted/dashed coin edge ring
        c.setStrokeColor(color_gold)
        c.setLineWidth(0.75)
        c.setDash([2, 2])
        c.circle(center_x, center_y, badge_r - 5, stroke=1, fill=0)

        # Inner warm parchment circle
        c.setDash([])
        c.setFillColor(colors.HexColor("#F5EEDC"))
        c.setStrokeColor(color_bronze)
        c.setLineWidth(1.0)
        c.circle(center_x, center_y, badge_r - 10, stroke=1, fill=1)
        c.restoreState()

        # Center star inside emblem
        _draw_star(
            c,
            center_x,
            center_y + 3,
            r_outer=8.5,
            r_inner=3.6,
            points=5,
            fill_color=color_bronze,
            stroke_color=color_deep_bronze,
        )

        # Emblem curved / centered labels
        c.setFont("Helvetica-Bold", 5.5)
        c.setFillColor(colors.HexColor("#7A5B18"))
        c.drawCentredString(center_x, center_y + 14, "★ SEAL OF ★")
        c.drawCentredString(center_x, center_y - 14, "EXCELLENCE")

        # 10. Certificate ID Footer
        if effective_cert_id:
            c.setFont("Helvetica", 8.5)
            c.setFillColor(color_slate_light)
            c.drawCentredString(center_x, 46, f"Certificate ID: {effective_cert_id}")

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
