"""Validação de parâmetros que chegam de fora do processo Python.

``compose_map`` recebe um dicionário JSON escrito por um agente de IA, não por
um programador Python. Isso muda o que "aceitar com tolerância" significa: um
``float("7,5")`` que estoura ``ValueError`` cru, um ``bool("false")`` que vale
``True``, ou um ``for item in 42`` que estoura ``TypeError`` são acidentes de
implementação, não recusas — o agente do outro lado não tem como saber que a
causa foi um decimal com vírgula, e o pior caso (``confirm_overwrite:
"false"`` sobrescrevendo um arquivo do usuário) não é um erro qualquer, é uma
perda de dado silenciosa.

As quatro funções daqui existem para que cada ponto de ``compose.py`` que lê
um parâmetro do dicionário faça isso de um jeito que:

* aceita as formas razoáveis que um agente de IA realmente envia (número como
  string, ``"true"``/``"sim"``/``1`` para booleano, um id solto em vez de uma
  lista de um item);
* recusa qualquer outra coisa com uma ``ParameterError`` — que ``compose.py``
  converte em ``CompositionError`` — cuja mensagem diz o que era esperado, em
  vez de deixar o Python levantar ``TypeError``/``KeyError``/``AttributeError``
  crus, que não apontam a causa;
* nunca adivinha em silêncio. ``bool("false")`` é ``True`` em Python porque
  uma string não vazia é verdadeira; converter automaticamente por esse
  caminho é exatamente o acidente que apagou arquivo de usuário com
  ``confirm_overwrite: "false"``. Por isso ``as_flag`` só aceita um conjunto
  fechado de grafias inequívocas, e não a conversão booleana do Python.

Python puro, sem PyQGIS, para poder rodar em CI — igual a ``scaling.py``.
"""

from __future__ import annotations

from typing import Any


class ParameterError(ValueError):
    """Um parâmetro não pôde ser interpretado com segurança.

    ``compose.py`` captura toda ``ParameterError`` e a relança como
    ``CompositionError``: do ponto de vista de quem chamou ``compose_map`` as
    duas são a mesma coisa — uma recusa com uma frase acionável. A distinção
    existe só para que este módulo, que não conhece ``CompositionError``,
    continue podendo ser testado e usado sem depender de ``compose.py``.
    """


# ---------------------------------------------------------------------------
# Números
# ---------------------------------------------------------------------------

def _range_text(minimum: float | None, maximum: float | None) -> str:
    if minimum is not None and maximum is not None:
        return f"entre {minimum:g} e {maximum:g}"
    if minimum is not None:
        return f">= {minimum:g}"
    if maximum is not None:
        return f"<= {maximum:g}"
    return ""


