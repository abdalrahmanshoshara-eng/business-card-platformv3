from rest_framework.permissions import BasePermission


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


class IsAdmin(BasePermission):
    """Allow only staff/superuser accounts."""

    message = 'هذه العملية متاحة للمشرفين فقط.'

    def has_permission(self, request, view):
        return is_admin(request.user)
