"""GitHub Webhooks signature verification and utilities."""

import hashlib
import hmac


def verify_webhook_signature(
    payload_bytes: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify GitHub webhook payload signature against HMAC-SHA256 digest.

    GitHub passes the signature in the `X-Hub-Signature-256` header formatted as:
    `sha256=<hex_digest>`
    """
    if not signature_header or not secret:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    received_signature = signature_header[len(prefix) :]
    computed_signature = hmac.new(
        secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_signature, received_signature)