def as_number(
    params: dict[str, Any],
    key: str,
    default: float | int | None = None,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
    label: str | None = None,
) -> float | int | None:
    """Extrai um número de ``params[key]``, sem herdar as tolerâncias do Python.

    Aceita ``int``/``float`` de verdade e uma string numérica limpa com
    **ponto** decimal — o suficiente para um agente de IA que serializa um
    número como texto. Recusa, cada uma com sua causa nomeada:

    * vírgula decimal inequívoca (``"7,5"``, ``"12,25"``): aceita e convertida,
      porque é assim que se escreve número em francês, alemão, italiano,
      espanhol e português, e há só uma leitura possível. Já ``"1,500"`` é
      recusado: vale mil e quinhentos em inglês e um e meio em francês, e
      escolher entre as duas seria adivinhar.
    * ``None``, lista, dict, string não numérica: nenhuma delas é um número, e
      deixar o Python tentar convertê-las produz um ``TypeError`` que não diz
      qual parâmetro falhou.
    * ``bool``: em Python ``bool`` é subclasse de ``int`` — ``True`` vale
      ``1``. Aceitar isso silenciosamente deixaria ``dpi: true`` virar
      ``dpi=1`` sem que ninguém tivesse pedido um DPI de verdade.

    Fora de ``minimum``/``maximum`` a recusa nomeia a faixa aceita; com
    ``integer=True`` um valor fracionário (``1.5``) também é recusado, porque
    truncar em silêncio (o que ``int(1.5)`` faria) entrega um resultado
    diferente do pedido. Chave ausente devolve ``default`` sem validação — é
    o valor que o próprio ``compose_map`` escolhe quando ninguém pediu nada.
    """
    if key not in params:
        return default
    value = params[key]
    name = label or key

    if isinstance(value, bool):
        raise ParameterError(
            f"{name} precisa ser um número; recebido um valor verdadeiro/falso ({value!r})."
        )

    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ParameterError(f"{name} precisa ser um número; recebido uma string vazia.")
        # Vírgula decimal: aceitar sempre esconderia ambiguidade real, e recusar
        # sempre puniria o usuário francês, alemão, italiano ou espanhol por
        # escrever o número como se escreve na língua dele. A separação é pelo
        # que é decidível: "7,5" e "12,25" só têm uma leitura possível; "1,500"
        # tem duas — mil e quinhentos para quem escreve em inglês, um e meio
        # para quem escreve em francês — e adivinhar entre elas é justamente o
        # que esta ferramenta não faz.
        if "," in text and "." not in text:
            casas = text.rsplit(",", 1)[-1]
            inequivoco = text.count(",") == 1 and casas.isdigit() and len(casas) != 3
            if inequivoco:
                text = text.replace(",", ".")
            else:
                raise ParameterError(
                    f"{name}: {value!r} pode ser lido de duas formas (vírgula de milhar ou "
                    f"vírgula decimal). Escreva com ponto decimal e sem separador de milhar — "
                    f"{text.replace(',', '')!r} ou {text.replace(',', '.')!r}."
                )
        try:
            number = float(text)
        except ValueError as exc:
            raise ParameterError(f"{name} precisa ser um número; recebido {value!r}.") from exc
    else:
        raise ParameterError(
            f"{name} precisa ser um número (int, float ou texto numérico com ponto decimal); "
            f"recebido {type(value).__name__} ({value!r})."
        )

    if integer and not number.is_integer():
        raise ParameterError(f"{name} precisa ser um número inteiro; recebido {value!r}.")

    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise ParameterError(
            f"{name} precisa estar {_range_text(minimum, maximum)}; recebido {value!r}."
        )

    return int(number) if integer else number


# ---------------------------------------------------------------------------
# Booleanos
# ---------------------------------------------------------------------------

#: Grafias inequívocas aceitas para um sinalizador, sem diferenciar caixa.
#: Deliberadamente NÃO é a conversão ``bool()`` do Python: ``bool("false")``
#: vale ``True`` porque toda string não vazia é verdadeira, e foi exatamente
#: esse atalho que fez ``confirm_overwrite: "false"`` sobrescrever um arquivo
#: do usuário em silêncio — o defeito mais grave encontrado nas rodadas de
#: teste. Por isso a lista é fechada: só entra o que um humano reconheceria
#: como "sim" ou "não" sem ambiguidade.
_FLAG_WORDS: dict[str, bool] = {
    "true": True, "false": False,
    "yes": True, "no": False,
    "sim": True, "não": False, "nao": False,
    "1": True, "0": False,
}


