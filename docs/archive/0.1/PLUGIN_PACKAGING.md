# Plugin Packaging

O comando `package_plugin_zip` gera um ZIP de plugin QGIS com manifest e exclusoes seguras.

## Exemplo

```json
{
  "action": "package_plugin_zip",
  "dry_run": true,
  "params": {
    "plugin_name": "sigmai",
    "output_path": "test_outputs/sigmai_package.zip"
  }
}
```

Depois do dry-run:

```json
{
  "action": "package_plugin_zip",
  "params": {
    "plugin_name": "sigmai",
    "output_path": "test_outputs/sigmai_package.zip",
    "confirm_overwrite": true
  }
}
```

## Exclusoes

- `__pycache__/`
- `.pyc`, `.pyo`
- `.git/`
- `diagnostics/`
- `test_outputs/`
- logs locais
- arquivos de sessao ou token

O comando valida `metadata.txt` antes de criar o pacote real.
