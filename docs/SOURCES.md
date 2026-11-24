# Sources, provenance and licensing

Research snapshot:2026-11-24. Exact commits are preserved in [source-review.json](../evidence/source-review.json).

| Primary project | Pinned commit | Use here |
|---|---|---|
| [alphaorderly/ultimate-bluetooth-updater](https://github.com/alphaorderly/ultimate-bluetooth-updater/tree/50ddc817b63ee548642436d9d272d019205fb73f) |50ddc817b63ee548642436d9d272d019205fb73f| Exact first-generation wake/remap review. Its patch overlaps our timing stub; no full merge or wake claim. MIT project. |
| [gomezluisj/8bitdo-ultimate-re](https://github.com/gomezluisj/8bitdo-ultimate-re/tree/0e4fc809d46764a61110ac6c716dc4482dc0b890) |0e4fc809d46764a61110ac6c716dc4482dc0b890| Exact80NA1.11 wake/reconnect and XIP-readback concept. No latency patch copied. MIT project. |
| [craigmdennis/8bitdo-ultimate-toolkit](https://github.com/craigmdennis/8bitdo-ultimate-toolkit/tree/4539ad29e35edf4a7974746b8735b63769673a0b) |4539ad29e35edf4a7974746b8735b63769673a0b| Different Ultimate2C/Telink hardware. Conceptual activity/scan comparison only; no source or binary incorporated. GPL project, not relicensed here. |
| [MiguelSanzBr/8bitdo-ultimate2-linux](https://github.com/MiguelSanzBr/8bitdo-ultimate2-linux/tree/03957a0c165b214a501337279149144e36764af3) |03957a0c165b214a501337279149144e36764af3| First-generation configuration protocol reference only. |
| [AeroModes/8cryptdo](https://github.com/AeroModes/8cryptdo) |Vendored file pinned below| Actual encryption/decryption dependency, MIT, unmodified source and license in vendor/. |

The root MIT license covers original code and documentation in this repository.
Manufacturer firmware, ROM and Windows binaries remain third-party property and are not included.
Patch recipes contain small preimage/change spans and original injected code; generated complete firmware files stay local.
No other project's Ultimate2/2C firmware or GPL source is embedded.

8cryptdo is a saved source snapshot (no upstream git commit recorded), not claimed to match current upstream HEAD.
Its exact vendored file hash is listed in [vendor/provenance.json](../vendor/provenance.json).
Retain [its MIT notice](../vendor/LICENSE-8cryptdo.txt) when redistributing this package.
The standalone executable also embeds Python3.11 and the PyInstaller bootloader;
their notices are included as `vendor/LICENSE-Python.txt` and `vendor/LICENSE-PyInstaller.txt`.
PyInstaller's bootloader linking exception applies; it does not make the original patcher GPL.

Official sources:

- [Original Ultimate Bluetooth product](https://www.8bitdo.com/ultimate-bluetooth-controller/)
- [Manufacturer support/history](https://support.8bitdo.com/#data_history_ultimate_bluetooth)
- [Manufacturer updater](https://support.8bitdo.com/firmware-updater.html)
- [Microsoft USB endpoint interval interpretation](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbspec/ns-usbspec-_usb_endpoint_descriptor)
- [Microsoft XINPUT_STATE / packet number](https://learn.microsoft.com/en-us/windows/win32/api/xinput/ns-xinput-xinput_state)

Exact official firmware URLs, sizes and SHA-256 values are in [stock.json](../patches/stock.json).
The official catalog's MD5 field matched the decimal file-size string in the acquired responses, not file content,
so it is not used for integrity. This project pins independently computed SHA-256 values.
The firmware endpoint uses HTTP; a changed byte or wrong size is rejected. No hash override is provided.
The original updater2.52 archive is downloaded by HTTPS and pinned, as are its executable and native DLL.

Community reports of disconnection/power-off were useful leads, not proof of this firmware fault.
Moving a2.4G receiver to the dock still uses2.4G radio; it changes USB placement/path, not automatically to Bluetooth.
The final firmware work does not claim to establish the cause of those reports.
