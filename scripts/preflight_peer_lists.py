#!/usr/bin/env python3
"""Validate alpha-safe PeerList and Info patches against pinned AyuGram sources.

Static assertions catch missing guarded paths; the full CI remains necessary
for complete C++ compilation and visual validation.
"""
from __future__ import annotations
import argparse
from pathlib import Path


def require(path: Path, *needles: str) -> None:
    source = path.read_text(encoding="utf-8")
    for needle in needles:
        if source.count(needle) != 1:
            raise RuntimeError(
                f"{path.name}: expected exactly one patched occurrence of {needle!r}"
            )
    print("Alpha safe:", path.name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ayugram", type=Path, required=True)
    root = parser.parse_args().ayugram
    require(
        root / "Telegram/SourceFiles/boxes/peer_list_box.cpp",
        "Transparent AyuGram: this shared cache stores Format_RGB32",
        "Replace stale pixels beneath the row, don't blend a translucent"
    )
    require(
        root / "Telegram/SourceFiles/info/info_content_widget.cpp",
        "Transparent AyuGram: Info/settings layers have alpha",
        "This is alpha-correct compositing, not a backdrop blur.",
    )


if __name__ == "__main__":
    main()
