"""Garante que o Processing do QGIS esteja utilizável, e explica quando não está.

Dentro do QGIS com interface, o plugin Processing registra os provedores na
inicialização e tudo simplesmente funciona. Fora disso — QGIS iniciado sem
interface, plugin Processing desativado pelo usuário, ou um perfil recém-criado
— o registro fica vazio, e o SIGMAI respondia apenas "Processing algorithm was
not found". Para um agente de IA isso é um beco sem saída: ele não sabe se
errou o identificador, se o algoritmo exige um plugin, ou se o QGIS é que não
está pronto, e tende a tentar variações do nome às cegas.

Este módulo faz duas coisas: tenta inicializar o Processing uma vez antes de
desistir, e transforma a falha numa mensagem que diz o que foi encontrado e
qual é o próximo passo.
"""

from __future__ import annotations

from typing import Any

from ..validators import ValidationError

#: A inicialização é cara e idempotente: uma tentativa por sessão basta.
_ATTEMPTED = False
_LAST_ERROR = ""


def ensure_processing_ready() -> bool:
    """Inicializa o Processing se ainda não estiver. Devolve se há algoritmos."""
    global _ATTEMPTED, _LAST_ERROR

    if _registered_algorithm_count() > 0:
        return True
    if _ATTEMPTED:
        return _registered_algorithm_count() > 0

    _ATTEMPTED = True
    try:
        from processing.core.Processing import Processing  # type: ignore

        Processing.initialize()
    except Exception as exc:
        _LAST_ERROR = f"{type(exc).__name__}: {exc}"

    # Os algoritmos nativos (qgis:, native:) vêm de um provedor separado que o
    # plugin Processing registra; sem interface é preciso registrá-lo à mão.
    try:
        from qgis.analysis import QgsNativeAlgorithms  # type: ignore
        from qgis.core import QgsApplication  # type: ignore

        registry = QgsApplication.processingRegistry()
        if registry.providerById("native") is None:
            registry.addProvider(QgsNativeAlgorithms())
    except Exception as exc:
        if not _LAST_ERROR:
            _LAST_ERROR = f"{type(exc).__name__}: {exc}"

    return _registered_algorithm_count() > 0


def _registered_algorithm_count() -> int:
    try:
        from qgis.core import QgsApplication  # type: ignore

        return len(QgsApplication.processingRegistry().algorithms())
    except Exception:
        return 0


def _registry_state() -> dict[str, Any]:
    try:
        from qgis.core import QgsApplication  # type: ignore

        registry = QgsApplication.processingRegistry()
        providers = [provider.id() for provider in registry.providers()]
        return {"providers": sorted(providers), "algorithm_count": len(registry.algorithms())}
    except Exception:
        return {"providers": [], "algorithm_count": 0}


def resolve_algorithm(algorithm_id: str) -> Any:
    """Busca um algoritmo, inicializando o Processing se preciso.

    Levanta ``ValidationError`` com um diagnóstico utilizável quando não acha.
    """
    from qgis.core import QgsApplication  # type: ignore

    registry = QgsApplication.processingRegistry()
    algorithm = registry.algorithmById(algorithm_id)
    if algorithm is not None:
        return algorithm

    if ensure_processing_ready():
        algorithm = QgsApplication.processingRegistry().algorithmById(algorithm_id)
        if algorithm is not None:
            return algorithm

    state = _registry_state()
    details: dict[str, Any] = {"algorithm": algorithm_id, **state}
    if _LAST_ERROR:
        details["initialization_error"] = _LAST_ERROR

    if state["algorithm_count"] == 0:
        message = (
            "O Processing do QGIS não tem nenhum algoritmo registrado, então nenhum identificador "
            "vai funcionar. Não é erro no nome do algoritmo. Verifique se o plugin Processing está "
            "ativado em Complementos > Gerenciar e instalar complementos > Instalados."
        )
        if _LAST_ERROR:
            message += f" A inicialização automática falhou com: {_LAST_ERROR}"
        raise ValidationError("PROCESSING_NOT_INITIALIZED", message, details)

    suggestions = _similar_algorithms(algorithm_id)
    details["similar"] = suggestions
    message = (
        f"Algoritmo não encontrado: {algorithm_id}. "
        f"Há {state['algorithm_count']} algoritmos registrados nos provedores "
        f"{', '.join(state['providers']) or 'nenhum'}."
    )
    if suggestions:
        message += " Nomes parecidos: " + ", ".join(suggestions) + "."
    else:
        message += " Use list_processing_algorithms para ver os identificadores válidos."
    raise ValidationError("PROCESSING_ALGORITHM_NOT_FOUND", message, details)


def _similar_algorithms(algorithm_id: str, limit: int = 5) -> list[str]:
    """Identificadores parecidos, para o agente corrigir em vez de adivinhar."""
    try:
        import difflib

        from qgis.core import QgsApplication  # type: ignore

        available = [algorithm.id() for algorithm in QgsApplication.processingRegistry().algorithms()]
    except Exception:
        return []

    wanted = algorithm_id.split(":")[-1].lower()
    scored = difflib.get_close_matches(algorithm_id, available, n=limit, cutoff=0.6)
    if scored:
        return scored
    return [item for item in available if wanted and wanted in item.split(":")[-1].lower()][:limit]


def run_algorithm(algorithm_id: str, parameters: dict[str, Any], feedback: Any = None) -> dict[str, Any]:
    """Executa um algoritmo do Processing, com ou sem o plugin Processing.

    ``processing.run`` é a via de conveniência, mas vem do *plugin* Processing:
    se o usuário o desativou, ou se o QGIS foi iniciado sem interface, o import
    falha e o SIGMAI respondia "QGIS Processing is not available" — o que soa
    como se o QGIS não tivesse Processing, quando na verdade o núcleo tem tudo
    o que é preciso.

    A queda para a API de núcleo (``QgsProcessingAlgorithm.run``) elimina essa
    dependência. O resultado é o mesmo dicionário de saídas.
    """
    algorithm = resolve_algorithm(algorithm_id)

    try:
        import processing  # type: ignore

        return processing.run(algorithm_id, parameters, feedback=feedback) if feedback else processing.run(algorithm_id, parameters)
    except ImportError:
        pass  # sem o plugin Processing; segue pela API de núcleo

    from qgis.core import QgsProcessingContext, QgsProcessingFeedback, QgsProject  # type: ignore

    context = QgsProcessingContext()
    try:
        context.setProject(QgsProject.instance())
    except Exception:
        pass
    results, successful = algorithm.run(parameters, context, feedback or QgsProcessingFeedback())
    if not successful:
        raise ValidationError(
            "PROCESSING_RUN_FAILED",
            f"O algoritmo {algorithm_id} foi encontrado mas não concluiu. "
            "Confira os parâmetros com get_processing_algorithm_info.",
            {"algorithm": algorithm_id, "parameters": sorted(parameters)},
        )
    # As camadas criadas ficam no armazenamento temporário do contexto, que é
    # destruído ao final. Transferi-las para o projeto é o que processing.run
    # faz por baixo.
    #
    # A DIREÇÃO IMPORTA. transferLayersFromStore(outro) move as camadas DE
    # 'outro' PARA 'self'. Escrever ao contrário move as camadas do projeto
    # para o armazenamento temporário — e o usuário perde o projeto inteiro no
    # instante em que roda um buffer.
    try:
        QgsProject.instance().layerStore().transferLayersFromStore(context.temporaryLayerStore())
    except Exception:
        pass
    return dict(results)
