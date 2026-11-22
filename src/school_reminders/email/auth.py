"""Local OAuth authorization and token persistence for read-only Gmail access."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def load_credentials(credentials_path: Path | None, token_path: Path) -> Credentials:
    """Reuse or refresh a token, or authorize interactively when none is usable.

    Opens a browser and a local callback server only when authorization is
    necessary. Writes a new token after authorization or refresh. Paths are
    relative to the caller's working directory unless absolute.
    OAuth, refresh, and filesystem failures propagate to the caller.
    """
    # Keep Google dependencies out of parsing and command help paths.
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    else:
        if credentials_path is None:
            raise ValueError("Unattended Gmail access requires a locally authorized refresh token.")
        if not credentials_path.is_file():
            raise FileNotFoundError(
                f"OAuth credentials missing: {credentials_path}. See README.md for setup."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        credentials = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials
