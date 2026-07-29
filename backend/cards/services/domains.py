"""Canonical domain normalization for website-enrichment caching.

Scoping decision (documented in ARCHITECTURE.md): we key cached enrichment on the
**registered domain** (eTLD+1) using the public-suffix list via ``tldextract``.
So ``https://www.Example.com/about?x=1``, ``http://example.com`` and
``https://careers.example.com/jobs`` all collapse to ``example.com`` and share a
single enrichment result. This is deliberate: one company site should be analysed
once, not once per subdomain or per employee card.
"""

from __future__ import annotations

from urllib.parse import urlparse

try:
    import tldextract

    # Use the bundled snapshot only (no network calls at runtime).
    _EXTRACT = tldextract.TLDExtract(suffix_list_urls=())
except Exception:  # pragma: no cover - tldextract should be installed
    tldextract = None
    _EXTRACT = None


def canonical_domain(url: str | None) -> str:
    """Return the lowercase registered domain (eTLD+1) for ``url``, or ''.

    Strips scheme, ``www``, path, query, fragment and port; keeps other
    meaningful subdomains folded into the registered domain.
    """
    raw = (url or '').strip()
    if not raw:
        return ''
    if '://' not in raw:
        raw = 'http://' + raw
    try:
        host = urlparse(raw).hostname or ''
    except Exception:
        return ''
    host = host.strip().lower().rstrip('.')
    if not host:
        return ''

    if _EXTRACT is not None:
        ext = _EXTRACT(host)
        if ext.domain and ext.suffix:
            return f'{ext.domain}.{ext.suffix}'
        # No known public suffix (e.g. intranet host): fall back to the host.
        return ext.domain or host

    # Fallback if tldextract is unavailable: drop a leading www.
    return host[4:] if host.startswith('www.') else host
