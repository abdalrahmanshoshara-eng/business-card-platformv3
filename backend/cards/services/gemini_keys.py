from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class KeyState:
    index: int
    disabled: bool = False
    cooldown_until: float = 0.0
    last_reason: str = ''


class GeminiKeyManager:
    """Small in-memory Gemini API key manager.

    The manager never logs key values. State is per Python process, which is
    enough for the requested runtime disable/cooldown behavior under Gunicorn.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[int, KeyState] = {}
        self._cursor = 0
        self._keys_signature: tuple[str, ...] = ()

    def _keys(self) -> list[str]:
        keys = [key.strip() for key in (getattr(settings, 'GEMINI_API_KEYS', []) or []) if str(key).strip()]
        signature = tuple(keys)
        with self._lock:
            if signature != self._keys_signature:
                self._keys_signature = signature
                self._states = {index: KeyState(index=index) for index in range(len(keys))}
                self._cursor = 0
        return keys

    def has_keys(self) -> bool:
        return bool(self._keys())

    def available_count(self) -> int:
        keys = self._keys()
        now = time.time()
        with self._lock:
            return sum(
                1
                for index in range(len(keys))
                if not self._states[index].disabled and self._states[index].cooldown_until <= now
            )

    def get_candidate(self, tried_indexes: set[int]) -> tuple[int, str] | None:
        keys = self._keys()
        if not keys:
            return None

        now = time.time()
        with self._lock:
            total = len(keys)
            for offset in range(total):
                index = (self._cursor + offset) % total
                state = self._states[index]
                if index in tried_indexes:
                    continue
                if state.disabled:
                    continue
                if state.cooldown_until > now:
                    continue
                self._cursor = (index + 1) % total
                logger.info('gemini_key_selected selected_key_index=%s key_attempt_count=%s', index, len(tried_indexes) + 1)
                return index, keys[index]
        return None

    def mark_invalid(self, index: int, reason: str = 'invalid_api_key') -> None:
        with self._lock:
            state = self._states.get(index)
            if state:
                state.disabled = True
                state.last_reason = reason
        logger.warning('gemini_key_failed selected_key_index=%s key_failed_reason=%s key_disabled=true', index, reason)

    def mark_cooldown(self, index: int, reason: str = 'rate_limit') -> None:
        cooldown_seconds = int(getattr(settings, 'GEMINI_KEY_COOLDOWN_SECONDS', 60))
        with self._lock:
            state = self._states.get(index)
            if state:
                state.cooldown_until = time.time() + max(1, cooldown_seconds)
                state.last_reason = reason
        logger.warning(
            'gemini_key_failed selected_key_index=%s key_failed_reason=%s key_marked_cooldown=true cooldown_seconds=%s',
            index,
            reason,
            cooldown_seconds,
        )

    def exhaustion_reason(self, tried_indexes: set[int] | None = None) -> str:
        keys = self._keys()
        if not keys:
            return 'missing_gemini_api_key'
        tried_indexes = tried_indexes or set()
        now = time.time()
        with self._lock:
            if all(self._states[index].disabled for index in range(len(keys))):
                return 'all_gemini_keys_invalid'
            if all(index in tried_indexes or self._states[index].cooldown_until > now for index in range(len(keys))):
                return 'all_gemini_keys_rate_limited'
        return 'all_gemini_keys_exhausted'


manager = GeminiKeyManager()
