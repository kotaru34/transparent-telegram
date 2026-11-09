# Transparent AyuGram (Windows x64)

Unofficial build of [AyuGram Desktop](https://github.com/AyuGram/AyuGramDesktop) with translucent Qt windows, panels, chat background and theme surface colors for the Windhawk **Translucent Windows** mod.

**Upstream:** AyuGram/AyuGramDesktop release **v7.2.9**, pinned for reproducibility. This is not an official AyuGram build.

## Build on Windows

GitHub Actions uses a hosted **Windows Server 2022 x64** runner, Python 3.10, Qt 5 (upstream v7.2.9 default) and MSVC 14.44. No self-hosted Windows laptop is required.

Configure two **Repository secrets** in **Settings > Secrets and variables > Actions**:

- `TDESKTOP_API_ID` – numeric Telegram API ID.
- `TDESKTOP_API_HASH` – Telegram API hash.

**Do not commit or share these credentials.** The workflow requires both secrets before building, and does not fall back to Telegram's test environment.

Trigger **Actions > Transparent AyuGram - Windows x64 > Run workflow** (or push to main). After a successful build, download the artifact `transparent-ayugram-windows-x64-production`, unzip and run `AyuGram.exe`. Auto-update is disabled to prevent upstream updates from overwriting the patch.

## Source patch

The script `scripts/apply_transparency.py` changes AyuGram's window initialization and painting, the opaque chat wallpaper, and common theme surface alpha values in AyuGram's own **lib_ui** fork. It retains the original theme RGB values.

Qt and Windhawk may behave differently across Windows builds, and some custom surfaces may still paint opaque. Actual rendering has not yet been visually verified on a Windows desktop.

## Build resource usage

Compiling third-party dependencies and Qt from source is resource-intensive. The workflow uses Windows-hosted CI rather than requiring your personal machine. Until GitHub Actions completes with success, the project should be treated as source and build instructions rather than a ready executable.

## CI resource safety

The full Windows build is gated by a short Windows preflight job that applies all patches to the pinned upstream source files before dependency preparation. The build removes the upstream CMake `/MP` option and uses one MSBuild worker to prevent MSVC `C1060` heap exhaustion on standard GitHub-hosted Windows runners. This may increase build time but avoids uncontrolled compiler concurrency; dependency/Qt caches are preserved.

## CI policy

Pushing to `main` runs **only** inexpensive Windows patch preflight checks, including an isolated MSVC syntax compile of the modified chat background for Windows and non-Windows paths. The costly full binary build normally runs **only** through **Actions > Transparent AyuGram - Windows x64 > Run workflow**. A one-off rebuild can also be triggered by a commit whose message includes `[run-full-build]`; ordinary pushes remain preflight-only. This deliberately prevents repeated multihour compilations after every fix. The syntax check is narrow and does not guarantee the complete application links or runs.

## Translucent scroll and resize compositing

For the Windows translucent build, scrollable list content cannot use the
usual opaque backing-store optimizations. The transparency patch applies an
alpha-safe painting policy to the shared `Ui::ScrollArea`: disables
`WA_OpaquePaintEvent` and `WA_StaticContents` on its viewport and
scrolling content and invalidates only the visible region after scrolling or
resizing. It also disables the dialogs' temporary `RowsScrollCache` whenever
the top-level window is translucent, because that cache uses
`QImage::Format_RGB32` and loses the alpha channel.

This change does not introduce per-widget Windhawk effects or new fixed
palette opacities. It prioritizes correct glass rendering over the RGB32
scroll cache optimization and may increase CPU use during continuous list
scrolling. The window-level blur remains Windhawk's responsibility. Native
Qt Widgets do not provide CSS `backdrop-filter` for sibling content; a
true intra-window backdrop blur would require an explicit offscreen capture
and blur compositor and is not implemented here.

Run `scripts/preflight_glass_cpp.py` in the Windows Actions preflight to
syntax-check the exact patched scroll methods with MSVC in both Windows and
ordinary configurations. This does not replace a full integration build or
visual testing.
