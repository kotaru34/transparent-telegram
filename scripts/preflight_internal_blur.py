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
    compile_lifetime_methods(cpp)
    print("Internal Qt modal blur lifetime and alpha inheritance: PASS")



def compile_lifetime_methods(source: str) -> None:
    """Compile the *actual* Windows blur blocks with MSVC Qt-shape stubs.

    This checks C++ syntax without building Qt or the entire Telegram app.
    It cannot replace a real Qt integration compile.
    """
    import subprocess
    import tempfile
    from pathlib import Path

    def block(after: str) -> str:
        at = source.find(after)
        if at < 0:
            raise RuntimeError(f"Missing source function {after!r}")
        start = source.find("#ifdef Q_OS_WIN", at)
        end = source.find("#endif", start)
        if start < 0 or end < 0:
            raise RuntimeError(f"Missing guarded C++ blur in {after!r}")
        return source[start:end + len("#endif")]

    show = block("void MainWindow::ensureLayerCreated() {")
    hide = block("void MainWindow::destroyLayer() {")
    stub = r"""
#include <string>
namespace Qt { enum WidgetAttribute { WA_TranslucentBackground }; }
struct Widget;
class QGraphicsBlurEffect {
public:
    enum BlurHint { QualityHint };
    explicit QGraphicsBlurEffect(Widget*) {}
    void setObjectName(const std::string&) {}
    void setBlurRadius(double) {}
    void setBlurHints(BlurHint) {}
    std::string objectName() const { return {}; }
};
struct Widget {
    QGraphicsBlurEffect *graphicsEffect() { return nullptr; }
    void setGraphicsEffect(QGraphicsBlurEffect*) {}
};
struct WidgetPtr {
    Widget *item = nullptr;
    explicit operator bool() const { return item != nullptr; }
    Widget *operator->() const { return item; }
    Widget *data() const { return item; }
};
bool qEnvironmentVariableIsEmpty(const char*) { return true; }
#define QStringLiteral(x) std::string(x)
struct MainWindow {
    WidgetPtr _main;
    bool testAttribute(Qt::WidgetAttribute) { return true; }
    void beginGlassBlur();
    void endGlassBlur();
};
"""
    contents = (
        stub
        + "void MainWindow::beginGlassBlur() {\n" + show + "\n}\n"
        + "void MainWindow::endGlassBlur() {\n" + hide + "\n}\n"
    )
    with tempfile.TemporaryDirectory(prefix="ayugram-blur-preflight-") as temp:
        f = Path(temp) / "blur.cpp"
        f.write_text(contents, encoding="utf-8")
        for system, flags in (("Windows", ["/DQ_OS_WIN"]), ("other", [])):
            result = subprocess.run(
                ["cl.exe", "/nologo", "/std:c++17", "/Zs", *flags, str(f)],
                capture_output=True, text=True,
            )
            print(f"{system} native modal blur MSVC syntax: {'PASS' if not result.returncode else 'FAIL'}")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            if result.returncode:
                raise RuntimeError("Native modal blur MSVC syntax preflight failed")


if __name__ == "__main__":
    main()
