"""Thin async wrapper over the Splunk SOAR REST API.

Everything the tools need funnels through here so that authentication, TLS
handling, pagination and error shaping live in exactly one place.

The one genuinely surprising part of the SOAR REST API is its filter syntax:
a filter value must arrive wrapped in *literal* double quotes, so filtering on
name ``foo`` means sending ``_filter_name__icontains="foo"`` — quotes included.
``_quoted`` below is the only reason this class exists rather than raw httpx.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .errors import NotFoundError, SoarError


def _quoted(value: Any) -> str:
    """Wrap a filter value in the literal double quotes SOAR's ORM expects."""
    return '"{0}"'.format(str(value).replace('"', '\\"'))


class SoarClient:
    """Async REST client bound to one SOAR instance."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base = settings.soar_url
        self._client = httpx.AsyncClient(
            base_url=f"{self.base}/rest",
            headers={
                "ph-auth-token": settings.soar_token,
                "Accept": "application/json",
                "User-Agent": "splunk-soar-mcp",
            },
            verify=settings.verify,
            timeout=settings.timeout,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- plumbing ----------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        path = path.lstrip("/")
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise SoarError(f"Timed out after {self.settings.timeout}s on {method} /rest/{path}") from exc
        except httpx.HTTPError as exc:
            raise SoarError(f"Could not reach SOAR at {self.base}: {exc}") from exc

        if response.status_code == 404:
            raise NotFoundError(
                f"/rest/{path} returned 404 (no such object or endpoint)",
                status=404,
                body=response.text[:500],
            )
        if not response.is_success:
            raise SoarError(
                f"HTTP {response.status_code} on {method} /rest/{path}: {response.text[:500]}",
                status=response.status_code,
                body=response.text[:2000],
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    async def get(self, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        return await self._request("GET", path, params=clean)

    async def post(self, path: str, payload: Any) -> Any:
        return await self._request("POST", path, json=payload)

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    # -- collection helpers ------------------------------------------------

    def clamp(self, page_size: int | None) -> int:
        if page_size is None:
            return self.settings.default_page_size
        return max(1, min(int(page_size), self.settings.max_page_size))

    async def search(
        self,
        path: str,
        query: str | None = None,
        *,
        field: str = "name",
        page_size: int | None = None,
        page: int = 0,
        sort: str | None = None,
        order: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """List a collection, optionally case-insensitively filtered on ``field``."""
        params: dict[str, Any] = {"page_size": self.clamp(page_size), "page": page}
        if sort:
            params["sort"] = sort
            params["order"] = order or "desc"
        params.update(extra)
        if query:
            params[f"_filter_{field}__icontains"] = _quoted(query)
        result = await self.get(path, **params)
        return result if isinstance(result, dict) else {"data": result}

    async def resolve(
        self, path: str, ident: str | int, *, field: str = "name", label: str = "object"
    ) -> dict[str, Any]:
        """Turn a numeric id *or* a name fragment into a full object.

        Name matching is a case-insensitive ``contains``; an exact match always
        wins over a partial one so ``"Triage"`` picks ``Triage`` over
        ``Triage Backfill``.
        """
        text = str(ident).strip()
        if text.isdigit():
            return await self.get(f"{path}/{text}")

        hits = (await self.search(path, text, field=field, page_size=25)).get("data", [])
        if not hits:
            raise NotFoundError(f"No {label} matching {text!r}")
        exact = [h for h in hits if str(h.get(field, "")).lower() == text.lower()]
        chosen = (exact or hits)[0]
        if chosen.get("id") is None:
            return chosen
        return await self.get(f"{path}/{chosen['id']}")

    async def resolve_id(
        self, path: str, ident: str | int, *, field: str = "name", label: str = "object"
    ) -> int:
        text = str(ident).strip()
        if text.isdigit():
            return int(text)
        return int((await self.resolve(path, text, field=field, label=label))["id"])

    @staticmethod
    def encode_path(*parts: Any) -> str:
        return "/".join(quote(str(p), safe="") for p in parts)
