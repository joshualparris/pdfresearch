from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Config:
    force_boundary_before: set[int] = field(default_factory=set)
    suppress_boundary_before: set[int] = field(default_factory=set)
    title_overrides: dict[int, str] = field(default_factory=dict)
    category_overrides: dict[int, str] = field(default_factory=dict)
    reference_patterns: list[str] = field(default_factory=list)
    personal_patterns: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path | None) -> "Config":
        if not path:
            return cls()
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        boundaries = data.get("boundaries", {})
        titles = data.get("titles", {})
        classify = data.get("classification", {})
        categories = {int(k): str(v) for k, v in data.get("categories", {}).items()}
        if any(value not in {"personal", "reference"} for value in categories.values()):
            raise ValueError("Category overrides must be personal or reference")
        return cls(
            force_boundary_before={int(x) for x in boundaries.get("force_before", [])},
            suppress_boundary_before={int(x) for x in boundaries.get("suppress_before", [])},
            title_overrides={int(k): str(v) for k, v in titles.items()},
            category_overrides=categories,
            reference_patterns=[str(x) for x in classify.get("reference_patterns", [])],
            personal_patterns=[str(x) for x in classify.get("personal_patterns", [])],
        )

    def classify_override(self, sample: str) -> tuple[str, str] | None:
        for pattern in self.personal_patterns:
            if re.search(pattern, sample, flags=re.I | re.S):
                return "personal", f"config_personal_pattern:{pattern}"
        for pattern in self.reference_patterns:
            if re.search(pattern, sample, flags=re.I | re.S):
                return "reference", f"config_reference_pattern:{pattern}"
        return None
