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
- Manual QGIS smoke test passes.
- Plugin loads in a clean QGIS profile.
