# Cthulu System Map Guide

## Open the map

The interactive architecture map is [`tools/system_map.html`](system_map.html). Open it in a browser from the repository. The map is a self-contained HTML page with embedded graph data; it is not connected to the running Cthulu process or a live source-code analyzer.

The graph can be searched and rearranged, but its embedded component details, version label, line/function totals, critical-issue count, and Smart Suggestions are a historical snapshot. Do not use those numbers or recommendations as current code metrics, a security review, a health check, or deployment guidance. Confirm architecture and runtime behavior in the source and current documentation.

## Map controls

- **Search** filters/highlights matching component names.
- **Force**, **Tree**, and **Radial** select graph layouts.
- Drag nodes to rearrange them and drag the background to pan.
- **Reset View** restores the initial framing.
- **Expand All** spreads out the graph.
- **Export** saves the current visualization.

## Repository quick actions

The separate root-level [`start_here.html`](../start_here.html) page has a Quick actions toolbar. These links point to existing repository files; they do not execute scripts from inside a browser. Depending on browser settings, clicking a `.bat` or `.ps1` link may show, open, or download the file. Use File Explorer to run the appropriate script.

| Toolbar label | Existing target | Important detail |
|---|---|---|
| **Install requirements** | `run_cthulu_startup.bat` | Runs dependency setup and continues to the startup menu; it is not a requirements-only action. |
| **Setup Cthulu** | `scripts/setup.ps1` | An older setup helper. It does not replace the first-run wizard that collects MT5 credentials and writes `config.json`, `config_multi.json`, and the Agent environment. |
| **Launch Cthulu** | `Cthulu Launcher.bat` | The normal double-click launcher after first-run setup. |

For a fresh source checkout, use the current wizard directly from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File .\installer\cthulu_first_run_setup.ps1
```

Then double-click `Cthulu Launcher.bat` in File Explorer. See the [Quick Start](../docs/02_QUICKSTART.md) for the complete installation, safety, and troubleshooting steps.
