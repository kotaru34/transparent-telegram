# Transparent Telegram (Windows x64)

This repository builds an unofficial **Windows-only, Qt6, per-pixel translucent** version of Telegram Desktop. It stores a repeatable source patch and GitHub Actions workflow, not the huge upstream source tree.

**Upstream target:** [Telegram Desktop v7.4.1](https://github.com/telegramdesktop/tdesktop/releases/tag/v7.4.1).
**Runner:** `windows-latest` (Windows x64; not Linux).

## Build and download

Run **Actions → Transparent Telegram - Windows x64 → Run workflow**. Successful builds upload a portable `Telegram.exe` under **Artifacts**. This compiles Telegram and third-party dependencies from source and is resource-intensive.

### Production API credentials required for normal login

Obtain your own `api_id` and `api_hash` from [my.telegram.org](https://my.telegram.org), then set **Settings → Secrets and variables → Actions → Repository secrets**:

- `TDESKTOP_API_ID`
- `TDESKTOP_API_HASH`

Do not commit the hash. If neither secret is set, the workflow builds with upstream `TDESKTOP_API_TEST=ON`, and labels the artifact **TEST-ONLY**. That executable is *not suitable for a normal Telegram account login*. If only one secret is set, the build fails intentionally. See [upstream API instructions](https://github.com/telegramdesktop/tdesktop/blob/v7.4.1/docs/api_credentials.md).

## Patch scope

- Qt per-pixel alpha on the main Telegram window (`WA_TranslucentBackground`).
- Translucent UI palette for window backgrounds, dialog list, header/title, menus, composer, popups, emoji panel and chat bubbles – retaining the base RGB values of the active light/dark/custom theme and leaving text/icons unchanged.
- Suppresses opaque chat wallpaper drawing in the live chat widget; image/preview offscreen rendering is not changed.
- Disables auto-update so an official binary does not overwrite the fork.

## Windhawk and caveats

Windows 11 transparency effects should be enabled. Optionally use the [Translucent Windows Windhawk mod](https://windhawk.net/mods/translucent-windows) for `Telegram.exe`. **Windhawk warns that its translucent effects do not generally work on Qt apps with application-painted backgrounds**. This patch attempts per-pixel translucency natively, but *acrylic blur from Windhawk is not guaranteed*. Some popups, embedded media, calls and separately rendered UI surfaces may remain opaque. Do not assume that an untested build is visually correct – test it on Windows 11.

Builds here are unofficial, unsigned and not guaranteed to work. Back up local Telegram data before experimenting. The source checkout and submodules retain their own upstream licensing terms: [LICENSE](https://github.com/telegramdesktop/tdesktop/blob/v7.4.1/LICENSE), [LEGAL](https://github.com/telegramdesktop/tdesktop/blob/v7.4.1/LEGAL).

## Maintenance

`scripts/apply_transparency.py` uses exact source anchors and fails rather than silently producing an unpatched executable if the pinned upstream layout changes. For newer Telegram versions, review the code and update both the pin and patch.