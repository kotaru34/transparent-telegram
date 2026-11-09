#!/usr/bin/env python3
"""Compile the patched chat renderer in isolation before expensive Windows builds.

The real patched function body is used verbatim. Only dependent Qt types are
stubbed, so declaration/redefinition errors are caught by the real MSVC
compiler without compiling any Qt/AyuGram dependencies. This is NOT a full
integration build or a test of other methods in the AyuGram codebase.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile

SIGNATURE = (
    "void SectionWidget::PaintBackground(\n"
    "\t\tnot_null<Ui::ChatTheme*> theme,\n"
    "\t\tnot_null<QWidget*> widget,\n"
    "\t\tint fillHeight,\n"
)

STUBS = """
template <typename T> using not_null = T;
struct QRect {
    QRect translated(int, int) const { return *this; }
};
struct QSize {
    QSize(int, int) {}
};
class QWidget {
public:
    int width() const { return 100; }
};
class QColor {
public:
    int alpha() const { return 255; }
    void setAlpha(int) {}
};
namespace st {
struct ColorData { QColor c; };
extern ColorData *windowBg;
}
class QPainter {
public:
    enum CompositionMode { CompositionMode_Source, CompositionMode_SourceOver };
    explicit QPainter(QWidget*) {}
    void setCompositionMode(CompositionMode) {}
    void fillRect(const QRect&, const QColor&) {}
    void translate(int, int) {}
};
namespace Ui { class ChatTheme {}; }
class SectionWidget {
public:
    static void PaintBackground(
        not_null<Ui::ChatTheme*>, not_null<QWidget*>,
        int, int, QRect, bool);
    static void PaintBackground(
        QPainter&, not_null<Ui::ChatTheme*>,
        QSize, QRect, bool) {}
};
"""


def extract(source: str) -> str:
    start = source.find(SIGNATURE)
    if start < 0 or source.find(SIGNATURE, start + 1) >= 0:
        raise ValueError("Expected exactly one chat PaintBackground(QWidget*) overload")
    brace = source.find("{", start + len(SIGNATURE))
    if brace < 0:
        raise ValueError("Missing chat paint function body")
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ValueError("Unbalanced braces in patched chat painter")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ayugram", type=Path, required=True)
    args = parser.parse_args()
    file = args.ayugram / "Telegram/SourceFiles/window/section_widget.cpp"
    body = extract(file.read_text(encoding="utf-8"))
    if "Transparent AyuGram" not in body:
        raise RuntimeError("Chat painter has not been transparency patched")

    with tempfile.TemporaryDirectory(prefix="ayugram-cpp-preflight-") as tmp:
        path = Path(tmp) / "chat_paint.cpp"
        path.write_text(STUBS + body + "\n", encoding="utf-8")
        for branch, defines in (
            ("Windows", ["/DQ_OS_WIN"]),
            ("other", []),
        ):
            command = ["cl.exe", "/nologo", "/std:c++20", "/Zs", *defines, str(path)]
            proc = subprocess.run(command, capture_output=True, text=True)
            print(f"{branch} chat paint syntax: " + ("PASS" if proc.returncode == 0 else "FAIL"))
            if proc.stdout:
                print(proc.stdout)
            if proc.stderr:
                print(proc.stderr)
            if proc.returncode != 0:
                raise RuntimeError(f"MSVC rejected patched chat C++ ({branch} branch)")


if __name__ == "__main__":
    main()
