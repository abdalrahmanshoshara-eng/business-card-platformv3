from __future__ import annotations

from ..models import BusinessCard


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def cards_for_user(user):
    """Base queryset scoped to what ``user`` may see.

    Admins (staff/superuser) see every card, including legacy cards that have
    no owner yet. Regular users see only the cards they own.
    """
    qs = BusinessCard.objects.all()
    if is_admin(user):
        return qs
    return qs.filter(owner=user)
