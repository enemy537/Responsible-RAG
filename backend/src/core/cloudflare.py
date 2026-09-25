"""Cloudflare AI API client."""

import os

import requests


class Cloudflare:
    """Thin wrapper around Cloudflare Workers AI REST API."""

    def __init__(
        self,
        api_token: str | None = None,
        account_id: str | None = None,
    ) -> None:
        self.api_token = api_token or os.getenv("CLOUDFLARE_API_TOKEN", "")
        self.account_id = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        if not self.api_token or not self.account_id:
            raise ValueError(
                "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be set"
            )
        self._base = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/"
        )

    def _post(self, model: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
        resp = requests.post(
            f"{self._base}{model}",
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": content_type,
            },
            data=data,
            timeout=600,
        )
        try:
            return resp.json()
        except ValueError:
            return {"status_code": resp.status_code, "text": resp.text}
