"""
Base interface for all Zecpath AI services.

Every service (ATS, Screening, Interview Intelligence, Behavior Analysis,
Decision & Scoring) should subclass BaseAIService and implement process().
This keeps every service's input/output contract consistent with the
Day 2 architecture (input dict in, output dict out, version-tagged).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from utils.config import MODEL_VERSION, SERVICE_NAME
from utils.logger import get_logger


class BaseAIService(ABC):
    """Common contract for every AI microservice in the pipeline."""

    service_name: str = SERVICE_NAME
    model_version: str = MODEL_VERSION

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
        """
        raise NotImplementedError

    def _base_response(self, status: str = "success") -> Dict[str, Any]:
        """Helper so every service returns a consistent response envelope."""
        return {
            "service": self.service_name,
            "model_version": self.model_version,
            "status": status,
        }
