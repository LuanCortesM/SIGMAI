"""EPS vetorial a partir do PDF do QGIS, pelo Ghostscript.

O QGIS não exporta EPS, e várias revistas o pedem para traço (Springer,
Elsevier, Taylor & Francis). O Ghostscript converte o PDF da figura em EPS
sem rasterizar: linhas e textos continuam vetoriais, com as fontes embutidas.
O QGIS para Windows instala o Ghostscript na própria pasta ``bin``; no Linux e
no macOS ele costuma estar no sistema. Sem ele, o SIGMAI recusa o pedido antes
de compor, dizendo o que fazer.

Sem PyQGIS de propósito: procura e conversão testáveis fora do QGIS.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

#: Nomes do executável do Ghostscript, na ordem em que são procurados.
GHOSTSCRIPT_NAMES = ("gswin64c", "gswin32c", "gs")
#: Tempo máximo da conversão (s). Uma figura A0 cheia leva poucos segundos.
CONVERSION_TIMEOUT_S = 180


def _candidate_dirs(extra: list[str] | None = None) -> list[Path]:
    """Pastas onde o QGIS costuma pôr o Ghostscript, além do PATH."""
    dirs: list[Path] = [Path(d) for d in (extra or []) if d]
    executable = Path(sys.executable).resolve()
    # OSGeo4W: <raiz>\bin\python*.exe ou <raiz>\apps\Python312\python.exe;
    # o Ghostscript fica em <raiz>\bin.
    for parent in (executable.parent, *executable.parents):
        dirs.append(parent / "bin")
        dirs.append(parent)
        if len(dirs) > 12:
            break
    return dirs


def find_ghostscript(extra_dirs: list[str] | None = None) -> str | None:
    """Caminho do Ghostscript de linha de comando, ou ``None`` se não há."""
    for name in GHOSTSCRIPT_NAMES:
        found = shutil.which(name)
        if found:
            return found
    suffix = ".exe" if os.name == "nt" else ""
    for folder in _candidate_dirs(extra_dirs):
        for name in GHOSTSCRIPT_NAMES:
            candidate = folder / f"{name}{suffix}"
            if candidate.is_file():
                return str(candidate)
    return None


def eps_command(ghostscript: str, pdf_path: str, eps_path: str) -> list[str]:
    """A linha de comando da conversão, sem shell.

    ``eps2write`` mantém o vetor. A caixa do EPS é a do que foi desenhado; o
    QGIS pinta o fundo branco da página, e ela sai com o tamanho da figura.
    """
    return [ghostscript, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=eps2write",
            f"-sOutputFile={eps_path}", pdf_path]


def pdf_to_eps(pdf_path: str, eps_path: str, ghostscript: str | None = None) -> dict[str, Any]:
    """Converte o PDF da figura em EPS. Devolve ``{"ok", "error"}``."""
    import subprocess  # nosec B404 - only to run Ghostscript with a fixed argument list, no shell.

    gs = ghostscript or find_ghostscript()
    if not gs:
        return {"ok": False, "error": "Ghostscript não encontrado"}
    extra: dict[str, Any] = {}
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(  # nosec B603 - no shell; Ghostscript converting the figure the plugin just exported.
            eps_command(gs, pdf_path, eps_path), capture_output=True, timeout=CONVERSION_TIMEOUT_S, **extra,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"o Ghostscript não terminou em {CONVERSION_TIMEOUT_S} s"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    if completed.returncode != 0 or not Path(eps_path).is_file() or Path(eps_path).stat().st_size == 0:
        detail = (completed.stderr or completed.stdout or b"").decode("utf-8", "replace").strip()[:300]
        return {"ok": False, "error": f"o Ghostscript falhou (código {completed.returncode}): {detail}"}
    return {"ok": True, "error": "", "ghostscript": gs}


def eps_bounding_box_mm(eps_path: str) -> tuple[float, float] | None:
    """Largura e altura (mm) da caixa declarada no cabeçalho do EPS."""
    try:
        with open(eps_path, "rb") as handle:
            head = handle.read(4096).decode("latin-1", "replace")
    except OSError:
        return None
    for line in head.splitlines():
        if line.startswith("%%HiResBoundingBox:") or line.startswith("%%BoundingBox:"):
            try:
                x0, y0, x1, y1 = (float(v) for v in line.split(":", 1)[1].split()[:4])
            except ValueError:
                continue
            return (x1 - x0) * 25.4 / 72.0, (y1 - y0) * 25.4 / 72.0
    return None
