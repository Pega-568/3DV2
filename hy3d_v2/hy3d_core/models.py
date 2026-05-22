from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReferenceView:
    path: Path
    view_type: str = "unknown"


@dataclass
class ReviewPayload:
    visual_score: int
    geometry_score: int
    object_similarity: int
    holes_or_artifacts: str
    usable_as_base: bool
    repair_needed: str
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "visual_score": self.visual_score,
            "geometry_score": self.geometry_score,
            "object_similarity": self.object_similarity,
            "holes_or_artifacts": self.holes_or_artifacts,
            "usable_as_base": self.usable_as_base,
            "repair_needed": self.repair_needed,
            "notes": self.notes,
        }


@dataclass
class JobPaths:
    root: Path
    job_dir: Path
    version_dir: Path
    input_dir: Path
    accepted_dir: Path
    engine_output_dir: Path
    blender_review_dir: Path
    validation_dir: Path
    edited_dir: Path
    multi_view_dir: Path
    instructions_dir: Path
    manifests: dict[str, Path] = field(default_factory=dict)

