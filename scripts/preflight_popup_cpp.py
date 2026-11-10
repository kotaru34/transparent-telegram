#!/usr/bin/env python3
"""Fast MSVC syntax check for live popup background painting and policy.

The real patched PopupMenu::paintBg method is checked in isolation with
shape-compatible Qt stand-ins, without rebuilding AyuGram dependencies.
Also checks that both popup and embedded menu painters agree on which
widget owns the translucent background. Not a full Qt integration test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile


def extract(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0 or source.find(signature, start + 1) >= 0:
        raise RuntimeError(f"Expected exactly one {signature}")
    begin = start + len(signature) - 1 if signature.endswith("{") else source.find("{", start + len(signature))
    if begin < 0:
        raise RuntimeError("Missing body")
    depth = 0
    for at in range(begin, len(source)):
        if source[at] == "{":
            depth += 1
        if source[at] == "}":
            depth -= 1
            if depth == 0:
                return source[start:at + 1]
    raise RuntimeError("Unbalanced C++ braces")


STUB = r"""
namespace Qt { constexpr int transparent = 0; }
struct QRect {};
struct QMargins {
    int left() const { return 1; }
    int right() const { return 1; }
    int top() const { return 1; }
    int bottom() const { return 1; }
};
struct QPainter {
    enum CompositionMode {
        CompositionMode_Source,
        CompositionMode_SourceOver,
    };
    void setCompositionMode(CompositionMode) {}
    template <class... Args> void fillRect(Args...) {}
};
struct ColorSet { int itemBg = 0; };
struct Style {
    ColorSet menu;
    int shadowFallback = 0;
};
class PopupMenu {
public:
    bool _useTransparency = true;
    QRect _inner;
    Style _st;
    QMargins _padding;
    QRect rect() const { return {}; }
    int width() const { return 120; }
    int height() const { return 180; }
    void paintBg(QPainter&);
};
"""


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--ayugram", type=Path, required=True)
    root = cli.parse_args().ayugram / "Telegram/lib_ui/ui/widgets"
    popup = (root / "popup_menu.cpp").read_text(encoding="utf-8")
    menu = (root / "menu/menu.cpp").read_text(encoding="utf-8")
    required = [
        '_menu->setProperty("ayugramGlassPopupAlphaFill", true);',
        '_menu->property("ayugramGlassPopupAlphaFill").toBool()',
        'p.fillRect(_inner, _st.menu.itemBg);',
        'p.fillRect(rect(), Qt::transparent);',
        'p.setCompositionMode(QPainter::CompositionMode_Source);',
    ]
    for needle in required:
        count = popup.count(needle)
        expected = 2 if needle in ("p.fillRect(_inner, _st.menu.itemBg);", "p.setCompositionMode(QPainter::CompositionMode_Source);") else 1
        if count != expected:
            raise RuntimeError(f"Popup policy occurrence mismatch: {needle}: {count}")
    if menu.count('property("ayugramGlassPopupAlphaFill").toBool()') != 1:
        raise RuntimeError("Nested menu missing child alpha-safe background painter")
    mask_line = "static const auto kOpaqueRoundingMask = style::owned_color(QColor(255, 255, 255, 255));"
    mask_setter = "_roundRect.setColor(kOpaqueRoundingMask.color());"
    if popup.count(mask_line) != 1 or popup.count(mask_setter) != 1:
        raise RuntimeError("DestinationIn corner mask must use a persistent opaque style::owned_color")
    if popup.count("p.setCompositionMode(QPainter::CompositionMode_Source);") != 2:
        raise RuntimeError("Popup root and padding must each use Source compositing")
    if menu.count("p.setCompositionMode(QPainter::CompositionMode_Source);") != 1:
        raise RuntimeError("Live Menu child must use Source compositing")
    if 'p.fillRect(clip, _st.itemBg);' not in menu:
        raise RuntimeError("Live Menu child must repaint its own background")
    if "if (_menu->property(\"ayugramGlassPopupAlphaFill\").toBool()) {\n\t\t\treturn;" in popup:
        raise RuntimeError("The padding child remains disabled in glass mode")
    method = extract(popup, "void PopupMenu::paintBg(QPainter &p) {")
    with tempfile.TemporaryDirectory(prefix="ayugram-popup-preflight-") as tmp:
        path = Path(tmp) / "popup_paint.cpp"
        path.write_text(STUB + "\n" + method + "\n", encoding="utf-8")
        for platform, flags in [("Windows", ["/DQ_OS_WIN"]), ("other", [])]:
            result = subprocess.run(
                ["cl.exe", "/nologo", "/std:c++17", "/Zs", *flags, str(path)],
                capture_output=True, text=True,
            )
            print(f"{platform} popup background MSVC syntax: "
                  f"{'PASS' if result.returncode == 0 else 'FAIL'}")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            if result.returncode:
                raise RuntimeError(f"{platform} popup background C++ check failed")
        # Verify the exact corner-mask statements with type-shaped stubs.
        # This catches unknown st:: palette symbols without building Qt.
        mask_begin = popup.index(mask_line)
        mask_end = popup.index("\n#endif", mask_begin)
        if mask_end < 0:
            raise RuntimeError("Missing Windows corner-mask block terminator")
        mask_source = popup[mask_begin:mask_end]
        mask_stub = r"""
struct QColor { QColor(int, int, int, int) {} };
namespace style {
struct color {};
class owned_color {
public:
    explicit owned_color(const QColor&) {}
    const style::color& color() const {
        static const style::color value;
        return value;
    }
};
}
struct RoundRect { void setColor(const style::color&) {} };
struct PopupMaskHarness {
    RoundRect _roundRect;
    void applyMask();
};
"""
        mask_path = Path(tmp) / "popup_mask.cpp"
        mask_path.write_text(
            mask_stub + "\nvoid PopupMaskHarness::applyMask() {\n"
            + mask_source + "\n}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            ["cl.exe", "/nologo", "/std:c++17", "/Zs", str(mask_path)],
            capture_output=True, text=True,
        )
        print(f"Windows opaque corner-mask MSVC syntax: "
              f"{'PASS' if result.returncode == 0 else 'FAIL'}")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        if result.returncode:
            raise RuntimeError("Corner-mask C++ syntax check failed")
    print("Popup root, padding, child painter and opaque corner-mask policy: PASS")


if __name__ == "__main__":
    main()
