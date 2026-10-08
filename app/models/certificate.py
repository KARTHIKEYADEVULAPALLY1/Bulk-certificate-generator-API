import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.enums import CertificateStatus

class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), index=True)
    recipient_name = Column(String, nullable=False)
    recipient_email = Column(String, nullable=False)
    course_name = Column(String, nullable=False)
    issue_date = Column(String, nullable=False)
    status = Column(Enum(CertificateStatus), default=CertificateStatus.PENDING)
    file_path = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="certificates")
