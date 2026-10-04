# Plugin Management Mode

O Plugin Management Mode permite que agentes locais inspecionem, validem, empacotem e preparem atualizacoes de plugins QGIS sem executar codigo arbitrario.

## Comandos principais

- `list_installed_plugins`
- `inspect_plugin`
- `validate_metadata_txt`
- `check_plugin_structure`
- `check_plugin_imports`
- `check_plugin_resources`
- `check_plugin_icon`
- `check_plugin_runtime_status`
- `check_plugin_menu_actions`
- `check_plugin_toolbar_actions`
- `check_processing_provider_registration`
- `check_plugin_algorithm_registration`
- `collect_plugin_logs`
- `generate_plugin_report`
- `package_plugin_zip`
- `search_qgis_plugin_repository`
- `download_qgis_plugin_zip`
- `inspect_qgis_plugin_zip`
- `install_plugin_from_zip`
- `install_qgis_plugin_from_repository`
- `install_plugin_from_folder`
- `update_plugin_from_folder`
- `enable_plugin`
- `disable_plugin`
- `reload_plugin`
- `uninstall_plugin`

## Regras

- `check_plugin_imports` usa AST e nao importa o plugin.
- Operacoes de escrita exigem `dry_run` primeiro e confirmacao explicita.
- Busca/download no repositorio oficial exigem `confirm_network=true`.
- Por padrao, downloads de plugin sao permitidos apenas via HTTPS em `plugins.qgis.org`.
- ZIPs de plugin sao inspecionados antes da instalacao e extraidos com protecao contra zip-slip.
- Atualizacao direta da propria Bridge e bloqueada; use Self-Management Mode.
- Pacotes excluem `__pycache__`, `.pyc`, `.git`, `diagnostics`, `test_outputs`, logs e arquivos de sessao/token.

## Fluxo recomendado

1. `inspect_plugin`
2. `validate_metadata_txt`
3. `check_plugin_structure`
4. `check_plugin_imports`
5. `check_plugin_resources`
6. `generate_plugin_report`
7. `package_plugin_zip` com `dry_run=true`
8. `package_plugin_zip` real se o dry-run estiver correto

## Instalacao a partir do repositorio QGIS

Fluxo seguro para instalar plugin externo:

1. `search_qgis_plugin_repository` com `confirm_network=true`
2. `download_qgis_plugin_zip` com `confirm_network=true` e `dry_run=true`
3. `download_qgis_plugin_zip` real para `test_outputs/` ou pasta temporaria controlada
4. `inspect_qgis_plugin_zip`
5. `install_plugin_from_zip` com `dry_run=true`
6. `install_plugin_from_zip` real somente se o relatorio do ZIP estiver valido
7. Reiniciar o QGIS ou desativar/ativar o plugin instalado quando necessario

O comando `install_qgis_plugin_from_repository` orquestra busca, download e instalacao, mas continua exigindo `confirm_network=true`, permissao `plugin_write`, confirmacao e respeito ao `dry_run`. O SIGMAI nao habilita plugins desconhecidos automaticamente nem libera algoritmos Processing externos sem allowlist.
