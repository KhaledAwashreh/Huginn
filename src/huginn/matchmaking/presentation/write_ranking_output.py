"""Publish complete operator snapshots without overwriting existing files."""

import os
import tempfile
from pathlib import Path


def write_ranking_output(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".ranking-", delete=True
    ) as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        os.link(stream.name, path)
