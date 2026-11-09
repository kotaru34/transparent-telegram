#!/usr/bin/env python3
"""Fast, isolated MSVC syntax checks for the exact patched scrolling C++.

The helper/method bodies are extracted from the patched AyuGram source.
Tiny Qt stand-ins permit /Zs checks with no Qt dependency compilation.
This catches C++ syntax/errors but is not an integration/rendering test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile


def extract(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0 or source.find(signature, start + 1) >= 0:
        raise RuntimeError(f"Expected exactly one {signature!r}")
    opened = source.find("{", start + len(signature))
    if opened < 0:
        raise RuntimeError(f"Missing body for {signature!r}")
    depth = 0
    for i in range(opened, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise RuntimeError("Unbalanced C++ braces")


STUBS = r"""
#include <cmath>
#include <utility>
#include <initializer_list>
namespace Qt {
    enum WidgetAttribute {
        WA_TranslucentBackground, WA_OpaquePaintEvent,
        WA_StaticContents, WA_AcceptTouchEvents
    };
}
struct QPoint { QPoint operator-() const { return {}; } };
struct QRect {
    QRect() = default;
    QRect(int, int, int, int) {}
    QRect translated(QPoint) const { return {}; }
    QRect intersected(QRect) const { return {}; }
    bool isEmpty() const { return false; }
};
struct QResizeEvent {};
struct QWidget {
    QWidget *window() { return this; }
    bool testAttribute(Qt::WidgetAttribute) const { return true; }
    void setAttribute(Qt::WidgetAttribute, bool = true) {}
    void setAutoFillBackground(bool) {}
    void removeEventFilter(QWidget*) {}
    void installEventFilter(QWidget*) {}
    QRect rect() const { return {}; }
    QPoint pos() const { return {}; }
    int width() const { return 100; }
    int height() const { return 100; }
    void update() {}
    void update(QRect) {}
};
struct QScrollArea : QWidget {
    QWidget *_content = nullptr;
    QWidget _viewport;
    QWidget *widget() const { return _content; }
    QWidget *viewport() { return &_viewport; }
    void setWidget(QWidget *w) { _content = w; }
    void scrollContentsBy(int, int) {}
    void resizeEvent(QResizeEvent*) {}
};
template <typename T> using object_ptr = T*;
struct GeometryWidget : QWidget {
    void recountSize() {}
    void setGeometry(QRect) {}
};
struct Stream {
    void fire(std::initializer_list<int>) {}
};
struct ScrollArea : QScrollArea {
    bool _disabled = false;
    bool _touchEnabled = false;
    bool _widgetAcceptsTouch = false;
    object_ptr<QWidget> _widget = nullptr;
    GeometryWidget *_horizontalBar = nullptr;
    GeometryWidget *_verticalBar = nullptr;
    GeometryWidget *_topShadow = nullptr;
    GeometryWidget *_bottomShadow = nullptr;
    struct { int topsh = 0; int bottomsh = 0; } _st;
    Stream _geometryChanged;
    void scrollContentsBy(int, int);
    void resizeEvent(QResizeEvent*);
    void doSetOwnedWidget(object_ptr<QWidget>);
};
"""


def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("--ayugram", type=Path, required=True)
    root = args.parse_args().ayugram
    file = root / "Telegram/lib_ui/ui/widgets/scroll_area.cpp"
    source = file.read_text(encoding="utf-8")
    dialogs = (root / "Telegram/SourceFiles/dialogs/dialogs_inner_widget.cpp").read_text(
        encoding="utf-8"
    )
    if "Transparent AyuGram" not in source or "Format_RGB32" not in dialogs:
        raise RuntimeError("Glass scroll/dialogs source patch was not applied")
    if (
        "&& !window()->testAttribute(Qt::WA_TranslucentBackground)" not in dialogs
        or "setAttribute(Qt::WA_OpaquePaintEvent, false)" not in dialogs
    ):
        raise RuntimeError("Missing alpha-safe dialogs painting/caching policy")
    signatures = [
        "[[nodiscard]] bool PrepareGlassScroll(QScrollArea *area) {",
        "void RepaintGlassScroll(QScrollArea *area) {",
        "void ScrollArea::scrollContentsBy(int dx, int dy) {",
        "void ScrollArea::resizeEvent(QResizeEvent *e) {",
        "void ScrollArea::doSetOwnedWidget(object_ptr<QWidget> w) {",
    ]
    bodies = "\n\n".join(extract(source, s) for s in signatures)
    with tempfile.TemporaryDirectory(prefix="ayugram-glass-preflight-") as tmp:
        path = Path(tmp) / "glass_scroll.cpp"
        path.write_text(STUBS + "\n" + bodies + "\n", encoding="utf-8")
        for platform, flags in (("Windows", ["/DQ_OS_WIN"]), ("other", [])):
            result = subprocess.run(
                ["cl.exe", "/nologo", "/std:c++20", "/Zs", *flags, str(path)],
                capture_output=True, text=True,
            )
            print(f"{platform} glass scroll MSVC syntax: {'PASS' if result.returncode == 0 else 'FAIL'}")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            if result.returncode:
                raise RuntimeError("Glass scroll C++ preflight failed")


if __name__ == "__main__":
    main()
