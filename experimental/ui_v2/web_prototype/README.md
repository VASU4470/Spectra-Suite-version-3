# SpectraSuite UI v2 Browser Prototype

This is a **design-only static prototype**. It is not connected to the production SpectraSuite launcher, scientific calculations, updater, installer, or release metadata.

## What is currently interactive

- Office-style ribbon tabs
- Project Explorer collapse/expand
- Data-table and plot documents visible together
- Tile / maximize / restore document behavior
- Active document changes command context
- Dummy FT-IR plot and data table
- Axis Properties dialog
- Basic command-search/status feedback

## Fastest preview

After checking out `feature/ui-workspace-redesign`, open:

`experimental/ui_v2/web_prototype/index.html`

directly in a browser.

## Local web server

For a browser URL such as `http://localhost:8765`:

### Windows

```powershell
cd experimental\ui_v2\web_prototype
py -m http.server 8765
```

If `py` is unavailable:

```powershell
python -m http.server 8765
```

Then open:

`http://localhost:8765`

### macOS / Linux

```bash
cd experimental/ui_v2/web_prototype
python3 -m http.server 8765
```

Then open:

`http://localhost:8765`

Stop the local server with `Ctrl+C`.

## Isolation

Do not publish this directory through GitHub Pages while it is an experimental design unless deliberate public preview is approved. The repository is public, so branch contents are visible to people browsing GitHub, but this prototype is not part of any SpectraSuite release or updater channel.
