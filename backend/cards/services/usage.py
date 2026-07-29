"""Persist Gemini usage + estimated cost. Logging must never break the caller,
so every failure here is swallowed and logged."""

from __future__ import annotations

import logging

from ..models import GeminiUsageLog
from .pricing import estimate_cost

logger = logging.getLogger(__name__)


def log_gemini_usage(
    *,
    operation_type: str,
    model_name: str,
    usage=None,
    owner=None,
    card=None,
    extraction_request=None,
    request_status: str = 'completed',
    request_count: int = 1,
    retry_number: int = 0,
    latency_ms: int | None = None,
    error_code: str = '',
    error_type: str = '',
) -> GeminiUsageLog | None:
    """Write one GeminiUsageLog row. ``usage`` is a GeminiUsage dataclass (or
    None when metadata is unavailable). Returns the row, or None on failure.
    """
    try:
        input_tokens = getattr(usage, 'input_tokens', 0) or 0
        output_tokens = getattr(usage, 'output_tokens', 0) or 0
        total_tokens = getattr(usage, 'total_tokens', 0) or 0
        available = bool(getattr(usage, 'available', False))

        if available:
            cost = estimate_cost(model_name, input_tokens, output_tokens)
            cost_note = cost['reason']
        else:
            # No metadata → store NULL costs with the reason (per requirements).
            cost = {'input': None, 'output': None, 'total': None}
            cost_note = 'no_usage_metadata'

        return GeminiUsageLog.objects.create(
            owner=owner,
            card=card,
            extraction_request=extraction_request,
            model_name=model_name or '',
            operation_type=operation_type,
            request_status=request_status,
            input_token_count=input_tokens,
            output_token_count=output_tokens,
            thoughts_token_count=getattr(usage, 'thoughts_tokens', None),
            cached_token_count=getattr(usage, 'cached_tokens', None),
            total_token_count=total_tokens,
            request_count=request_count,
            retry_number=retry_number,
            estimated_input_cost_usd=cost['input'],
            estimated_output_cost_usd=cost['output'],
            estimated_total_cost_usd=cost['total'],
            currency='USD',
            cost_note=cost_note[:120],
            latency_ms=latency_ms,
            error_code=(error_code or '')[:64],
            error_type=(error_type or '')[:64],
        )
    except Exception:
        logger.exception('gemini_usage_log_failed operation=%s', operation_type)
        return None
