# MIDI Learn & Control Mapping

Auricle can receive MIDI input and map an incoming controller to a numeric Block Inspector parameter or one of the four global Director macros.

## Connect an input

1. Click **MIDI IN** in the top bar.
2. Select a device and click **Connect**.
3. Right-click a numeric knob in Block Inspector and choose **MIDI Learn this parameter…**. For a global macro, right-click its header slider and choose the corresponding action.
4. Move one control on the external MIDI device. Auricle captures the message type, MIDI channel, controller/note number and input port.

Supported input sources:

- Control Change (CC), using its 0–127 value.
- Note On, using velocity; Note Off and zero-velocity Note On are ignored.
- Pitch Bend, normalized from the full signed 14-bit range.
- Channel Aftertouch.
- Polyphonic Aftertouch, matched by note number.

## Mapping behavior

- A learned mapping is scoped to the selected input port and MIDI channel.
- Each target has one active mapping; learning it again replaces the previous mapping.
- Soft takeover is enabled by default. The controller must reach or cross the parameter's current value before it takes control, preventing an abrupt jump when the mapping is learned or the project is loaded.
- Mapping ranges are taken from the knob's actual minimum and maximum. Integer parameters are rounded before being applied.
- Mappings are stored in the project and restored when it is reopened. The preferred input port is also saved and is reconnected when available.
- Use the **MIDI IN** dialog to enable/disable mappings, remove one mapping, or clear all mappings.
- Right-click a mapped knob and choose **Clear MIDI mapping** to remove its assignment.

MIDI Learn currently targets numeric Block Inspector knobs and the four global macros. It does not yet learn discrete combo-box choices, checkboxes, individual points in automation curves, or arbitrary controls inside third-party plug-ins.
