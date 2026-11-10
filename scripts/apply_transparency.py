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
    path = root / "Telegram/lib_ui/ui/widgets/scroll_area.cpp"
    source = path.read_text(encoding="utf-8")
    if MARK in source:
        print("Already patched:", path)
        return

    def replace(before: str, after: str) -> None:
        nonlocal source
        count = source.count(before)
        if count != 1:
            raise RuntimeError(
                f"{path}: glass scroll anchor mismatch (expected 1, found {count}): {before[:65]!r}"
            )
        source = source.replace(before, after, 1)

    replace(
        "namespace Ui {\nnamespace {\n\n[[nodiscard]] int ComputeScrollTo(",
        """namespace Ui {
namespace {

#ifdef Q_OS_WIN
// Transparent AyuGram: apply once at attachment and again before scroll
// or resize, since some widgets change painting hints after construction.
[[nodiscard]] bool PrepareGlassScroll(QScrollArea *area) {
\tif (!area->window()->testAttribute(Qt::WA_TranslucentBackground)) {
\t\treturn false;
\t}
\tconst auto disableOpaqueOptimization = [](QWidget *widget) {
\t\tif (widget) {
\t\t\twidget->setAttribute(Qt::WA_OpaquePaintEvent, false);
\t\t\twidget->setAttribute(Qt::WA_StaticContents, false);
\t\t}
\t};
\tdisableOpaqueOptimization(area->viewport());
\tdisableOpaqueOptimization(area->widget());
\treturn true;
}

// Do not repaint an entire potentially huge chat list: update only the
// region visible through the viewport in the content's coordinates.
void RepaintGlassScroll(QScrollArea *area) {
\tif (const auto content = area->widget()) {
\t\tconst auto visible = area->viewport()->rect()
\t\t\t.translated(-content->pos())
\t\t\t.intersected(content->rect());
\t\tif (!visible.isEmpty()) {
\t\t\tcontent->update(visible);
\t\t}
\t}
\tarea->viewport()->update();
}
#endif // Q_OS_WIN

[[nodiscard]] int ComputeScrollTo(""",
    )
    replace(
        "\tQScrollArea::scrollContentsBy(dx, dy);\n}",
        """#ifdef Q_OS_WIN
\tconst auto glass = PrepareGlassScroll(this);
#endif
\tQScrollArea::scrollContentsBy(dx, dy);
#ifdef Q_OS_WIN
\tif (glass) {
\t\tRepaintGlassScroll(this);
\t}
#endif
}""",
    )
    replace(
        """void ScrollArea::resizeEvent(QResizeEvent *e) {
\tQScrollArea::resizeEvent(e);""",
        """void ScrollArea::resizeEvent(QResizeEvent *e) {
#ifdef Q_OS_WIN
\tconst auto glass = PrepareGlassScroll(this);
#endif
\tQScrollArea::resizeEvent(e);
#ifdef Q_OS_WIN
\tif (glass) {
\t\tRepaintGlassScroll(this);
\t}
#endif""",
    )
    replace(
        "\tQScrollArea::setWidget(_widget);\n\tif (_widget) {",
        """\tQScrollArea::setWidget(_widget);
#ifdef Q_OS_WIN
\tPrepareGlassScroll(this);
#endif
\tif (_widget) {""",
    )
    path.write_text(source, encoding="utf-8", newline="\n")
    print("Patched:", path)


def patch_dialogs(root: Path) -> None:
    path = root / "Telegram/SourceFiles/dialogs/dialogs_inner_widget.cpp"
    source = path.read_text(encoding="utf-8")
    if MARK in source:
        print("Already patched:", path)
        return

    replacements = [
        (
            "\tsetAttribute(Qt::WA_OpaquePaintEvent, true);\n\tsetAccessibleName(",
            """#ifdef Q_OS_WIN
\t// Transparent AyuGram: rows are semi-transparent, not opaque.
\tsetAttribute(Qt::WA_OpaquePaintEvent, false);
#else
\tsetAttribute(Qt::WA_OpaquePaintEvent, true);
#endif
\tsetAccessibleName(""",
        ),
        (
            "\t\tconst auto cacheAllowed = _rowsScrollCache.scrolling()\n"
            "\t\t\t&& (!videoUserpic || !context.narrow)",
            """\t\tconst auto cacheAllowed = _rowsScrollCache.scrolling()
#ifdef Q_OS_WIN
\t\t\t// RowsScrollCache uses QImage::Format_RGB32 (no alpha);
\t\t\t// never composite it into our translucent window.
\t\t\t&& !window()->testAttribute(Qt::WA_TranslucentBackground)
#endif
\t\t\t&& (!videoUserpic || !context.narrow)""",
        ),
    ]
    for before, after in replacements:
        count = source.count(before)
        if count != 1:
            raise RuntimeError(
                f"{path}: dialogs anchor mismatch (expected 1, found {count}): {before[:70]!r}"
            )
        source = source.replace(before, after, 1)
    path.write_text(source, encoding="utf-8", newline="\n")
    print("Patched:", path)


