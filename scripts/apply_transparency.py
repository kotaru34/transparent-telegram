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


def patch_internal_backdrop_blur(root: Path) -> None:
    # Called after patch_window() which already modified mainwindow.cpp.
    # That file contains MARK, so patch_one() would skip it; use a unique
    # feature marker for this independent change instead.
    path = root / "Telegram/SourceFiles/mainwindow.cpp"
    source = path.read_text(encoding="utf-8")
    if "AyuGramGlassBackdropEffect" in source:
        print("Already patched:", path)
        return

    replacements = [
        (
            "#include <QtGui/QWindow>\n",
            """#include <QtGui/QWindow>
#ifdef Q_OS_WIN
#include <QtWidgets/QGraphicsBlurEffect>
#endif
""",
        ),
        (
            "void MainWindow::ensureLayerCreated() {\n"
            "\tif (_layer) {\n"
            "\t\treturn;\n"
            "\t}\n",
            """void MainWindow::ensureLayerCreated() {
\tif (_layer) {
\t\treturn;
\t}
#ifdef Q_OS_WIN
\t// Transparent AyuGram: native Qt blur of the application content
\t// underneath modal layers, not a Windhawk effect on individual
\t// widgets. Remove it once the layer stack is destroyed.
\tif (testAttribute(Qt::WA_TranslucentBackground)
\t\t&& qEnvironmentVariableIsEmpty("AYUGRAM_NO_INTERNAL_BLUR")
\t\t&& _main && !_main->graphicsEffect()) {
\t\tauto blur = new QGraphicsBlurEffect(_main.data());
\t\tblur->setObjectName(QStringLiteral("AyuGramGlassBackdropEffect"));
\t\tblur->setBlurRadius(15.);
\t\tblur->setBlurHints(QGraphicsBlurEffect::QualityHint);
\t\t_main->setGraphicsEffect(blur);
\t}
#endif
""",
        ),
        (
            "void MainWindow::destroyLayer() {\n"
            "\tif (!_layer) {\n"
            "\t\treturn;\n"
            "\t}\n",
            """void MainWindow::destroyLayer() {
\tif (!_layer) {
\t\treturn;
\t}
#ifdef Q_OS_WIN
\tif (_main && _main->graphicsEffect()
\t\t&& _main->graphicsEffect()->objectName()
\t\t\t== QStringLiteral("AyuGramGlassBackdropEffect")) {
\t\t_main->setGraphicsEffect(nullptr);
\t}
#endif
""",
        ),
    ]
    for before, after in replacements:
        count = source.count(before)
        if count != 1:
            raise RuntimeError(
                f"{path}: backdrop blur anchor mismatch ({count}): {before[:85]!r}"
            )
        source = source.replace(before, after, 1)
    path.write_text(source, encoding="utf-8", newline="\n")
    print("Patched:", path)


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


