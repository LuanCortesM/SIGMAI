# Self-Management Mode

Self-Management Mode existe para que o SIGMAI consiga cuidar da propria instalacao sem quebrar a Bridge que esta em execucao.

## Comandos

- `self_inspect`
- `self_health_check`
- `self_backup`
- `self_validate_update`
- `self_stage_update`
- `self_apply_update`
- `self_restart_required`
- `self_rollback`
- `self_generate_report`

## Regra de ouro

Nunca use `update_plugin_from_folder` diretamente sobre `sigmai`. O comando retorna erro e orienta o fluxo seguro:

1. `self_validate_update`
2. `self_stage_update` com `dry_run=true`
3. `self_stage_update` com confirmacao
4. `self_backup`
5. `self_apply_update` com confirmacao explicita
6. reiniciar QGIS se `restart_required=true`

## Backup e rollback

Backups sao gravados em `%LOCALAPPDATA%/SIGMAI/backups/` quando possivel. O rollback exige `confirm=true` e `backup_path`.

Hot reload agressivo da propria Bridge continua fora do modo normal porque pode derrubar a resposta HTTP no meio da operacao.

