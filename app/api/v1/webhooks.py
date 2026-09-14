"""Webhook API routes.

Receives and verifies GitHub webhook events.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.integrations.github.webhooks import verify_webhook_signature
from app.services.webhook_service import webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github", status_code=status.HTTP_200_OK)
async def handle_github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Handle incoming GitHub webhook events with HMAC-SHA256 signature verification."""
    payload_bytes = await request.body()

    webhook_secret = settings.github_webhook_secret
    if webhook_secret:
        if not verify_webhook_signature(payload_bytes, x_hub_signature_256, webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing webhook signature",
            )

    try:
        payload: dict[str, Any] = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON payload",
        ) from exc

    return await webhook_service.process_github_event(db, event=x_github_event, payload=payload)
