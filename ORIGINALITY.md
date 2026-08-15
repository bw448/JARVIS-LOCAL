# JARVIS LOCAL originality record

## Product identity

- Product shell: `JARVIS LOCAL`
- Configurable in-app identity: assistant name, owner name, and personality
- Visual concept: a private “signal desk” paired with a circular edge-docking holographic HUD assistant
- Primary palette: graphite glass with switchable cyan, violet, emerald, and amber energy accents

The product shell is deliberately separate from the configured assistant identity. A user may rename the assistant without changing the program or its model directories.

## Original assets and interactions

The following assets are authored in this repository:

- `jarvis/static/mark.svg` and `jarvis/static/jarvis-hud-logo.png` — background-free circular signal identity and its original browser-preview rendering;
- `jarvis/native_floating.py` — original Windows-native transparent vector HUD, animated glass arcs, reactive voice waveform, status orbit, hover treatment, and desktop interactions;
- `jarvis/static/index.html` — responsive signal-desk interface;
- `jarvis/static/styles.css` and the native desktop bridge — responsive glass-panel system, selectable themes, live Windows whole-window opacity, and voice-state animations;
- `jarvis/static/app.js` — conversation, continuous voice detection, transcription, proactive speech, playback, and settings state machine;
- `jarvis/static/floating.html`, `floating.css`, and `floating.js` — browser preview and fallback presentation for the circular HUD; production desktop rendering is handled by the native transparent overlay;

The interface uses no remote font, image, script, tracking pixel, or recovered application asset. All icons are small inline geometric SVG paths authored for this interface.

## Voice implementation boundary

JARVIS LOCAL supplies adapters and installation logic; third-party runtime packages and model weights retain their own licenses. No model weights are committed to this repository. The installer downloads only after an explicit user confirmation and keeps the upstream model license beside the installed model.

## Release checklist

Before redistributing a packaged build:

1. choose and clear a distinct product trademark;
2. lock exact dependency versions and generate an inventory;
3. include every license required by the packages and model archives actually shipped;
4. verify that every voice/model permits the intended commercial or non-commercial use;
5. scan the final package for recovered assets, secrets, test recordings, and private configuration;
6. test offline operation on a clean Windows account.
