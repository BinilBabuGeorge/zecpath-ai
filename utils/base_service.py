"""
Base interface for all Zecpath AI services.

Every service (ATS, Screening, Interview Intelligence, Behavior Analysis,
Decision & Scoring) should subclass BaseAIService and implement process().
This keeps every service's input/output contract consistent with the
Day 2 architecture (input dict in, output dict out, version-tagged).

DAY 57 -- THE STABLE BOUNDARY. `process()` is still where each service does its work, but callers
should use `run()`:

    run(payload) -> dict      NEVER raises. Always returns one of two shapes.

    success: {"service", "model_version", "api_version", "status": "success", ...service fields...}
    error:   {"service", "model_version", "api_version", "status": "error",
              "error": {"code": "...", "message": "...", "field": "..." | null}}

Error codes: invalid_payload | invalid_input | missing_field | invalid_score | too_large |
unsupported_value | internal_error. An unexpected exception is logged in full but the caller only ever sees
`internal_error` with a generic message (no stack trace, no library internals).

Every response is JSON-safe: NaN / infinity become null, enums become their values, dataclasses become dicts.
Breaking a response shape means bumping API_VERSION.
"""

from __future__ import annotations

import dataclasses
import math
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional, Sequence

from utils.config import MODEL_VERSION, SERVICE_NAME
from utils.logger import get_logger

API_VERSION = "1.0"
MAX_TEXT_CHARS = 200_000          # one resume / job description / answer; larger is refused, not truncated silently
MAX_ITEMS = 200                   # turns / answers / requirements in one request


class ServiceInputError(ValueError):
    """The caller's input is unusable. `code` and `field` are machine-readable; `str(error)` is safe to show."""

    def __init__(self, code: str, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.field = field


def to_json_safe(obj: Any, _depth: int = 0) -> Any:
    """Recursively make a result JSON-serialisable: no NaN/inf, no enums, no dataclasses, no tuples/sets."""
    if _depth > 12:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, Enum):
        return to_json_safe(obj.value, _depth + 1)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_json_safe(getattr(obj, f.name), _depth + 1) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v, _depth + 1) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((to_json_safe(v, _depth + 1) for v in obj), key=str)
    return str(obj)


class BaseAIService(ABC):
    """Common contract for every AI microservice in the pipeline."""

    service_name: str = SERVICE_NAME
    model_version: str = MODEL_VERSION
    api_version: str = API_VERSION

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run this service's core logic.

        Args:
            payload: input data as defined in the Day 2 I/O spec
                     (e.g. resume + job requirements for ATS AI Service).

        Returns:
            A result dict that always includes 'service', 'model_version',
            and a 'status' field, plus service-specific fields.

        May raise ServiceInputError (or ValueError/TypeError) for unusable input; callers that must not see
        exceptions should use run().
        """
        raise NotImplementedError

    # ---------------------------------------------------------------- stable entry point
    def run(self, payload: Any) -> Dict[str, Any]:
        """The stable boundary: validates, runs `process`, and ALWAYS returns a JSON-safe envelope."""
        try:
            if not isinstance(payload, dict):
                raise ServiceInputError("invalid_payload", f"The request body must be a JSON object, got {type(payload).__name__}.")
            return to_json_safe(self.process(payload))
        except ServiceInputError as exc:
            return self._error_response(exc.code, str(exc), exc.field)
        except (ValueError, TypeError) as exc:
            return self._error_response("invalid_input", str(exc))
        except Exception:                                    # noqa: BLE001 - the boundary must not leak internals
            self.logger.exception("Unexpected error in %s", self.__class__.__name__)
            return self._error_response("internal_error", "An internal error occurred; the request was not processed.")

    # ---------------------------------------------------------------- envelopes
    def _base_response(self, status: str = "success") -> Dict[str, Any]:
        """Helper so every service returns a consistent response envelope."""
        return {
            "service": self.service_name,
            "model_version": self.model_version,
            "api_version": self.api_version,
            "status": status,
        }

    def _error_response(self, code: str, message: str, field: Optional[str] = None) -> Dict[str, Any]:
        response = self._base_response("error")
        response["error"] = {"code": code, "message": message, "field": field}
        return response

    # ---------------------------------------------------------------- input validators
    @staticmethod
    def _get_text(payload: Dict[str, Any], key: str, required: bool = True, allow_empty: bool = False) -> Optional[str]:
        value = payload.get(key)
        if value is None:
            if required:
                raise ServiceInputError("missing_field", f"'{key}' is required.", key)
            return None
        if not isinstance(value, str):
            raise ServiceInputError("invalid_input", f"'{key}' must be text, got {type(value).__name__}.", key)
        if len(value) > MAX_TEXT_CHARS:
            raise ServiceInputError("too_large", f"'{key}' is {len(value)} characters; the limit is {MAX_TEXT_CHARS}.", key)
        if not allow_empty and not value.strip():
            raise ServiceInputError("invalid_input", f"'{key}' must not be empty.", key)
        return value

    @staticmethod
    def _get_score(payload: Dict[str, Any], key: str) -> Optional[float]:
        """A 0-100 score, or None when absent. A missing score is NOT zero; the caller decides what absence means."""
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ServiceInputError("invalid_score", f"'{key}' must be a number between 0 and 100, got {type(value).__name__}.", key)
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ServiceInputError("invalid_score", f"'{key}' must be between 0 and 100, got {value}.", key)
        return float(value)

    @staticmethod
    def _get_choice(payload: Dict[str, Any], key: str, choices: Sequence[str], default: str) -> str:
        value = payload.get(key, default)
        if not isinstance(value, str) or value.lower() not in choices:
            raise ServiceInputError("unsupported_value", f"'{key}' must be one of {list(choices)}, got {value!r}.", key)
        return value.lower()

    @staticmethod
    def _get_list(payload: Dict[str, Any], key: str, required: bool = False) -> Optional[list]:
        value = payload.get(key)
        if value is None:
            if required:
                raise ServiceInputError("missing_field", f"'{key}' is required.", key)
            return None
        if not isinstance(value, (list, tuple)):
            raise ServiceInputError("invalid_input", f"'{key}' must be a list, got {type(value).__name__}.", key)
        if len(value) > MAX_ITEMS:
            raise ServiceInputError("too_large", f"'{key}' has {len(value)} items; the limit is {MAX_ITEMS}.", key)
        return list(value)
