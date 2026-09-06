from __future__ import annotations

from pydantic import BaseModel


class CompatBaseModel(BaseModel):
    """Pydantic v1/v2 compatibility helpers for this lesson repo."""

    @classmethod
    def model_validate(cls, value):  # type: ignore[override]
        if hasattr(super(), "model_validate"):
            return super().model_validate(value)  # type: ignore[misc]
        return cls.parse_obj(value)

    def model_dump(self, *args, **kwargs):  # type: ignore[override]
        kwargs.setdefault("exclude", {"model_config"})
        if hasattr(super(), "model_dump"):
            return super().model_dump(*args, **kwargs)  # type: ignore[misc]
        return super().dict(*args, **kwargs)

    def model_copy(self, *, deep: bool = False):  # type: ignore[override]
        if hasattr(super(), "model_copy"):
            return super().model_copy(deep=deep)  # type: ignore[misc]
        return super().copy(deep=deep)
