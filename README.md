# Range Tint

Created by [JazzleyVFX](https://jazzley.nl).

Range Tint is a Viewer-only range indicator for Foundry Nuke and NukeX. It
shows whether the current frame is inside or outside one or more delivery
ranges without modifying the image or node graph.

## Features

- Colored rails around the displayed frame.
- Rails remain outside the image whenever the frame edge is visible.
- When zoomed beyond the Viewer, a small indicator remains at the safe canvas
  edge without covering Viewer controls, rulers, status text, or the timeline.
- Native Viewer-transform tracking for pan, zoom, Fit, resize, and floating
  Viewers.
- Immediate event-driven updates while dragging.
- A thin range strip at the bottom of Nuke's TimeSlider, away from frame
  numbers and tick labels.
- Draggable `RANGE ON/OFF` Viewer button.
- Configurable keyboard shortcuts.
- Multiple inclusive ranges, for example `1001-1050, 1075-1100`.
- Settings stored as hidden Root knobs in the current `.nk` project.
- No Viewer Input Process, helper nodes, or render-time image changes.

## Compatibility

The included Windows DLL targets:

- Nuke/NukeX 14.1v5
- Windows x64
- Visual Studio 2019 runtime (v142)

Rebuild the native bridge against the matching Nuke NDK when targeting another
Nuke release.

## Installation

1. Download `RangeTint-3.2.5-Nuke14.1-Windows.zip` from GitHub Releases.
2. Copy the included `RangeTint` directory to:

   ```text
   %USERPROFILE%\.nuke\RangeTint
   ```

3. Add this line to `%USERPROFILE%\.nuke\init.py` if it is not already there:

   ```python
   nuke.pluginAddPath("./RangeTint")
   ```

4. Restart Nuke and choose **Range Tint > Start**.

Range Tint remains passive at startup. Loading the menu does not create timers
or Viewer widgets until **Start** is selected.

## Settings

Open **Range Tint > Settings...**. Available settings include:

- Frame ranges
- Inside-range and outside-range colors
- Border thickness
- Timeline opacity and height
- Overlay enabled state
- Viewer-button position
- Keyboard shortcuts

The Viewer button can also be repositioned by dragging it.

## Keyboard shortcuts

The following actions have editable shortcut fields in Settings:

| Action | Default |
| --- | --- |
| Open settings | `Ctrl+Alt+R` |
| Toggle overlay | `Ctrl+Alt+T` |
| Refresh Viewers | Unassigned |

Click a shortcut field and press the desired combination. Each action accepts
exactly one combination; pressing a new combination replaces the previous one.
Use Backspace or Delete to clear it. Duplicate shortcuts are rejected. Saving
Settings immediately re-registers the Nuke menu with the new assignments.

Valid shortcut keys are letters, numbers, function keys, and navigation keys,
with optional Ctrl, Alt, Shift, or Meta modifiers. Text symbols such as `®` or
`©` are rejected. On Windows, physical virtual-key codes are used so AltGr
keyboard layouts cannot turn `Ctrl+Alt+R` into a symbol.

## Reload during development

Run this in Nuke's Script Editor:

```python
import importlib
import range_tint

range_tint.stop()
importlib.invalidate_caches()
range_tint = importlib.reload(range_tint)
range_tint.install()
range_tint.diagnostics()
```

## Building the native bridge

Requirements:

- Nuke 14.1 NDK
- Visual Studio 2019 Build Tools with the C++ workload
- CMake

From a Visual Studio x64 developer shell:

```powershell
cmake -S native -B native/build -G "Visual Studio 16 2019" -A x64 `
  -DNuke_DIR="C:/Program Files/Nuke14.1v5/cmake"
cmake --build native/build --config Release
Copy-Item native/build/Release/range_tint_native.dll RangeTint/bin/
```

The native bridge is read-only. It exposes Nuke's current
`ViewerWindowFormatContext` to the Python UI and does not create nodes, draw
into the image, or register persistent native callbacks.

## License

[MIT](LICENSE)
