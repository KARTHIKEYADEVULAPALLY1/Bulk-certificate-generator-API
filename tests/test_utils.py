import pytest
from app.core.utils import get_certificate_path, sanitize_path_component

def test_sanitize_path_component():
    with pytest.raises(ValueError):
        # Everything gets stripped out, leaving an empty string which raises ValueError
        sanitize_path_component("../..")
        
    assert sanitize_path_component("valid_id-123") == "valid_id-123"

def test_get_certificate_path_safety():
    path = get_certificate_path("job_1", "cert_1")
    assert path.name == "cert_1.pdf"
    
    # Path traversal attempts are blocked by sanitization first, 
    # but the explicit resolve and check also guards against OS symlink attacks.
    # An attempt with only dangerous chars is caught by sanitization
    with pytest.raises(ValueError):
        get_certificate_path("../../../", "cert")
        
    # An attempt with mixed chars is silently cleaned
    safe = get_certificate_path("../../job", "cert")
    assert "job" in str(safe)
    assert ".." not in str(safe)
