from __future__ import annotations

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.db.models import Count
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .permissions import IsAdmin
from .serializers import (
    AdminUserCreateSerializer,
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services import build_reset_link, send_reset_email

User = get_user_model()


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfView(APIView):
    """GET to prime the CSRF cookie before the first unsafe request."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'detail': 'ok'})


@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_register'

    def post(self, request):
        if not getattr(settings, 'PUBLIC_REGISTRATION_ENABLED', False):
            return Response(
                {'detail': 'التسجيل الذاتي غير مفعّل. يرجى التواصل مع المشرف.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
        )
        if user is None:
            # Generic message: do not reveal whether the identifier exists.
            return Response(
                {'detail': 'بيانات الدخول غير صحيحة.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.is_active:
            return Response(
                {'detail': 'هذا الحساب معطّل. يرجى التواصل مع المشرف.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        login(request, user)  # rotates the session key
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)  # flushes the session
        return Response({'detail': 'تم تسجيل الخروج.'})


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        # Keep the current session valid after the password change.
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return Response({'detail': 'تم تغيير كلمة المرور بنجاح.'})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_forgot'

    def post(self, request):
        identifier = (request.data.get('email') or request.data.get('username') or '').strip()
        user = (
            User.objects.filter(email__iexact=identifier).first()
            or User.objects.filter(username__iexact=identifier).first()
        )
        if user and user.is_active and user.email:
            send_reset_email(user, build_reset_link(user))
        # Always generic, to avoid account enumeration.
        return Response({'detail': 'إذا كان الحساب موجوداً فسيتم إرسال رابط إعادة التعيين.'})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uidb64 = request.data.get('uid', '')
        token = request.data.get('token', '')
        new_password = request.data.get('new_password', '')
        confirm = request.data.get('new_password_confirm', new_password)
        if new_password != confirm:
            return Response({'detail': 'كلمتا المرور غير متطابقتين.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, token):
            return Response({'detail': 'رابط إعادة التعيين غير صالح أو منتهي.'}, status=status.HTTP_400_BAD_REQUEST)
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'detail': 'تم تعيين كلمة المرور. يمكنك تسجيل الدخول الآن.'})


class AdminUserViewSet(viewsets.ModelViewSet):
    """Admin-only user management with per-user card counts."""

    permission_classes = [IsAdmin]
    queryset = User.objects.all().order_by('id')

    def get_serializer_class(self):
        if self.action == 'create':
            return AdminUserCreateSerializer
        if self.action in {'update', 'partial_update'}:
            return AdminUserUpdateSerializer
        return UserSerializer

    def get_queryset(self):
        return User.objects.all().annotate(card_count=Count('business_cards')).order_by('id')

    def _payload(self, user):
        data = UserSerializer(user).data
        data['card_count'] = getattr(user, 'card_count', user.business_cards.count())
        return data

    def list(self, request, *args, **kwargs):
        # Hide superusers (the main admin); the list manages regular users only.
        users = self.get_queryset().filter(is_superuser=False)
        return Response([self._payload(u) for u in users])

    def retrieve(self, request, *args, **kwargs):
        return Response(self._payload(self.get_object()))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(self._payload(user), status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        instance.refresh_from_db()
        return Response(self._payload(instance))

    def destroy(self, request, *args, **kwargs):
        """Permanently delete a regular user together with all their cards and
        the cards' image files. The main admin (superuser) and the currently
        signed-in admin are protected."""
        from cards.models import BusinessCard

        user = self.get_object()
        if user.is_superuser:
            return Response(
                {'detail': 'لا يمكن حذف حساب المشرف الرئيسي.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user == request.user:
            return Response(
                {'detail': 'لا يمكنك حذف حسابك الخاص.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cards = BusinessCard.objects.filter(owner=user)
        card_count = cards.count()
        username = user.username
        with transaction.atomic():
            for card in cards:
                for field in (card.front_image, card.back_image):
                    if field:
                        field.delete(save=False)  # remove the file from storage
            cards.delete()
            user.delete()
        return Response(
            {'detail': f'تم حذف المستخدم "{username}" و{card_count} كرت نهائياً.'},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='reset-link')
    def reset_link(self, request, pk=None):
        user = self.get_object()
        link = build_reset_link(user)
        if user.email:
            send_reset_email(user, link)
        return Response({'detail': 'تم إنشاء رابط إعادة التعيين.', 'reset_link': link})

    @action(detail=True, methods=['post'], url_path='set-password')
    def set_password(self, request, pk=None):
        """Admin sets a user's password directly (never reads the old one)."""
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        user = self.get_object()
        new_password = request.data.get('new_password', '')
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'detail': 'تم تعيين كلمة المرور بنجاح.'})
