"""Briefing ORM model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Briefing(Base):
    __tablename__ = "briefings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    overall_risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_alert_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    llm_model: Mapped[str | None] = mapped_column(String(128))
