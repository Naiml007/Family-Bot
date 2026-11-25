"""Application-level exception hierarchy with user-safe messages."""

from __future__ import annotations


class AppError(Exception):
    """Base error carrying a message safe to display directly to Discord users."""

    code: str = "app_error"

    def __init__(self, user_message: str, *, code: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        if code is not None:
            self.code = code


class AccessDeniedError(AppError):
    """Raised when an actor lacks required role/permission for an action."""

    code = "access_denied"


class UserInputError(AppError):
    """Raised when user-supplied parameters fail validation."""

    code = "invalid_input"


class NotFoundError(AppError):
    """Raised when a requested entity does not exist."""

    code = "not_found"


class ConflictError(AppError):
    """Raised on duplicate actions or invalid state transitions."""

    code = "conflict"


class ModuleDisabledError(AppError):
    """Raised when a guild has disabled the invoked module."""

    code = "module_disabled"
