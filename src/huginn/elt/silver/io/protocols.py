from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol


class JsonReportWriter(Protocol):
    def prepare_summary_path(self, path: str | Path | None) -> Path | None: ...

    def write_json(self, path: str | Path, value: object) -> None: ...

    def write_summary(
        self, path: Path | None, report: Mapping[str, object]
    ) -> None: ...
