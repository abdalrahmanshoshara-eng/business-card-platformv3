from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminUserViewSet,
    ChangePasswordView,
    CsrfView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    MeView,
    ProfileView,
    RegisterView,
    ResetPasswordView,
)

# Router keeps the trailing-slash URLs (used by tests and the browsable API).
router = DefaultRouter()
router.register(r'admin/users', AdminUserViewSet, basename='admin-users')

# Explicit no-slash aliases: the Next.js proxy strips trailing slashes
# (trailingSlash: false), so requests reach Django without a slash.
admin_users_list = AdminUserViewSet.as_view({'get': 'list', 'post': 'create'})
admin_users_detail = AdminUserViewSet.as_view(
    {'get': 'retrieve', 'patch': 'partial_update', 'put': 'update', 'delete': 'destroy'}
)
admin_users_reset = AdminUserViewSet.as_view({'post': 'reset_link'})
admin_users_setpw = AdminUserViewSet.as_view({'post': 'set_password'})

auth_patterns = [
    path('auth/csrf', CsrfView.as_view()),
    path('auth/csrf/', CsrfView.as_view()),
    path('auth/register', RegisterView.as_view()),
    path('auth/register/', RegisterView.as_view()),
    path('auth/login', LoginView.as_view()),
    path('auth/login/', LoginView.as_view()),
    path('auth/logout', LogoutView.as_view()),
    path('auth/logout/', LogoutView.as_view()),
    path('auth/me', MeView.as_view()),
    path('auth/me/', MeView.as_view()),
    path('auth/profile', ProfileView.as_view()),
    path('auth/profile/', ProfileView.as_view()),
    path('auth/change-password', ChangePasswordView.as_view()),
    path('auth/change-password/', ChangePasswordView.as_view()),
    path('auth/forgot-password', ForgotPasswordView.as_view()),
    path('auth/forgot-password/', ForgotPasswordView.as_view()),
    path('auth/reset-password', ResetPasswordView.as_view()),
    path('auth/reset-password/', ResetPasswordView.as_view()),
]

admin_users_patterns = [
    path('admin/users', admin_users_list),
    path('admin/users/<int:pk>', admin_users_detail),
    path('admin/users/<int:pk>/reset-link', admin_users_reset),
    path('admin/users/<int:pk>/set-password', admin_users_setpw),
]

urlpatterns = auth_patterns + admin_users_patterns + router.urls
