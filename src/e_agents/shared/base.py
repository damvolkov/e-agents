"""Base models with YAML serialization support."""

from __future__ import annotations

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict


class BaseModelYAML(BaseModel):
    """Base for YAML-backed configuration models."""

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        """Load model from a YAML file."""
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    @classmethod
    def model_validate_yaml(cls, data: str | bytes) -> Self:
        """Validate and parse YAML string into model instance."""
        raw = data if isinstance(data, str) else data.decode()
        return cls.model_validate(yaml.safe_load(raw))

    def model_dump_yaml(self, **kwargs) -> str:
        """Serialize model to a YAML string."""
        kwargs.setdefault("exclude_none", True)
        return yaml.dump(self.model_dump(**kwargs), sort_keys=False)
