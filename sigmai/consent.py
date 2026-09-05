"""Controle de consentimento para ações vindas de agentes de IA.

O SIGMAI 0.1.1 tinha um impasse: o proxy MCP forçava ``dry_run=True`` em toda
ação de escrita. Nenhum comando que produzisse um mapa, criasse um layout ou
gravasse um arquivo chegava a executar. A ferramenta era segura por
impossibilidade — e inútil pelo mesmo motivo.

A saída não é afrouxar a validação, é dar ao usuário um lugar para decidir.
Este módulo implementa três modos, do mais restritivo ao mais permissivo:

``read_only``
    Só leitura e simulação. É o padrão. Uma ação de escrita é recusada com uma
    mensagem que explica ao agente o que o usuário precisa fazer para liberar.

``ask``
    Cada ação de escrita abre uma caixa de decisão no QGIS mostrando o que será
    feito, com que parâmetros e em que arquivos. O usuário aprova, nega, ou
    aprova a categoria inteira pelo resto da sessão.

``allow_session``
    Escrita liberada dentro dos limites configurados (pastas de saída, teto de
    execuções). Para quem está trabalhando ativamente com o agente e não quer
    aprovar cada passo.

Em todos os modos há limites de sessão e uma trilha de auditoria, e nenhum modo
libera ``dev_execute_qgis_python``: execução de Python arbitrário continua
exigindo o Modo DEV explícito na interface.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

MODE_READ_ONLY = "read_only"
MODE_ASK = "ask"
MODE_ALLOW_SESSION = "allow_session"
MODES = (MODE_READ_ONLY, MODE_ASK, MODE_ALLOW_SESSION)

DECISION_ALLOWED = "allowed"
DECISION_DENIED = "denied"

#: Ações que nunca são liberadas por consentimento genérico. Instalar, remover
#: ou atualizar plugins e executar Python arbitrário mexem no próprio ambiente
#: que executa o SIGMAI; exigem a interface e o Modo DEV.
NEVER_AUTO_APPROVED = frozenset({
    "dev_execute_qgis_python",
    "install_plugin_from_folder",
    "install_plugin_from_zip",
    "install_qgis_plugin_from_repository",
    "update_plugin_from_folder",
    "uninstall_plugin",
    "enable_plugin",
    "disable_plugin",
    "reload_plugin",
    "download_qgis_plugin_zip",
    "self_apply_update",
    "self_stage_update",
    "self_rollback",
})

#: Categorias apresentadas ao usuário. Aprovar "cartografia" libera compor e
#: exportar mapas, sem liberar edição de dados.
ACTION_CATEGORIES: dict[str, tuple[str, str]] = {
    "cartography": ("Cartografia", "Criar layouts, compor e exportar mapas"),
    "cartographic_design": ("Cartografia", "Aplicar estilos e paletas cartográficas"),
    "symbology": ("Simbologia", "Alterar símbolos, cores e rótulos das camadas"),
    "labels": ("Simbologia", "Alterar símbolos, cores e rótulos das camadas"),
    "layers": ("Camadas", "Carregar e exportar camadas"),
    "layer_tree": ("Camadas", "Reorganizar, agrupar e remover camadas do projeto"),
    "raster": ("Raster", "Processar rasters e gravar arquivos derivados"),
    "vector_tools": ("Vetor", "Operações geométricas que criam novas camadas"),
    "vector_analysis": ("Vetor", "Operações geométricas que criam novas camadas"),
    "selection": ("Seleção", "Selecionar e extrair feições"),
    "processing": ("Processing", "Executar algoritmos do Processing do QGIS"),
    "workflows": ("Fluxos", "Executar fluxos de trabalho compostos"),
    "job_queue": ("Fluxos", "Executar fluxos de trabalho compostos"),
    "atlas_reports": ("Atlas e relatórios", "Gerar atlas, séries e relatórios"),
    "data_sources": ("Fontes de dados", "Conectar a serviços e reparar caminhos"),
    "databases": ("Bancos de dados", "Conectar a bancos e carregar tabelas"),
    "crs_quality": ("Geometria", "Corrigir geometrias inválidas"),
    "expressions": ("Expressões", "Avaliar expressões do QGIS"),
    "user_profile": ("Perfil", "Gravar o perfil de autoria do usuário"),
    "gps_gpx": ("GPS", "Carregar e converter trilhas GPX"),
}

#: Nome canônico da categoria → chave de tradução em ui/strings. O registro
#: (categorias lembradas/recusadas, trilha de auditoria) guarda o canônico em
#: português para que uma troca de idioma não "esqueça" o que o usuário já
#: aprovou; a interface traduz só na hora de mostrar.
CATEGORY_KEYS: dict[str, str] = {
    "Cartografia": "category_cartografia",
    "Simbologia": "category_simbologia",
    "Camadas": "category_camadas",
    "Raster": "category_raster",
    "Vetor": "category_vetor",
    "Seleção": "category_selecao",
    "Processing": "category_processing",
    "Fluxos": "category_fluxos",
    "Atlas e relatórios": "category_atlas",
    "Fontes de dados": "category_fontes",
    "Bancos de dados": "category_bancos",
    "Geometria": "category_geometria",
    "Expressões": "category_expressoes",
    "Perfil": "category_perfil",
    "GPS": "category_gps",
}

DEFAULT_LIMITS: dict[str, int] = {
    "writes_per_session": 200,
    "exports_per_session": 60,
    "processing_runs_per_session": 120,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ConsentRequest:
    """Uma ação de escrita aguardando decisão."""

    action: str
    group: str
    permission_level: str
    params: dict[str, Any]
    client: str
    requested_at: str = field(default_factory=_now)

    @property
    def category(self) -> str:
        return ACTION_CATEGORIES.get(self.group, (self.group, ""))[0]

    @property
    def category_description(self) -> str:
        return ACTION_CATEGORIES.get(self.group, ("", "Ação que altera o projeto ou grava arquivos"))[1]

    def output_paths(self) -> list[str]:
        """Caminhos que a ação pretende escrever, para mostrar ao usuário."""
        found: list[str] = []

        def walk(value: Any, key: str = "") -> None:
            if isinstance(value, dict):
                for nested_key, nested in value.items():
                    walk(nested, str(nested_key))
            elif isinstance(value, list):
                for nested in value:
                    walk(nested, key)
            elif isinstance(value, str) and value:
                lowered = key.lower()
                if lowered.startswith("output") or lowered.endswith("_path") or lowered in {"path", "destination"}:
                    found.append(value)

        walk(self.params)
        return found

    def summary(self) -> str:
        outputs = self.output_paths()
        parts = [f"Ação: {self.action}", f"Categoria: {self.category}"]
        if outputs:
            parts.append("Grava em: " + "; ".join(outputs))
        interesting = {
            key: value for key, value in self.params.items()
            if key in {"layout_name", "layer_id", "layer_ids", "title", "page", "template", "format", "algorithm_id"}
        }
        if interesting:
            parts.append("Parâmetros: " + json.dumps(interesting, ensure_ascii=False)[:300])
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "group": self.group,
            "category": self.category,
            "permission_level": self.permission_level,
            "client": self.client,
            "requested_at": self.requested_at,
            "output_paths": self.output_paths(),
        }


@dataclass
class ConsentDecision:
    """Resultado de uma solicitação."""

    status: str
    reason: str = ""
    remembered: bool = False

    @property
    def allowed(self) -> bool:
        return self.status == DECISION_ALLOWED


class ConsentManager:
    """Guarda o modo, os limites, as aprovações lembradas e a auditoria."""

    def __init__(
        self,
        mode: str = MODE_READ_ONLY,
        limits: dict[str, int] | None = None,
        output_roots: list[str] | None = None,
        prompt: Callable[[ConsentRequest], tuple[str, bool]] | None = None,
        audit_sink: Callable[[dict[str, Any]], None] | None = None,
    ):
        self._lock = threading.RLock()
        self.mode = mode if mode in MODES else MODE_READ_ONLY
        self.limits = dict(DEFAULT_LIMITS)
        if limits:
            self.limits.update({key: int(value) for key, value in limits.items()})
        self.output_roots = [str(Path(root).expanduser()) for root in (output_roots or [])]
        self._prompt = prompt
        self._audit_sink = audit_sink
        self.counters: dict[str, int] = {key: 0 for key in DEFAULT_LIMITS}
        self.remembered_categories: set[str] = set()
        self.denied_categories: set[str] = set()
        self.audit: list[dict[str, Any]] = []

    # -- configuração ----------------------------------------------------
    def set_mode(self, mode: str) -> None:
        with self._lock:
            self.mode = mode if mode in MODES else MODE_READ_ONLY
            self._record("mode_changed", mode=self.mode)

    def set_output_roots(self, roots: list[str]) -> None:
        with self._lock:
            self.output_roots = [str(Path(root).expanduser()) for root in roots if str(root).strip()]
            self._record("output_roots_changed", roots=self.output_roots)

    def set_limit(self, name: str, value: int) -> None:
        with self._lock:
            self.limits[name] = max(0, int(value))
            self._record("limit_changed", limit=name, value=self.limits[name])

    def reset_session(self) -> None:
        with self._lock:
            self.counters = {key: 0 for key in DEFAULT_LIMITS}
            self.remembered_categories.clear()
            self.denied_categories.clear()
            self._record("session_reset")

    def set_prompt(self, prompt: Callable[[ConsentRequest], tuple[str, bool]] | None) -> None:
        self._prompt = prompt

    # -- decisão ---------------------------------------------------------
    def note_never_auto_approved_dry_run(self, action: str, client: str) -> None:
        """Registra que uma ação de ``NEVER_AUTO_APPROVED`` rodou como simulação.

        Simular continua legítimo mesmo para esta lista — nenhuma escrita
        acontece — mas isso passou a depender inteiramente do manipulador da
        ação honrar ``dry_run`` de verdade, já que o clique do usuário foi
        dispensado. Sem este registro, essa dispensa era invisível: não
        aparecia na auditoria de jeito nenhum, distinguível de qualquer outra
        simulação comum. Ver ``bridge_server._check_consent``.
        """
        self._record("dry_run_bypassed_never_auto_approved", action=action, client=client)

    def evaluate(self, request: ConsentRequest) -> ConsentDecision:
        """Decide se a ação pode executar. Bloqueia em modo ``ask``."""
        if request.action in NEVER_AUTO_APPROVED:
            decision = ConsentDecision(
                DECISION_DENIED,
                "Esta ação altera plugins ou executa Python arbitrário. O consentimento genérico não a cobre: "
                "ela precisa ser disparada pelo usuário no painel do SIGMAI, com o Modo DEV quando aplicável.",
            )
            self._record("denied_never_auto", request=request.to_dict(), reason=decision.reason)
            return decision

        with self._lock:
            mode = self.mode
            category = request.category
            remembered = category in self.remembered_categories
            denied_category = category in self.denied_categories

        path_problem = self._check_output_roots(request)
        if path_problem:
            self._record("denied_output_root", request=request.to_dict(), reason=path_problem)
            return ConsentDecision(DECISION_DENIED, path_problem)

        limit_problem = self._check_limits(request)
        if limit_problem:
            self._record("denied_limit", request=request.to_dict(), reason=limit_problem)
            return ConsentDecision(DECISION_DENIED, limit_problem)

        if denied_category:
            reason = (
                f"O usuário negou a categoria '{category}' nesta sessão. Não repita a mesma ação; "
                "explique o que pretendia fazer e peça que ele libere no painel do SIGMAI."
            )
            self._record("denied_remembered", request=request.to_dict())
            return ConsentDecision(DECISION_DENIED, reason)

        if mode == MODE_READ_ONLY:
            reason = (
                "O SIGMAI está em modo somente leitura. Simule com dry_run para mostrar o que faria e peça ao "
                "usuário que mude o modo de acesso no painel do SIGMAI (Somente leitura → Perguntar sempre "
                "ou Liberar nesta sessão)."
            )
            self._record("denied_read_only", request=request.to_dict())
            return ConsentDecision(DECISION_DENIED, reason)

        if mode == MODE_ALLOW_SESSION or remembered:
            self._consume(request)
            self._record("allowed", request=request.to_dict(), mode=mode, remembered=remembered)
            return ConsentDecision(DECISION_ALLOWED, "", remembered=remembered)

        # modo ask
        if self._prompt is None:
            reason = (
                "O modo 'Perguntar sempre' está ativo, mas o painel do SIGMAI não está disponível para "
                "exibir a confirmação. Abra o painel no QGIS e tente novamente."
            )
            self._record("denied_no_prompt", request=request.to_dict())
            return ConsentDecision(DECISION_DENIED, reason)

        try:
            answer, remember = self._prompt(request)
        except Exception as exc:
            self._record("prompt_failed", request=request.to_dict(), error=str(exc))
            return ConsentDecision(DECISION_DENIED, f"Falha ao pedir confirmação ao usuário: {exc}")

        if answer == DECISION_ALLOWED:
            with self._lock:
                if remember:
                    self.remembered_categories.add(request.category)
            self._consume(request)
            self._record("allowed", request=request.to_dict(), mode=mode, remembered=remember)
            return ConsentDecision(DECISION_ALLOWED, "", remembered=remember)

        with self._lock:
            if remember:
                self.denied_categories.add(request.category)
        reason = (
            "O usuário negou esta ação. Não tente de novo com os mesmos parâmetros: "
            "explique o que pretendia e pergunte como ele prefere prosseguir."
        )
        self._record("denied_by_user", request=request.to_dict(), remembered=remember)
        return ConsentDecision(DECISION_DENIED, reason, remembered=remember)

    # -- limites e caminhos ----------------------------------------------
    def _counter_key(self, request: ConsentRequest) -> str:
        if request.group in {"cartography", "atlas_reports"}:
            return "exports_per_session"
        if request.group in {"processing", "vector_tools", "vector_analysis", "raster", "job_queue"}:
            return "processing_runs_per_session"
        return "writes_per_session"

    def _check_limits(self, request: ConsentRequest) -> str:
        key = self._counter_key(request)
        with self._lock:
            limit = self.limits.get(key, 0)
            used = self.counters.get(key, 0)
        if limit and used >= limit:
            return (
                f"Limite de sessão atingido para '{key}' ({used}/{limit}). "
                "Peça ao usuário que aumente o limite ou reinicie a sessão no painel do SIGMAI."
            )
        return ""

    def _consume(self, request: ConsentRequest) -> None:
        key = self._counter_key(request)
        with self._lock:
            self.counters[key] = self.counters.get(key, 0) + 1

    def _check_output_roots(self, request: ConsentRequest) -> str:
        with self._lock:
            roots = list(self.output_roots)
        if not roots:
            return ""
        for raw in request.output_paths():
            try:
                candidate = Path(raw).expanduser().resolve()
            except Exception:
                return f"Caminho de saída inválido: {raw}"
            if not any(_is_within(candidate, Path(root).resolve()) for root in roots):
                return (
                    f"O caminho de saída {candidate} está fora das pastas autorizadas "
                    f"({'; '.join(roots)}). Peça ao usuário que grave dentro de uma pasta autorizada "
                    "ou que acrescente a pasta no painel do SIGMAI."
                )
        return ""

    # -- auditoria -------------------------------------------------------
    def _record(self, event: str, **payload: Any) -> None:
        entry = {"timestamp": _now(), "event": event, **payload}
        with self._lock:
            self.audit.append(entry)
            if len(self.audit) > 500:
                del self.audit[:-500]
        if self._audit_sink is not None:
            try:
                self._audit_sink(entry)
            except Exception:
                pass

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self.mode,
                "mode_label": {
                    MODE_READ_ONLY: "Somente leitura",
                    MODE_ASK: "Perguntar sempre",
                    MODE_ALLOW_SESSION: "Liberado nesta sessão",
                }[self.mode],
                "limits": dict(self.limits),
                "counters": dict(self.counters),
                "output_roots": list(self.output_roots),
                "remembered_categories": sorted(self.remembered_categories),
                "denied_categories": sorted(self.denied_categories),
                "never_auto_approved": sorted(NEVER_AUTO_APPROVED),
                "audit_entries": len(self.audit),
            }

    def recent_audit(self, count: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.audit[-max(1, count):])


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False
