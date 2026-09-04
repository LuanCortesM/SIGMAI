#!/usr/bin/env python3
"""Procura acessos a enums que existem no Qt5 e somem no Qt6.

O PyQt5 expõe os membros de enum tanto no escopo da classe (``QSizePolicy.Fixed``)
quanto no qualificado (``QSizePolicy.Policy.Fixed``). O PyQt6 removeu a forma
curta. O QGIS 4 usa Qt6, e o SIGMAI declara ``qgisMaximumVersion=4.99``, então
cada acesso na forma curta é uma falha esperando o usuário atualizar — foi
exatamente assim que ``QSizePolicy.Fixed`` impediu o painel de abrir no QGIS 4.1.

O mesmo vale para as classes do QGIS: desde a versão 3.30 os enums migraram
para ``Qgis.<Escopo>.<Membro>`` e os nomes antigos ficaram como apelidos de
compatibilidade, que desaparecem na 4.x.

O verificador roda em duas passagens porque os dois bindings não coexistem no
mesmo processo:

* com PyQt6 instalado, confere os acessos a classes Qt;
* com o PyQt do QGIS, confere os acessos a classes Qgs* — um membro cujo valor
  pertence a um enum declarado em ``Qgis`` é apelido e precisa da forma nova.

Também enxerga o padrão ``imports["QgsUnitTypes"].LayoutMillimeters``, que o
plugin usava para carregar símbolos do PyQGIS e que nenhuma varredura de
atributos simples encontraria.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys
from typing import Iterator

#: Chamadas que já resolvem o enum de forma tolerante e não devem ser acusadas.
SAFE_HELPERS = {"qt_enum", "layout_unit_mm", "distance_unit", "geometry_type", "getattr", "_quiet", "_try"}


class Access:
    __slots__ = ("path", "line", "base", "member", "source")

    def __init__(self, path: str, line: int, base: str, member: str, source: str):
        self.path, self.line, self.base, self.member, self.source = path, line, base, member, source

    def __str__(self) -> str:
        return f"{self.path}:{self.line}  {self.base}.{self.member}  ({self.source})"


def collect(paths: list[pathlib.Path]) -> list[Access]:
    found: list[Access] = []
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            print(f"ERRO DE SINTAXE {path}: {exc}", file=sys.stderr)
            continue
        found.extend(_walk(tree, str(path)))
    return found


def _walk(tree: ast.AST, path: str) -> Iterator[Access]:
    # Argumentos passados a qt_enum() e amigos são nomes de membro em string,
    # não acessos: precisam ser ignorados.
    safe_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in SAFE_HELPERS:
                for child in ast.walk(node):
                    safe_nodes.add(id(child))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or id(node) in safe_nodes:
            continue
        if not node.attr[:1].isupper():
            continue

        # Forma direta: QSizePolicy.Fixed
        if isinstance(node.value, ast.Name) and _is_qt_class(node.value.id):
            yield Access(path, node.lineno, node.value.id, node.attr, "direto")
            continue

        # Forma indireta: imports["QgsUnitTypes"].LayoutMillimeters
        if isinstance(node.value, ast.Subscript):
            index = node.value.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, str) and _is_qt_class(index.value):
                yield Access(path, node.lineno, index.value, node.attr, "via dicionário")


def _is_qt_class(name: str) -> bool:
    return name.startswith("Qgs") or name.startswith("Qgis") or (
        name.startswith("Q") and len(name) > 1 and name[1].isupper()
    )


def check_qt(accesses: list[Access]) -> list[tuple[Access, str]]:
    """Confere acessos a classes Qt contra o PyQt6 instalado."""
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets  # type: ignore
    except ImportError:
        print("PyQt6 não instalado; passagem Qt ignorada.", file=sys.stderr)
        return []

    namespace = {}
    for module in (QtCore, QtGui, QtWidgets):
        namespace.update({k: v for k, v in vars(module).items() if isinstance(v, type)})

    problems = []
    for access in accesses:
        target = namespace.get(access.base)
        if target is None:
            continue
        if not hasattr(target, access.member):
            scope = _find_scope(target, access.member)
            hint = f"use {access.base}.{scope}.{access.member}" if scope else "membro não existe no Qt6"
            problems.append((access, hint))
    return problems


def check_qgis(accesses: list[Access]) -> list[tuple[Access, str]]:
    """Confere acessos a classes Qgs* usando a instalação do QGIS disponível.

    São dois defeitos distintos, e ambos quebram no QGIS 4:

    1. *apelido depreciado* — ``QgsUnitTypes.DistanceMeters`` aponta para um
       enum declarado em ``Qgis`` desde a versão 3.30; o nome antigo some;
    2. *enum com escopo próprio* — ``QgsLayoutExporter.Success`` continua sendo
       da própria classe, mas o Qt6 exige o caminho completo
       ``QgsLayoutExporter.ExportResult.Success``. É a mesma armadilha que
       ``QSizePolicy.Fixed``, só que do lado do QGIS, e é a mais numerosa.
    """
    try:
        from qgis import core as qgis_core  # type: ignore
    except ImportError:
        print("PyQGIS não disponível; passagem QGIS ignorada.", file=sys.stderr)
        return []

    problems = []
    for access in accesses:
        target = getattr(qgis_core, access.base, None)
        if target is None or not isinstance(target, type):
            continue
        try:
            value = getattr(target, access.member)
        except AttributeError:
            problems.append((access, "membro não existe nesta versão do QGIS"))
            continue

        owner = type(value).__qualname__
        if "." not in owner:
            continue  # não é membro de enum com escopo; nada a corrigir

        enum_class, enum_name = owner.rsplit(".", 1)
        if enum_class != access.base:
            problems.append((
                access,
                f"apelido depreciado; a forma nova é {enum_class}.{enum_name}.{access.member}",
            ))
        elif not hasattr(getattr(target, enum_name, None) or object(), access.member):
            continue
        else:
            problems.append((
                access,
                f"enum com escopo; no Qt6 é {access.base}.{enum_name}.{access.member}",
            ))
    return problems


def _find_scope(target: type, member: str) -> str | None:
    for name, value in vars(target).items():
        if isinstance(value, type) and hasattr(value, member):
            return name
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["sigmai"], help="pastas ou arquivos a verificar")
    parser.add_argument("--mode", choices=["qt", "qgis", "both"], default="both")
    args = parser.parse_args()

    files: list[pathlib.Path] = []
    for raw in args.paths or ["sigmai"]:
        path = pathlib.Path(raw)
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    files = [f for f in files if "__pycache__" not in f.parts]

    accesses = collect(files)
    print(f"{len(accesses)} acesso(s) a enum de classe Qt/QGIS em {len(files)} arquivo(s).")

    problems: list[tuple[Access, str]] = []
    if args.mode in ("qt", "both"):
        problems += check_qt(accesses)
    if args.mode in ("qgis", "both"):
        problems += check_qgis(accesses)

    if not problems:
        print("Nenhum acesso incompatível com Qt6/QGIS 4.")
        return 0

    print(f"\n{len(problems)} problema(s):")
    for access, hint in problems:
        print(f"  {access}\n      -> {hint}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
