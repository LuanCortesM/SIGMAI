# QGIS Plugin Publication Checklist

- `metadata.txt` has required fields.
- Plugin has a clear name, description, version, author, and minimum QGIS version.
- Plugin includes an icon.
- No development-only bridge features are enabled without user action.
- No remote server is exposed.
- Errors are visible and logged.
- README explains installation and use.
- License is included.
- ZIP package does not include `__pycache__`, `.pyc`, logs, or local secrets.
- `python tools/validate_plugin_package.py` passes and `xvfb-run -a python tools/release_battery.py --full --data <test shapes>` prints `LIBERADO`.
- Manual QGIS smoke test passes.
- Plugin loads in a clean QGIS profile — including QGIS 4.x (Qt6): open the SIGMAI panel, start the bridge, run the connection self-test. Not provable from the headless battery.
- Live network paths tried by hand: install a plugin from plugins.qgis.org through `install_plugin_from_repository`, and load an XYZ basemap with `load_xyz_tile_layer`. The battery exercises these against local servers only.
