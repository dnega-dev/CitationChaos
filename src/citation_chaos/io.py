"""Small JSON and output helpers with UTF-8 and stable formatting."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Union


PathLike = Union[str, Path]


def read_json(path: PathLike) -> Any:
    if str(path) == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: PathLike, value: Any) -> None:
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    write_text(path, text)


def write_text(path: PathLike, text: str) -> None:
    if str(path) == "-":
        sys.stdout.write(text)
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
