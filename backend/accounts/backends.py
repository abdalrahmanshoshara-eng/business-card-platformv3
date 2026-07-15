from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    """Authenticate with either username or (case-insensitive) email.

    The generic ``username`` argument may hold a username or an email. We look
    the user up by either, then defer password/active checks to Django.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get('email') or '').strip()
        if not identifier or password is None:
            return None
        try:
            user = UserModel.objects.get(
                Q(username__iexact=identifier) | Q(email__iexact=identifier)
            )
        except UserModel.DoesNotExist:
            # Run the default hasher once to reduce timing side-channels.
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            user = (
                UserModel.objects.filter(username__iexact=identifier).first()
                or UserModel.objects.filter(email__iexact=identifier).first()
            )
            if user is None:
                return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
