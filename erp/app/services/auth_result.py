from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthResult:
    success: bool
    message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def as_tuple(self) -> tuple[bool, str | None, dict[str, Any]]:
        return self.success, self.message, self.data

    @classmethod
    def ok(cls, data: dict[str, Any] | None = None, message: str | None = None) -> AuthResult:
        return cls(True, message, data or {})

    @classmethod
    def fail(cls, message: str, data: dict[str, Any] | None = None) -> AuthResult:
        return cls(False, message, data or {})
