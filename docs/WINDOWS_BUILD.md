# Windows build

1. Install **Python 3.12 x64** from python.org with the *Python Launcher* (`py`) enabled.
2. Run `setup_windows.bat`. It creates `.venv` and installs `requirements-windows.txt`
   (runtime dependencies plus PyInstaller).
3. Run `build_windows.bat`. It removes old `build\` and `dist\` folders and runs
   PyInstaller with `Auricle.spec`.
4. The result is a one-folder application: `dist\Auricle\Auricle.exe`. Distribute the
   whole `dist\Auricle` folder.

Notes

- MIDI goes through `mido` with the `python-rtmidi` backend; the spec lists the backend
  modules as hidden imports because mido loads them dynamically.
- Windows has no built-in virtual MIDI port. Install a loopback driver such as loopMIDI
  to route Auricle into a DAW, then choose that port as a block output.
- The application is built without a console window. Transport errors are written to
  `auricle_transport.log` in the working directory.
