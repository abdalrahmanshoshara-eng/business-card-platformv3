"""Central Gemini cost estimation.

Prices live in ``settings.GEMINI_PRICING`` (USD per 1,000,000 tokens) so they can
be updated without touching code. All money math uses ``Decimal`` — never float.
The result is an *estimate* based on returned usage metadata and the configured
prices; the authoritative bill comes from Google.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

_MILLION = Decimal('1000000')
_CENTS = Decimal('0.000001')


def _price_for(model_name: str, kind: str) -> Decimal | None:
    pricing = getattr(settings, 'GEMINI_PRICING', {}) or {}
    entry = pricing.get(model_name)
    if not entry:
        return None
    value = entry.get(kind)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def estimate_cost(
    model_name: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> dict:
    """Return estimated input/output/total cost in USD as ``Decimal`` values.

    Returns ``{'input': None, 'output': None, 'total': None, 'reason': ...}`` when
    pricing is unknown so the caller can store NULL and record why. Never raises.
    """
    input_price = _price_for(model_name, 'input')
    output_price = _price_for(model_name, 'output')
    if input_price is None or output_price is None:
        return {
            'input': None,
            'output': None,
            'total': None,
            'reason': f'no_pricing_for_model:{model_name}',
        }

    in_tokens = Decimal(int(input_tokens or 0))
    out_tokens = Decimal(int(output_tokens or 0))
    input_cost = (in_tokens / _MILLION * input_price).quantize(_CENTS, rounding=ROUND_HALF_UP)
    output_cost = (out_tokens / _MILLION * output_price).quantize(_CENTS, rounding=ROUND_HALF_UP)
    total_cost = (input_cost + output_cost).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return {'input': input_cost, 'output': output_cost, 'total': total_cost, 'reason': ''}