def patch_popup_menu(root: Path) -> None:
    """Keep the themed backdrop visible after popup opening animations end.

    The transition frame contains a background painted into a cached image,
    but live PopupMenu::paintBg() normally paints *only* the fallback shadow.
    On Windows layered windows the live backdrop can disappear when the
    cached frame is discarded and child widgets are shown. The popup root
    now owns the single backdrop; the child Menu skips its duplicate fill.
    """
    popup = root / "Telegram/lib_ui/ui/widgets/popup_menu.cpp"
    menu = root / "Telegram/lib_ui/ui/widgets/menu/menu.cpp"
    if "ayugramGlassPopupRootPaint" in popup.read_text(encoding="utf-8"):
        if "ayugramGlassPopupRootPaint" not in menu.read_text(encoding="utf-8"):
            raise RuntimeError("Partial popup menu patch: missing child painter update")
        print("Already patched:", popup, menu)
        return

    def apply(path: Path, replacements: list[tuple[str, str]]) -> None:
        source = path.read_text(encoding="utf-8")
        for old, new in replacements:
            count = source.count(old)
            if count != 1:
                raise RuntimeError(
                    f"{path}: popup anchor mismatch ({count}): {old[:90]!r}"
                )
            source = source.replace(old, new, 1)
        path.write_text(source, encoding="utf-8", newline="\n")
        print("Patched:", path)

    apply(popup, [
        (
            "\t_useTransparency = Platform::TranslucentWindowsSupported();\n"
            "\tif (_useTransparency) {\n"
            "\t\tsetAttribute(Qt::WA_TranslucentBackground, true);",
            """\t_useTransparency = Platform::TranslucentWindowsSupported();
\tif (_useTransparency) {
\t\tsetAttribute(Qt::WA_TranslucentBackground, true);
#ifdef Q_OS_WIN
\t\t// Transparent AyuGram: native popup owns its live background,
\t\t// including after the initial cached show animation is gone.
\t\t_menu->setProperty("ayugramGlassPopupRootPaint", true);
#endif""",
        ),
        (
            "\t\t\tPlatform::AcceptAllMouseInput(this);\n"
            "\t\t});",
            """\t\t\tPlatform::AcceptAllMouseInput(this);
#ifdef Q_OS_WIN
\t\t\t// Transparent AyuGram: force first live popup repaint just
\t\t\t// after the cached opening animation is discarded.
\t\t\tupdate();
#endif
\t\t});""",
        ),
        (
            "void PopupMenu::paintBg(QPainter &p) {\n"
            "\tif (!_useTransparency) {",
            """void PopupMenu::paintBg(QPainter &p) {
#ifdef Q_OS_WIN
\tif (_useTransparency) {
\t\t// Clear old backing-store pixels and replace them once with
\t\t// the actual themed popup color. Never alpha-blend old frames.
\t\tp.setCompositionMode(QPainter::CompositionMode_Source);
\t\tp.fillRect(rect(), Qt::transparent);
\t\tp.fillRect(_inner, _st.menu.itemBg);
\t\tp.setCompositionMode(QPainter::CompositionMode_SourceOver);
\t\treturn;
\t}
#endif
\tif (!_useTransparency) {""",
        ),
        (
            "\tpaddingWrap->paintRequest(\n"
            "\t) | rpl::on_next([=](QRect clip) {\n"
            "\t\tconst auto top = clip.intersected(",
            """\tpaddingWrap->paintRequest(
\t) | rpl::on_next([=](QRect clip) {
#ifdef Q_OS_WIN
\t\t// The live popup root paints the whole backdrop and padding.
\t\t// Duplicate translucent fills would make these edges darker.
\t\tif (_menu->property("ayugramGlassPopupRootPaint").toBool()) {
\t\t\treturn;
\t\t}
#endif
\t\tconst auto top = clip.intersected(""",
        ),
    ])
    apply(menu, [
        (
            "\tpaintRequest(\n"
            "\t) | rpl::on_next([=](const QRect &clip) {\n"
            "\t\tQPainter(this).fillRect(clip, _st.itemBg);",
            """\tpaintRequest(
\t) | rpl::on_next([=](const QRect &clip) {
#ifdef Q_OS_WIN
\t\t// Transparent AyuGram: the PopupMenu top-level paints this
\t\t// background in its own backing store after animation ends.
\t\tif (property("ayugramGlassPopupRootPaint").toBool()) {
\t\t\treturn;
\t\t}
#endif
\t\tQPainter(this).fillRect(clip, _st.itemBg);""",
        ),
    ])


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
    patch_internal_backdrop_blur(root)
    patch_chat(root)
    patch_main_menu(root)
    patch_scroll(root)
    patch_dialogs(root)
    patch_peer_lists(root)
    patch_info_content(root)
    patch_popup_menu(root)
    patch_palette(root)
    print("Transparent AyuGram: all patches applied")


if __name__ == "__main__":
    main()
