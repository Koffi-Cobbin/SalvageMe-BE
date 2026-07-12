"""
Thin server-to-server client for FileForge (https://github.com/Koffi-Cobbin/FileForge).

This is the ONLY module in the codebase allowed to make HTTP calls to
FileForge. No view or serializer should call `requests` against
FILEFORGE_BASE_URL directly — go through `FileForgeClient` so there is a
single seam to mock in tests and a single place holding the API key header.

Usage:
    from common.fileforge_client import get_fileforge_client, FileForgeError

    client = get_fileforge_client()
    try:
        result = client.upload_file(file_obj, filename="cover.jpg", content_type="image/jpeg")
    except FileForgeError:
        # translate into a clean 502-style API response — never create a
        # ListingPhoto/avatar row with no backing file.
        ...
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import BinaryIO

import requests
from django.conf import settings

logger = logging.getLogger("salvageme")


class FileForgeError(Exception):
    """Raised for any FileForge failure: network error, timeout, non-2xx response."""


@dataclass(frozen=True)
class FileForgeUploadResult:
    file_id: int
    url: str
    provider: str | None = None


class FileForgeClient:
    """
    Server-to-server client wrapping FileForge's Storage API.

    All upload/delete calls in this codebase go through an instance of this
    class (obtained via `get_fileforge_client()`), never directly via
    `requests`.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"}

    def upload_file(
        self,
        file_obj: BinaryIO,
        *,
        filename: str,
        content_type: str,
    ) -> FileForgeUploadResult:
        """
        Uploads a file synchronously (`mode: "sync"`) — appropriate for
        listing-photo/avatar sized files, which are small enough to block
        for a single round trip. Raises FileForgeError on any failure so
        the caller can fail the API request cleanly instead of persisting
        a local row with no backing file.
        """
        try:
            response = requests.post(
                f"{self._base_url}/api/files/",
                headers=self._headers(),
                data={"mode": "sync"},
                files={"file": (filename, file_obj, content_type)},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("FileForge upload failed (network error): %s", exc)
            raise FileForgeError(f"FileForge unreachable: {exc}") from exc

        if not response.ok:
            logger.error(
                "FileForge upload failed (status=%s body=%s)",
                response.status_code,
                response.text[:500],
            )
            raise FileForgeError(f"FileForge returned {response.status_code}")

        data = response.json()
        try:
            return FileForgeUploadResult(
                file_id=data["id"],
                url=data["url"],
                provider=data.get("provider"),
            )
        except KeyError as exc:
            logger.error("FileForge upload response missing field %s: %s", exc, data)
            raise FileForgeError(f"Unexpected FileForge response shape: missing {exc}") from exc

    def delete_file(self, file_id: int) -> None:
        """
        Deletes the underlying object in FileForge. Raises FileForgeError
        on failure so callers can decide whether to retry / surface an
        error rather than silently leaving an orphaned remote file.
        """
        try:
            response = requests.delete(
                f"{self._base_url}/api/files/{file_id}/",
                headers=self._headers(),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("FileForge delete failed (network error): %s", exc)
            raise FileForgeError(f"FileForge unreachable: {exc}") from exc

        # 404 is treated as success: the remote file is already gone, which
        # is the desired end state (e.g. reconciliation retrying a delete).
        if not response.ok and response.status_code != 404:
            logger.error(
                "FileForge delete failed (status=%s body=%s)",
                response.status_code,
                response.text[:500],
            )
            raise FileForgeError(f"FileForge returned {response.status_code}")

    def get_file_status(self, file_id: int) -> dict:
        """Used by the daily reconciliation job to check upload state."""
        try:
            response = requests.get(
                f"{self._base_url}/api/files/{file_id}/",
                headers=self._headers(),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise FileForgeError(f"FileForge unreachable: {exc}") from exc

        if not response.ok:
            raise FileForgeError(f"FileForge returned {response.status_code}")

        return response.json()


def get_fileforge_client() -> FileForgeClient:
    """
    Factory so views/services never construct FileForgeClient directly with
    raw settings — keeps the API-key wiring in exactly one place.
    """
    return FileForgeClient(
        base_url=settings.FILEFORGE_BASE_URL,
        api_key=settings.FILEFORGE_API_KEY,
        timeout=settings.FILEFORGE_TIMEOUT_SECONDS,
    )
