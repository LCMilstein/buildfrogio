# Changelog

All notable changes to the 3D-Workshop project will be documented in this file.

## [Unreleased]

### Added
- **Slicer Thumbnails**: Added `thumbnails = 256x256/PNG, 16x16/PNG` to all `bambu_*.ini` preset files. When users slice models through the app, the generated `.gcode`/`.3mf` will now include base64 PNG previews that natively display on Bambu Lab printer touchscreens.
- **Live Print Time Estimation**: Enabled `gcode_comments = 1` in all slicing presets. The PrusaSlicer engine will now inject standard `M73` tags throughout the gcode stream so the printer can accurately display elapsed and remaining times on its screen.
- **Build123d Best Practices Guide**: Authored a detailed `/build123d_best_practices.md` document outlining how to mathematically prevent printing failures, floating parts, and ghost geometry when extending existing STEP models via script.

### Changed
- **AI System Prompt**: Upgraded the core system prompt in `server.py` to enforce strict geometrical integrity for LLM agents generating Build123d code. Agents are now required to:
  - Perform internal hollowing operations on STEP models before splitting/extending.
  - Extract the exact `outer_wire()` mathematical cross-sections for gap-bridging to prevent visible seams or overhanging lips.
  - Assemble snap-fit lid components on the `Z=0` axis as merged single bodies, guaranteeing support-free flat bed printing.
