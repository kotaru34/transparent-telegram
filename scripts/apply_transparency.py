#!/usr/bin/env python3
"""Patch the pinned AyuGram Desktop v7.2.9 source checkout for Windows alpha."""
from __future__ import annotations

import argparse
from pathlib import Path

MARK = "Transparent AyuGram"


def patch_one(path: Path, before: str, after: str) -> None:
    source = path.read_text(encoding="utf-8")
    if MARK in source:
        print("Already patched:", path)
        return
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"{path}: source anchor mismatch (expected 1, found {count})")
    path.write_text(source.replace(before, after, 1), encoding="utf-8", newline="\n")
    print("Patched:", path)


def patch_window(root: Path) -> None:
    patch_one(
        root / "Telegram/SourceFiles/window/main_window.cpp",
        "MainWindow::MainWindow(not_null<Controller*> controller)\n: _controller(controller)",
        """MainWindow::MainWindow(not_null<Controller*> controller)
#ifdef Q_OS_WIN
: Ui::RpWindow(true) // Transparent AyuGram: initialize Qt alpha before creating HWND.
#else
: Ui::RpWindow()
#endif
, _controller(controller)""",
    )
    patch_one(
        root / "Telegram/SourceFiles/mainwindow.cpp",
        "\tsetAttribute(Qt::WA_OpaquePaintEvent);\n}\n\nvoid MainWindow::initHook()",
        """#ifdef Q_OS_WIN
\t// Transparent AyuGram: preserve the alpha channel in window painting.
\tsetAttribute(Qt::WA_OpaquePaintEvent, false);
#else
\tsetAttribute(Qt::WA_OpaquePaintEvent);
#endif
}

void MainWindow::initHook()""",
    )


def patch_chat(root: Path) -> None:
    patch_one(
        root / "Telegram/SourceFiles/window/section_widget.cpp",
        "\t\tint fromy,\n\t\tQRect clip,\n\t\tbool paused) {\n\tauto p = QPainter(widget);",
        """\t\tint fromy,
\t\tQRect clip,
\t\tbool paused) {
#ifdef Q_OS_WIN
\t// Transparent AyuGram: a fully clear chat is click-through on Windows
\t// layered windows. Paint a nonzero-alpha glass surface, with Source
\t// composition to replace stale backing-store pixels after scrolling.
\tauto glass = st::windowBg->c;
\tif (glass.alpha() == 0) {
\t\tglass.setAlpha(1);
\t}
\tauto glassPainter = QPainter(widget);
\tglassPainter.setCompositionMode(QPainter::CompositionMode_Source);
\tglassPainter.fillRect(clip, glass);
\treturn;
#endif
\tauto p = QPainter(widget);""",
    )


def patch_main_menu(root: Path) -> None:
    path = root / "Telegram/SourceFiles/window/window_main_menu.cpp"
    source = path.read_text(encoding="utf-8")
    if MARK in source:
        print("Already patched:", path)
        return

    replacements = [
        (
            "\tsetAttribute(Qt::WA_OpaquePaintEvent);",
            """#ifdef Q_OS_WIN
\t// Transparent AyuGram: the menu is NOT opaque.
\tsetAttribute(Qt::WA_OpaquePaintEvent, false);
#else
\tsetAttribute(Qt::WA_OpaquePaintEvent);
#endif""",
        ),
        (
            "\tp.fillRect(clip, st::mainMenuBg);\n\tif (cover.intersects(clip)) {",
            """#ifdef Q_OS_WIN
\t// Transparent AyuGram: do not alpha-blend repeatedly with old pixels
\t// while this menu is scrolling, moving or being hovered.
\tp.setCompositionMode(QPainter::CompositionMode_Source);
\tp.fillRect(clip, st::mainMenuBg);
\tp.setCompositionMode(QPainter::CompositionMode_SourceOver);
#else
\tp.fillRect(clip, st::mainMenuBg);
#endif
\tif (cover.intersects(clip)) {""",
        ),
    ]
    for original, replacement in replacements:
        count = source.count(original)
        if count != 1:
            raise RuntimeError(f"{path}: menu anchor mismatch (expected 1, found {count})")
        source = source.replace(original, replacement, 1)
    path.write_text(source, encoding="utf-8", newline="\n")
    print("Patched:", path)


def patch_scroll(root: Path) -> None:
    patch_one(
        root / "Telegram/lib_ui/ui/widgets/scroll_area.cpp",
        "\tQScrollArea::scrollContentsBy(dx, dy);\n}",
        """\tQScrollArea::scrollContentsBy(dx, dy);
#ifdef Q_OS_WIN
\t// Transparent AyuGram: Qt's scroll-copy optimization can retain
\t// old translucent rows in the backing store. Invalidate the visible
\t// content and viewport after moving the scrollable widget.
\tif (window()->testAttribute(Qt::WA_TranslucentBackground)) {
\t\tif (auto content = widget()) {
\t\t\tcontent->update();
\t\t}
\t\tviewport()->update();
\t}
#endif
}""",
    )


