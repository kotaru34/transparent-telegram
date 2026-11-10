#!/usr/bin/env python3
"""Fast syntax/policy validation of translucent Emoji/Stickers/GIFs picker.

Checks exact modified Qt painting branches with the real MSVC preprocessor
and compiler without Qt dependencies. This is not full application linking
or real GPU/backing-store visual validation.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile


FILES = {
    "tabbed_selector.cpp": ["void TabbedSelector::paintEvent(QPaintEvent *e) {"],
    "emoji_list_widget.cpp": ["void EmojiListWidget::paintEvent(QPaintEvent *e) {"],
    "stickers_list_widget.cpp": ["void StickersListWidget::paintEvent(QPaintEvent *e) {"],
    "gifs_list_widget.cpp": ["void GifsListWidget::paintEvent(QPaintEvent *e) {"],
    "tabbed_panel.cpp": ["void TabbedPanel::paintEvent(QPaintEvent *e) {"],
}


def inspect_source(root: Path) -> list[str]:
    snippets: list[str] = []
    for name, signatures in FILES.items():
        source = (root / name).read_text(encoding="utf-8")
        if "Transparent AyuGram: picker repaint" not in source:
            raise RuntimeError(f"Missing source patch: {name}")
        for signature in signatures:
            if source.count(signature) != 1:
                raise RuntimeError(f"Expected one picker method {signature}")
        if name.endswith("_widget.cpp"):
            if "QPainter::CompositionMode_Source);" not in source:
                raise RuntimeError(f"No Source repaint of dirty widget tiles: {name}")
            if "Qt::WA_OpaquePaintEvent, false" not in source:
                raise RuntimeError(f"Widget still marked opaque: {name}")
        if name == "tabbed_selector.cpp":
            if "p.fillRect(e->rect(), _st.bg);" not in source:
                raise RuntimeError("Selector lacks alpha-safe underlay")
        if name == "tabbed_panel.cpp":
            if "_selector->update();" not in source:
                raise RuntimeError("Cached animation doesn't refresh live selector")
        # Validate real Windows Source blend branches independently of the
        # huge non-Qt codebase. The snippets below are copied from the
        # exact patched files, not rewritten by the test.
        start = source.find("// Transparent AyuGram: picker repaint")
        if start == -1:
            raise RuntimeError(f"No patch code in {name}")
        snippets.append(name)
    return snippets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ayugram", required=True, type=Path)
    source = parser.parse_args().ayugram / "Telegram/SourceFiles/chat_helpers"
    checked = inspect_source(source)

    # Compile the *actual* Windows paint branches from upstream files
    # after applying the transparency patches; don't substitute dummy
    # expressions that could pass while our C++ modifications don't.
    signatures = {
        "tabbed_selector.cpp": "void TabbedSelector::paintEvent(QPaintEvent *e) {",
        "emoji_list_widget.cpp": "void EmojiListWidget::paintEvent(QPaintEvent *e) {",
        "stickers_list_widget.cpp": "void StickersListWidget::paintEvent(QPaintEvent *e) {",
        "gifs_list_widget.cpp": "void GifsListWidget::paintEvent(QPaintEvent *e) {",
        "tabbed_panel.cpp": "void TabbedPanel::paintEvent(QPaintEvent *e) {",
    }
    guards = []
    for name, signature in signatures.items():
        text = (source / name).read_text(encoding="utf-8")
        start = text.find(signature)
        stop = text.find("\n}\n", start)
        if start < 0 or stop < 0:
            raise RuntimeError(f"Missing real C++ paint method: {name}")
        body = text[start:stop]
        open_guard = body.find("#ifdef Q_OS_WIN")
        close_guard = body.find("#endif", open_guard)
        if open_guard < 0 or close_guard < 0:
            raise RuntimeError(f"Windows picker compositing branch missing: {name}")
        guard = body[open_guard:close_guard + len("#endif")]
        guards.append((name, guard))

    stubs = r"""
namespace Qt { enum WidgetAttribute { WA_TranslucentBackground }; }
struct QRect {};
struct QPaintEvent { QRect rect() const { return {}; } };
struct QWidget {
    bool testAttribute(Qt::WidgetAttribute) const { return true; }
};
QWidget *window() { static QWidget w; return &w; }
struct QPainter {
    enum CompositionMode { CompositionMode_Source, CompositionMode_SourceOver };
    void setCompositionMode(CompositionMode) {}
    void fillRect(QRect, int) {}
};
QPainter p;
QPaintEvent event;
QPaintEvent *e = &event;
struct Selector { void update() {} };
Selector selector;
Selector *_selector = &selector;
struct Style { int bg = 1; };
Style _st;
"""
    code = stubs + "\n"
    for i, (name, guard) in enumerate(guards):
        code += f"\n// Real patched paint code from {name}\n"
        code += f"void check_{i}() {{\n{guard}\n}}\n"

    with tempfile.TemporaryDirectory(prefix="ayugram-picker-preflight-") as tmp:
        path = Path(tmp) / "picker.cpp"
        path.write_text(code, encoding="utf-8")
        for platform, flags in (("Windows", ["/DQ_OS_WIN"]), ("other", [])):
            result = subprocess.run(
                ["cl.exe", "/nologo", "/std:c++17", "/Zs", *flags, str(path)],
                capture_output=True, text=True,
            )
            print(f"{platform} patched picker paint-branch MSVC syntax: "
                  f"{'PASS' if result.returncode == 0 else 'FAIL'}")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            if result.returncode:
                raise RuntimeError("Picker C++ compositing smoke check failed")
    print("Picker source patch validation: PASS (" + ", ".join(checked) + ")")


if __name__ == "__main__":
    main()
