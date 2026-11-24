# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-24

### Added

- Window (GTK 4 / libadwaita) to turn the fix on and off, with a live level meter, microphone gain,
  optional RNNoise noise suppression and a record-and-play-back test.
- The fix: a PipeWire filter-chain, run as a systemd user service, that keeps only the working
  (right) channel of the built-in microphone, removes hum below 120 Hz and sets the input to +18 dB.
- Previous default input and volume are saved and restored when the fix is turned off.
- Hardware check for the MSI GF63 Thin (Realtek ALC233); a short diagnosis confirms the defect on
  variants that are not verified yet (verified: GF63 Thin 10SC).
- Uninstaller in the app menu, like on Windows: restores the microphone, then removes the program.
- Packages for Fedora/Nobara (rpm), Debian/Ubuntu and derivatives (deb), Arch (pkg.tar.zst and
  PKGBUILD) and a no-root installer for any other distribution.
- Updates through the project's signed apt and dnf repositories, or a weekly signed self-update
  (install.sh) / notification (Arch).
- English and Brazilian Portuguese.

[1.0.0]: https://github.com/junior9283/gf63-mic-fix/releases/tag/v1.0.0
