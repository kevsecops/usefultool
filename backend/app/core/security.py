"""Security utilities."""

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def verify_admin_token(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    settings = get_settings()
    if not settings.admin_token or not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )
