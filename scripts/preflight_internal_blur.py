#!/usr/bin/env python3
"""Fast source integrity checks for the scoped lifetime of Qt backdrop blur.

This isn't a full Qt integration test. The Windows build still verifies
linkage, while a visual test is needed for appearance and performance.
"""
from __future__ import annotations
import argparse
from pathlib import Path

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ayugram", type=Path, required=True)
    root = ap.parse_args().ayugram
    cpp = (root / "Telegram/SourceFiles/mainwindow.cpp").read_text(encoding="utf-8")
    src = (root / "Telegram/SourceFiles/info/info_content_widget.cpp").read_text(encoding="utf-8")
    for needle in (
        '#include <QtWidgets/QGraphicsBlurEffect>',
        'new QGraphicsBlurEffect(_main.data())',
        'blur->setBlurRadius(15.)',
        'blur->setBlurHints(QGraphicsBlurEffect::QualityHint)',
        'qEnvironmentVariableIsEmpty("AYUGRAM_NO_INTERNAL_BLUR")',
        '_main->setGraphicsEffect(blur)',
        '_main->setGraphicsEffect(nullptr)',
    ):
        if cpp.count(needle) != 1:
            raise RuntimeError(f"Qt backdrop missing/duplicated: {needle}")
    # The Info widget should inherit the blurred underlying QWidget via
    # standard SourceOver painting, not overwrite it with Source.
    start = src.find("void ContentWidget::paintEvent(QPaintEvent *e) {")
    end = src.find("\n}\n", start)
    if start < 0 or end < 0:
        raise RuntimeError("Info paintEvent was not found")
    if 'CompositionMode_Source' in src[start:end]:
        raise RuntimeError("Info paintEvent overwrites its actual blurred backdrop")
    if 'setAttribute(Qt::WA_OpaquePaintEvent, false)' not in src:
        raise RuntimeError("Info widget retains opaque paint hint")
    print("Internal Qt modal blur lifetime and alpha inheritance: PASS")

if __name__ == "__main__":
    main()
