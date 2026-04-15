from __future__ import annotations

import json
from typing import Any, Mapping

import httpx

from intelliforge.exceptions import (
    AuthenticationError,
    IntelliForgeError,
    RateLimitError,
    ValidationError,
)


class Admin:
    """Admin API bound to an :class:`IntelliForge` client (requires ``admin_key``)."""

    def __init__(self, client: IntelliForge) -> None:
        self._c = client

    def stats(self) -> dict[str, Any]:
        return self._c._request_json("GET", "/api/admin/stats", admin=True)

    def list_certificates(
        self,
        limit: int = 50,
        offset: int = 0,
        course: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if course is not None:
            params["course"] = course
        return self._c._request_json(
            "GET",
            "/api/admin/certificates",
            admin=True,
            params=params,
        )

    def bulk_generate(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        return self._c._request_json(
            "POST",
            "/api/admin/certificates/bulk",
            admin=True,
            json={"entries": entries},
        )

    def revoke(self, cert_db_id: str | int) -> dict[str, Any]:
        return self._c._request_json(
            "POST",
            f"/api/admin/certificates/{cert_db_id}/revoke",
            admin=True,
        )

    def list_courses(self) -> dict[str, Any]:
        return self._c._request_json("GET", "/api/admin/courses", admin=True)

    def add_course(self, name: str, description: str = "") -> dict[str, Any]:
        return self._c._request_json(
            "POST",
            "/api/admin/courses",
            admin=True,
            json={"name": name, "description": description},
        )

    def toggle_course(self, course_id: str | int, active: bool) -> dict[str, Any]:
        return self._c._request_json(
            "PATCH",
            f"/api/admin/courses/{course_id}",
            admin=True,
            json={"active": active},
        )


class IntelliForge:
    """
    Client for the IntelliForge Certificate API.

    Use ``X-API-Key`` for certificate creation and ``X-Admin-Key`` for admin routes.
    """

    def __init__(
        self,
        api_key: str | None = None,
        admin_key: str | None = None,
        base_url: str = "https://certs.intelliforge.tech",
        *,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._admin_key = admin_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._http = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "intelliforge-python-sdk/2.0.0"},
        )
        self.admin = Admin(self)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> IntelliForge:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(
        self,
        *,
        api: bool = False,
        admin: bool = False,
        extra: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        h: dict[str, str] = {}
        if extra:
            h.update(extra)
        if api:
            if not self._api_key:
                raise AuthenticationError(
                    "X-API-Key is required for this operation but api_key was not set.",
                    status_code=None,
                )
            h["X-API-Key"] = self._api_key
        if admin:
            if not self._admin_key:
                raise AuthenticationError(
                    "X-Admin-Key is required for this operation but admin_key was not set.",
                    status_code=None,
                )
            h["X-Admin-Key"] = self._admin_key
        return h

    def _execute(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            return self._http.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=dict(headers) if headers else None,
            )
        except httpx.RequestError as exc:
            raise IntelliForgeError(f"HTTP request failed: {exc}") from exc

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        status = response.status_code
        body = response.text
        try:
            detail = response.json()
            if isinstance(detail, dict) and "detail" in detail:
                message = str(detail["detail"])
            elif isinstance(detail, dict) and "message" in detail:
                message = str(detail["message"])
            elif isinstance(detail, dict) and "error" in detail:
                message = str(detail["error"])
            else:
                message = json.dumps(detail) if detail else body or response.reason_phrase
        except (json.JSONDecodeError, ValueError):
            message = body or response.reason_phrase

        if status in (401, 403):
            raise AuthenticationError(
                message,
                status_code=status,
                response_body=body,
            )
        if status == 429:
            raise RateLimitError(
                message,
                status_code=status,
                response_body=body,
            )
        if status in (400, 422):
            raise ValidationError(
                message,
                status_code=status,
                response_body=body,
            )
        raise IntelliForgeError(
            message,
            status_code=status,
            response_body=body,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        api: bool = False,
        admin: bool = False,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> dict[str, Any]:
        response = self._execute(
            method,
            path,
            params=params,
            json_body=json,
            headers=self._headers(api=api, admin=admin),
        )
        self._raise_for_status(response)
        data = response.json()
        if not isinstance(data, dict):
            raise IntelliForgeError(
                "Expected JSON object in response.",
                status_code=response.status_code,
                response_body=response.text,
            )
        return data

    def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        api: bool = False,
        admin: bool = False,
        json_body: Any = None,
    ) -> bytes:
        response = self._execute(
            method,
            path,
            json_body=json_body,
            headers=self._headers(api=api, admin=admin),
        )
        self._raise_for_status(response)
        return response.content

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/health")

    def list_courses(self) -> list[str]:
        data = self._request_json("GET", "/api/courses")
        courses = data.get("courses")
        if not isinstance(courses, list):
            raise IntelliForgeError(
                "Invalid response: missing or invalid 'courses' array.",
                status_code=None,
            )
        return [str(c) for c in courses]

    def create_certificate(
        self,
        participant_name: str,
        course_name: str,
        completion_date: str,
        instructor_name: str = "IntelliForge AI Team",
        participant_email: str | None = None,
        callback_url: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "participant_name": participant_name,
            "course_name": course_name,
            "completion_date": completion_date,
            "instructor_name": instructor_name,
        }
        if participant_email is not None:
            payload["participant_email"] = participant_email
        if callback_url is not None:
            payload["callback_url"] = callback_url
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        response = self._execute(
            "POST",
            "/api/certificate",
            json_body=payload,
            headers=self._headers(api=True),
        )
        self._raise_for_status(response)
        out = response.json()
        if not isinstance(out, dict):
            raise IntelliForgeError(
                "Expected JSON object in response.",
                status_code=response.status_code,
                response_body=response.text,
            )
        return out

    def verify(self, token: str) -> dict[str, Any]:
        return self._request_json("GET", f"/certificate/{token}/verify")

    def batch_verify(self, tokens: list[str]) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/certificates/verify",
            json={"tokens": tokens},
        )

    def download_pdf(self, token: str, path: str | None = None) -> bytes | None:
        data = self._request_bytes("GET", f"/certificate/{token}/download")
        if path is not None:
            with open(path, "wb") as f:
                f.write(data)
            return None
        return data
