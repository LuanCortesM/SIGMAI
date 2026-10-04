# Plugin Update Safety

Toda escrita em plugins deve ser segura, auditavel e reversivel.

## Politica

- `plugin_write`: exige confirmacao.
- `dangerous_plugin_write`: exige confirmacao, backup e relatorio.
- Operacoes destrutivas suportam `dry_run` quando possivel.
- A propria Bridge e protegida por roteamento para Self-Management Mode.

## Confirmacao

Use um destes parametros quando a operacao ja foi revisada:

```json
{
  "confirm": true
}
```

ou uma confirmacao especifica, como:

```json
{
  "confirm_self_apply_update": true
}
```

## Nao fazer

- Nao atualizar `sigmai` diretamente.
- Nao apagar plugin sem backup.
- Nao empacotar tokens, sessoes, diagnostics ou outputs locais.
- Nao tentar reload agressivo da propria Bridge.
