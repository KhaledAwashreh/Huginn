"""Fragment-to-body opt-out; opening mail links never changes subscription state."""

import secrets
from typing import Annotated
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from huginn.management.presentation.api.dependencies.services import Management

router = APIRouter(prefix="/weekly-digest", include_in_schema=False)
_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'",
}


async def _capability(request: Request) -> tuple[UUID, str]:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].lower()
        != "application/x-www-form-urlencoded"
    ):
        raise HTTPException(status_code=404, detail="Digest link unavailable")
    body = bytearray()
    async for block in request.stream():
        body.extend(block)
        if len(body) > 2048:
            raise HTTPException(status_code=404, detail="Digest link unavailable")
    try:
        fields = parse_qs(
            body.decode("utf-8"),
            strict_parsing=True,
            keep_blank_values=True,
            max_num_fields=2,
        )
        if set(fields) != {"user_id", "token"} or any(
            len(values) != 1 for values in fields.values()
        ):
            raise ValueError("Invalid capability fields")
        return UUID(fields["user_id"][0]), fields["token"][0]
    except ValueError, UnicodeError:
        raise HTTPException(status_code=404, detail="Digest link unavailable") from None


@router.get("/unsubscribe", response_class=HTMLResponse)
def confirm_unsubscribe():
    nonce = secrets.token_urlsafe(18)
    headers = {
        **_HEADERS,
        "Content-Security-Policy": _HEADERS["Content-Security-Policy"]
        + f"; script-src 'nonce-{nonce}'",
    }
    return HTMLResponse(
        f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stop weekly digests</title><main><h1>Stop weekly Huginn digests?</h1>
<p>This pauses weekly email. Your account and saved feedback stay available.</p>
<p id="guidance">Open the unsubscribe link from your digest email to continue.</p>
<form method="post" action="/weekly-digest/unsubscribe">
<input type="hidden" name="user_id"><input type="hidden" name="token">
<button type="submit" disabled>Stop weekly digests</button></form>
<noscript>Enable JavaScript to confirm this email link, or ask the operator to unsubscribe you.</noscript></main>
<script nonce="{nonce}">
const values = new URLSearchParams(location.hash.slice(1));
const user = values.get('user_id') || '';
const token = values.get('token') || '';
history.replaceState(null, '', location.pathname);
if (/^[0-9a-f-]{{36}}$/i.test(user) && /^[0-9a-f]{{64}}$/.test(token)) {{
  const form = document.querySelector('form');
  form.elements.namedItem('user_id').value = user;
  form.elements.namedItem('token').value = token;
  form.querySelector('button').disabled = false;
  document.querySelector('#guidance').textContent = 'Confirm below to stop future weekly digests.';
}}
</script></html>''',
        headers=headers,
    )


@router.post("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(
    capability: Annotated[tuple[UUID, str], Depends(_capability)],
    dependencies: Management,
):
    user_id, token = capability
    if not dependencies.digest_subscriptions_service.unsubscribe_signed(
        user_id, token, dependencies.config.lifecycle_proof_key or ""
    ):
        raise HTTPException(status_code=404, detail="Digest link unavailable")
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Weekly digests stopped</title><main><h1>Weekly digests stopped</h1><p>You can still review recommendations and feedback in Huginn.</p></main></html>',
        headers=_HEADERS,
    )
