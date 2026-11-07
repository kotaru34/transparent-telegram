# Transparent AyuGram (Windows x64)

Unofficial build of [AyuGram Desktop](https://github.com/AyuGram/AyuGramDesktop) with translucent Qt windows, panels, chat background and theme surface colors for the Windhawk **Translucent Windows** mod.

**Upstream:** AyuGram/AyuGramDesktop release **v7.2.9**, pinned for reproducibility. This is not an official AyuGram build.

## Build on Windows

GitHub Actions uses a hosted **Windows Server 2022 x64** runner, Python 3.10, Qt 6 and MSVC 14.44. No self-hosted Windows laptop is required.

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