def as_flag(params: dict[str, Any], key: str, default: bool) -> tuple[bool, str]:
    """Extrai um booleano de ``params[key]``, sem usar ``bool()`` do Python.

    Aceita ``bool`` de verdade, os inteiros ``1``/``0`` e as strings (sem
    diferenciar maiúsculas) ``"true"``/``"false"``, ``"yes"``/``"no"``,
    ``"sim"``/``"não"``/``"nao"``, ``"1"``/``"0"``. Qualquer outro valor —
    inclusive ``None`` e uma string fora dessa lista — é recusado nomeando o
    que é aceito.

    Devolve ``(valor, nota)``: ``nota`` é ``""`` quando o parâmetro já era um
    ``bool`` e não precisou de conversão, ou um texto explicando a conversão
    quando o valor veio como número ou texto — para que ``compose.py``
    registre isso na lista de notas da resposta e o pedido não vire uma
    interpretação silenciosa. Chave ausente devolve ``(default, "")``.
    """
    if key not in params:
        return default, ""
    value = params[key]

    if isinstance(value, bool):
        return value, ""

    # bool já foi tratado acima (é subclasse de int); um int puro só pode
    # chegar aqui como 1 ou 0 — qualquer outro inteiro é rejeitado adiante.
    if isinstance(value, int) and value in (0, 1):
        resolved = bool(value)
        rotulo = "verdadeiro" if resolved else "falso"
        return resolved, f"{key}={value!r} (número) foi interpretado como {rotulo}."

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _FLAG_WORDS:
            resolved = _FLAG_WORDS[normalized]
            rotulo = "verdadeiro" if resolved else "falso"
            return resolved, (
                f"{key}={value!r} (texto) foi interpretado como {rotulo}. "
                "Isto NÃO é a conversão bool() do Python — nela, bool('false') vale True — "
                "e sim uma lista fechada de grafias inequívocas."
            )

    raise ParameterError(
        f"{key} precisa ser verdadeiro ou falso; recebido {value!r}. "
        "Aceito: true/false, yes/no, sim/não, 1/0 (como bool ou como texto)."
    )


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def as_text(params: dict[str, Any], key: str, default: str = "", *, label: str | None = None) -> str:
    """Extrai um texto de ``params[key]``, sem deixar ``None`` virar ``"None"``.

    ``str(None)`` é a string de três letras ``"None"`` — foi assim que
    ``title: null`` passou a imprimir literalmente "None" no mapa, e
    ``data_source``/``map_author`` nulos entraram na linha de crédito da
    mesma forma. Aqui ``None`` e a chave ausente têm o mesmo resultado que
    quem pediu esperava: ``default`` (tipicamente string vazia, "omita este
    campo"). Números são convertidos (``2024`` vira ``"2024"``); lista e dict
    são recusados, porque não há conversão de texto razoável para eles que não
    seja inventar um formato.
    """
    if key not in params or params[key] is None:
        return default
    value = params[key]
    name = label or key
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    raise ParameterError(
        f"{name} precisa ser texto (ou um número, convertido automaticamente); "
        f"recebido {type(value).__name__}: {value!r}. Listas e dicionários não são aceitos aqui."
    )


# ---------------------------------------------------------------------------
# Listas de identificadores de camada
# ---------------------------------------------------------------------------

def as_id_list(
    params: dict[str, Any],
    key: str,
    *,
    allow_single: bool = True,
    label: str | None = None,
) -> list[str] | None:
    """Extrai uma lista de ids/nomes de camada de ``params[key]``.

    Aceita uma lista de strings e, com ``allow_single=True`` (o padrão),
    também um único texto solto — devolvido como lista de um item, porque
    ``layer_ids: "abc123"`` é uma forma comum de um agente de IA esquecer os
    colchetes ao pedir uma única camada. Recusa ``int``, ``bool``, ``None``,
    ``dict`` e uma lista com algum item que não seja texto, nomeando o que é
    esperado — era aqui que ``layer_ids: 42`` ou ``layer_ids: true`` estourava
    ``TypeError: 'int' object is not iterable`` direto na iteração, longe de
    qualquer mensagem que apontasse a causa.

    Chave ausente devolve ``None`` (não ``[]``): o chamador decide o que
    significa "nenhuma camada informada" — em ``compose_map`` isso costuma
    envolver checar mais de uma chave possível (``layer_ids``/``layers``).
    """
    if key not in params:
        return None
    value = params[key]
    name = label or key

    if value is None:
        raise ParameterError(f"{name} não pode ser nulo; informe uma lista de ids/nomes de camada.")
    if isinstance(value, bool):
        raise ParameterError(
            f"{name} precisa ser uma lista de ids de camada; recebido um valor verdadeiro/falso ({value!r})."
        )
    if isinstance(value, str):
        if not allow_single:
            raise ParameterError(
                f"{name} precisa ser uma lista de ids de camada; recebido um único texto ({value!r})."
            )
        if not value.strip():
            raise ParameterError(f"{name} não pode ser uma string vazia.")
        return [value]
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, str):
                raise ParameterError(
                    f"{name}: todo item precisa ser um texto (id ou nome de camada); "
                    f"encontrado {type(item).__name__} ({item!r})."
                )
        return list(value)

    raise ParameterError(
        f"{name} precisa ser uma lista de textos"
        + (" (ou um texto único)" if allow_single else "")
        + f"; recebido {type(value).__name__} ({value!r})."
    )