def patch_peer_lists(root: Path) -> None:
    path = root / "Telegram/SourceFiles/boxes/peer_list_box.cpp"
    source = path.read_text(encoding="utf-8")
    if MARK in source:
        print("Already patched:", path)
        return

    replacements = [
        (
            "\tif (_rowsScrollCache.scrolling()\n"
            "\t\t&& !selected",
            """\tif (_rowsScrollCache.scrolling()
#ifdef Q_OS_WIN
\t\t// Transparent AyuGram: this shared cache stores Format_RGB32.
\t\t// Contacts, members and Calls must not blit opaque cached rows.
\t\t&& !window()->testAttribute(Qt::WA_TranslucentBackground)
#endif
\t\t&& !selected""",
        ),
        (
            "\tfor (const auto &rect : fill) {\n"
            "\t\t\tp.fillRect(rect, _st.item.button.textBg);\n"
            "\t\t}",
            """\tfor (const auto &rect : fill) {
#ifdef Q_OS_WIN
\t\t\tif (window()->testAttribute(Qt::WA_TranslucentBackground)) {
\t\t\t\tp.setCompositionMode(QPainter::CompositionMode_Source);
\t\t\t}
#endif
\t\t\tp.fillRect(rect, _st.item.button.textBg);
#ifdef Q_OS_WIN
\t\t\tp.setCompositionMode(QPainter::CompositionMode_SourceOver);
#endif
\t\t}""",
        ),
        (
            "\tp.fillRect(0, 0, outerWidth, _rowHeight, bg);\n"
            "\trow->paintRipple(",
            """#ifdef Q_OS_WIN
\tif (window()->testAttribute(Qt::WA_TranslucentBackground)) {
\t\t// Replace stale pixels beneath the row, don't blend a translucent
\t\t// row with copies left over from previous scroll/resize frames.
\t\tp.setCompositionMode(QPainter::CompositionMode_Source);
\t}
#endif
\tp.fillRect(0, 0, outerWidth, _rowHeight, bg);
#ifdef Q_OS_WIN
\tp.setCompositionMode(QPainter::CompositionMode_SourceOver);
#endif
\trow->paintRipple(""",
        ),
    ]
    for before, after in replacements:
        count = source.count(before)
        if count != 1:
            raise RuntimeError(
                f"{path}: peer list anchor mismatch (expected 1, found {count}): {before[:70]!r}"
            )
        source = source.replace(before, after, 1)
    path.write_text(source, encoding="utf-8", newline="\n")
    print("Patched:", path)


def patch_info_content(root: Path) -> None:
    path = root / "Telegram/SourceFiles/info/info_content_widget.cpp"
    source = path.read_text(encoding="utf-8")
    if MARK in source:
        print("Already patched:", path)
        return
    replacements = [
        (
            "\tsetAttribute(Qt::WA_OpaquePaintEvent);\n"
            "\t_controller->wrapValue(",
            """#ifdef Q_OS_WIN
\t// Transparent AyuGram: Info/settings layers have alpha, so they
\t// must not advertise opaque backing-store contents to Qt.
\tsetAttribute(Qt::WA_OpaquePaintEvent, false);
#else
\tsetAttribute(Qt::WA_OpaquePaintEvent);
#endif
\t_controller->wrapValue(""",
        ),
        (
            "void ContentWidget::paintEvent(QPaintEvent *e) {\n"
            "\tauto p = QPainter(this);",
            """void ContentWidget::paintEvent(QPaintEvent *e) {
\tauto p = QPainter(this);
#ifdef Q_OS_WIN
\tif (window()->testAttribute(Qt::WA_TranslucentBackground)) {
\t\t// Replace prior frame pixels, including hover/focus artifacts.
\t\t// This is alpha-correct compositing, not a backdrop blur.
\t\tp.setCompositionMode(QPainter::CompositionMode_Source);
\t}
#endif""",
        ),
    ]
    for before, after in replacements:
        count = source.count(before)
        if count != 1:
            raise RuntimeError(
                f"{path}: info content anchor mismatch (expected 1, found {count}): {before[:70]!r}"
            )
        source = source.replace(before, after, 1)
    path.write_text(source, encoding="utf-8", newline="\n")
    print("Patched:", path)


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
    patch_dialogs(root)
    patch_peer_lists(root)
    patch_info_content(root)
    patch_palette(root)
    print("Transparent AyuGram: all patches applied")


if __name__ == "__main__":
    main()
