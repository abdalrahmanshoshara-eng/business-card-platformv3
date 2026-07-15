from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings
from rest_framework import serializers

_FORMULA_PREFIXES = ('=', '+', '-', '@')


def excel_safe(value):
    """Neutralise spreadsheet formula injection.

    A leading =, +, -, @ (or tab/CR) makes Excel/LibreOffice treat the cell as
    a formula; prefix such strings with an apostrophe so they stay literal.
    """
    if not isinstance(value, str):
        return value
    if value[:1] in _FORMULA_PREFIXES or value[:1] in ('\t', '\r', '\n'):
        return "'" + value
    return value


def validate_image_upload(uploaded_file):
    """Validate a card image by declared type, size, and real content.

    Raises rest_framework.serializers.ValidationError on failure.
    """
    if uploaded_file is None:
        return uploaded_file

    max_mb = getattr(settings, 'MAX_UPLOAD_IMAGE_MB', 10)
    size = getattr(uploaded_file, 'size', None)
    if size is not None and size > max_mb * 1024 * 1024:
        raise serializers.ValidationError(f'حجم الصورة يتجاوز الحد المسموح ({max_mb} ميغابايت).')

    allowed = getattr(settings, 'ALLOWED_IMAGE_CONTENT_TYPES', {'image/jpeg', 'image/png'})
    content_type = getattr(uploaded_file, 'content_type', '') or ''
    if content_type and content_type not in allowed:
        raise serializers.ValidationError('نوع الصورة غير مدعوم. المسموح: JPEG, PNG, WEBP.')

    # Verify the real bytes are a decodable image (not just a spoofed header).
    try:
        from PIL import Image

        pos = uploaded_file.tell() if hasattr(uploaded_file, 'tell') else None
        uploaded_file.seek(0)
        Image.open(uploaded_file).verify()
    except serializers.ValidationError:
        raise
    except Exception:
        raise serializers.ValidationError('تعذّر التحقق من صورة صالحة.')
    finally:
        try:
            uploaded_file.seek(pos if pos is not None else 0)
        except Exception:
            pass
    return uploaded_file


def is_public_http_url(url: str) -> bool:
    """Return True only for http(s) URLs whose host resolves to a public IP.

    Blocks loopback/private/link-local/reserved ranges to prevent SSRF when we
    fetch external company websites from the server.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except Exception:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False
    return True
