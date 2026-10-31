"""Preço de tabela dos modelos da Anthropic, para o custo estimado de cada conversa.

Fonte: tabela de preços da Anthropic de 06/10/2026, em dólares por milhão de
tokens. A escrita no cache de 5 minutos custa 1,25 vez a entrada. O preço muda;
por isso o painel mostra a data junto do valor. Para os provedores do formato
da OpenAI não há tabela aqui, e o painel mostra só os tokens.
"""

from __future__ import annotations

from .providers import Usage

PRICES_DATE = "2026-10-06"
CACHE_WRITE_FACTOR = 1.25
#: modelo: (entrada, saída, leitura de cache), US$ por milhão de tokens
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    # Sem leitura de cache na tabela de origem: 1/10 da entrada, a razão dos modelos anteriores.
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}


def cost_usd(model: str, usage: Usage) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    entrada, saida, leitura = price
    return (usage.input * entrada + usage.cache_write * entrada * CACHE_WRITE_FACTOR
            + usage.cache_read * leitura + usage.output * saida) / 1_000_000