def patch_palette(root: Path) -> None:
    header = root / "Telegram/lib_ui/ui/style/style_core_palette.h"
    patch_one(
        header,
        "\tvoid setData(int index, const internal::ColorData &value);",
        """\tvoid setData(int index, const internal::ColorData &value);
\t// Transparent AyuGram: this class is a friend of ColorData, so only
\t// member functions may use its private copy and RGBA constructors.
\t[[nodiscard]] static internal::ColorData GlassData(
\t\tint index, const internal::ColorData &original);""",
    )

    path = root / "Telegram/lib_ui/ui/style/style_core_palette.cpp"
    source = path.read_text(encoding="utf-8")
    if MARK in source:
        print("Already patched:", path)
        return

    def replace(before: str, after: str) -> None:
        nonlocal source
        found = source.count(before)
        if found != 1:
            raise RuntimeError(f"{path}: palette source anchor mismatch ({found}): {before[:55]!r}")
        source = source.replace(before, after, 1)

    replace(
        '#include "ui/style/style_palette_colorizer.h"\n\nnamespace style {',
        """#include "ui/style/style_palette_colorizer.h"
#include <array>
#include <utility>

namespace style {
namespace {

// Transparent AyuGram: clamp surface alpha, preserving original theme RGB.
// Opaque palette defaults are softened; explicit RGBA custom theme alpha wins.
[[nodiscard]] uchar GlassAlpha(int index, uchar alpha) {
\tstatic const auto limits = std::array{
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("windowBg")), uchar(0x65) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("windowBgOver")), uchar(0x90) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("dialogsBg")), uchar(0x65) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("dialogsBgOver")), uchar(0x85) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("topBarBg")), uchar(0x6A) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("titleBg")), uchar(0x55) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("titleBgActive")), uchar(0x55) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("sideBarBg")), uchar(0x65) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("mainMenuBg")), uchar(0xB0) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("menuBg")), uchar(0xC0) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("boxBg")), uchar(0xC8) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("historyComposeAreaBg")), uchar(0x82) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("historyReplyBg")), uchar(0x96) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("historyPinnedBg")), uchar(0x9C) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("msgInBg")), uchar(0xB8) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("msgOutBg")), uchar(0xB8) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("filterInputActiveBg")), uchar(0xA0) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("filterInputInactiveBg")), uchar(0xA0) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("emojiPanBg")), uchar(0xB0) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("emojiPanCategories")), uchar(0xB0) },
\t\tstd::pair{ internal::GetPaletteIndex(QLatin1String("emojiPanHeaderBg")), uchar(0xB0) },
\t};
\tfor (const auto &[key, maximum] : limits) {
\t\tif (key == index && alpha == uchar(255)) {
\t\t\treturn maximum;
\t\t}
\t}
\treturn alpha;
}

} // namespace

// Declared as a member of palette: ColorData constructors are private,
// and palette is the only authorized friend for palette transformations.
internal::ColorData palette::GlassData(
\t\tint index,
\t\tconst internal::ColorData &original) {
\tconst auto alpha = GlassAlpha(index, uchar(original.c.alpha()));
\treturn (alpha == original.c.alpha())
\t\t? original
\t\t: internal::ColorData(
\t\t\tuchar(original.c.red()),
\t\t\tuchar(original.c.green()),
\t\t\tuchar(original.c.blue()),
\t\t\talpha);
}"""
    )
    replace("new (data(i)) internal::ColorData(*other.data(i));",
            "new (data(i)) internal::ColorData(GlassData(i, *other.data(i)));")
    replace("*data(i) = *other.data(i);",
            "*data(i) = GlassData(i, *other.data(i));")
    replace("new (data(index)) internal::ColorData(*data(fallbackIndex));",
            "new (data(index)) internal::ColorData(GlassData(index, *data(fallbackIndex)));")
    replace("new (data(index)) internal::ColorData(value.r, value.g, value.b, value.a);",
            "new (data(index)) internal::ColorData(value.r, value.g, value.b, GlassAlpha(index, value.a));")
    replace(
        """void palette::setData(int index, const internal::ColorData &value) {
\tif (_status[index] == Status::Initial) {
\t\tnew (data(index)) internal::ColorData(value);
\t} else {
\t\t*data(index) = value;
\t}
\t_status[index] = Status::Loaded;
}""",
        """void palette::setData(int index, const internal::ColorData &value) {
\tconst auto glass = GlassData(index, value);
\tif (_status[index] == Status::Initial) {
\t\tnew (data(index)) internal::ColorData(glass);
\t} else {
\t\t*data(index) = glass;
\t}
\t_status[index] = Status::Loaded;
}""",
    )
    path.write_text(source, encoding="utf-8", newline="\n")
    print("Patched:", path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ayugram", required=True, type=Path)
    args = parser.parse_args()
    root = args.ayugram.resolve()
    if not (root / "Telegram/lib_ui/ui/colors.palette").is_file():
        parser.error("AyuGram source or its lib_ui submodule is missing")
    patch_window(root)
    patch_chat(root)
    patch_main_menu(root)
    patch_scroll(root)
    patch_palette(root)
    print("Transparent AyuGram: all patches applied")


if __name__ == "__main__":
    main()
