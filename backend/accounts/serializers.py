from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Profile, WelcomeLetter
from .permissions import is_admin
from .services_email import (
    DEFAULT_WELCOME_MESSAGE,
    DEFAULT_WELCOME_MESSAGE_EN,
    DEFAULT_WELCOME_SUBJECT,
    DEFAULT_WELCOME_SUBJECT_EN,
)

User = get_user_model()

# Saved on the profile. The letter itself has its own model and endpoint (see
# WelcomeLetter) so it can be edited and reset independently. The actual From
# account is a single platform email in settings, not per user.
WELCOME_CONFIG_FIELDS = ('sender_email',)

# Keys of the platform letter, as exposed by the API.
LETTER_API_FIELDS = ('welcome_subject', 'welcome_message', 'welcome_subject_en', 'welcome_message_en')


def effective_letter(user=None) -> dict:
    """The letter as this user will actually send it: their own wording where
    they set it, otherwise the ministry default for that language."""
    letter = WelcomeLetter.load(user)
    return {
        'welcome_subject': letter.subject_ar or DEFAULT_WELCOME_SUBJECT,
        'welcome_message': letter.body_ar or DEFAULT_WELCOME_MESSAGE,
        'welcome_subject_en': letter.subject_en or DEFAULT_WELCOME_SUBJECT_EN,
        'welcome_message_en': letter.body_en or DEFAULT_WELCOME_MESSAGE_EN,
        'is_customized': letter.is_customized,
    }


def get_welcome_config(user) -> dict:
    """Everything the welcome screens need: the user's sender email and their
    own letter as it will be sent."""
    profile = getattr(user, 'profile', None)
    return {
        'sender_email': profile.sender_email if profile else '',
        'configured': profile.has_welcome_config() if profile else False,
        # Every user owns their letter, so anyone signed in may edit it. Kept in
        # the payload because the UI branches on it.
        'can_edit_letter': True,
        'can_test_send': is_admin(user),
        **effective_letter(user),
    }


def set_welcome_config(user, data: dict) -> None:
    """Persist the welcome-email config. Only provided keys change."""
    defaults = {field: data[field] for field in WELCOME_CONFIG_FIELDS if field in data}
    if defaults:
        Profile.objects.update_or_create(user=user, defaults=defaults)


class WelcomeLetterSerializer(serializers.Serializer):
    """One user's letter. A blank field means "use the ministry default for that
    language"."""

    welcome_subject = serializers.CharField(required=False, allow_blank=True, max_length=255)
    welcome_message = serializers.CharField(required=False, allow_blank=True)
    welcome_subject_en = serializers.CharField(required=False, allow_blank=True, max_length=255)
    welcome_message_en = serializers.CharField(required=False, allow_blank=True)

    API_TO_MODEL = {
        'welcome_subject': 'subject_ar',
        'welcome_message': 'body_ar',
        'welcome_subject_en': 'subject_en',
        'welcome_message_en': 'body_en',
    }

    def save(self, *, user) -> WelcomeLetter:
        letter = WelcomeLetter.load(user)
        letter.user = user
        for api_field, model_field in self.API_TO_MODEL.items():
            if api_field in self.validated_data:
                setattr(letter, model_field, self.validated_data[api_field].strip())
        if letter.is_customized:
            letter.save()
        else:
            # Everything blank is the same as never having customised, so keep
            # the letter tracking the shipped default instead of pinning a row
            # of empty strings.
            WelcomeLetter.reset_for(user)
        return letter


def normalize_email(value: str) -> str:
    return (value or '').strip().lower()


def _email_taken(email: str, *, exclude_pk=None) -> bool:
    qs = User.objects.filter(email__iexact=email)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def _username_taken(username: str, *, exclude_pk=None) -> bool:
    qs = User.objects.filter(username__iexact=username)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def get_phone(user) -> str:
    profile = getattr(user, 'profile', None)
    return profile.phone if profile else ''


def set_phone(user, phone) -> None:
    if phone is None:
        return
    Profile.objects.update_or_create(user=user, defaults={'phone': (phone or '').strip()})


class UserSerializer(serializers.ModelSerializer):
    """Public representation of a user. Never exposes password or lets the
    client escalate privileges (is_staff/is_superuser are read-only)."""

    phone = serializers.SerializerMethodField()
    welcome_email = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'phone',
            'is_active', 'is_staff', 'is_superuser', 'date_joined', 'last_login',
            'welcome_email',
        ]
        read_only_fields = ['id', 'is_staff', 'is_superuser', 'date_joined', 'last_login']

    def get_phone(self, obj):
        return get_phone(obj)

    def get_welcome_email(self, obj):
        return get_welcome_config(obj)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value):
        value = value.strip()
        if _username_taken(value):
            raise serializers.ValidationError('اسم المستخدم مستخدم بالفعل.')
        return value

    def validate_email(self, value):
        value = normalize_email(value)
        if _email_taken(value):
            raise serializers.ValidationError('البريد الإلكتروني مستخدم بالفعل.')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'كلمتا المرور غير متطابقتين.'})
        user = User(
            username=attrs['username'], email=attrs['email'],
            first_name=attrs.get('first_name', ''), last_name=attrs.get('last_name', ''),
        )
        try:
            validate_password(attrs['password'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})
        return attrs

    def create(self, validated_data):
        # Self-registered users never get admin privileges.
        return User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    remember = serializers.BooleanField(required=False, default=False)


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """A user editing their own profile: name, email, phone, welcome-email config."""

    phone = serializers.CharField(required=False, allow_blank=True, max_length=30)
    # The only welcome setting a user owns; the letter is edited separately and
    # by admins only.
    sender_email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'sender_email',
        ]

    def validate(self, attrs):
        # Refuse the letter fields outright instead of ignoring them, so a stale
        # client never believes this endpoint saved its wording.
        sent = [field for field in LETTER_API_FIELDS if field in self.initial_data]
        if sent:
            raise serializers.ValidationError({
                sent[0]: 'نصّ رسالة الترحيب يُحفظ من صفحة «رسالة الترحيب» لا من الملف الشخصي.',
            })
        return attrs

    def validate_email(self, value):
        value = normalize_email(value)
        if _email_taken(value, exclude_pk=self.instance.pk):
            raise serializers.ValidationError('البريد الإلكتروني مستخدم بالفعل.')
        return value

    def validate_sender_email(self, value):
        return normalize_email(value)

    def update(self, instance, validated_data):
        phone = validated_data.pop('phone', None)
        welcome = {field: validated_data.pop(field) for field in WELCOME_CONFIG_FIELDS if field in validated_data}
        instance = super().update(instance, validated_data)
        set_phone(instance, phone)
        if welcome:
            set_welcome_config(instance, welcome)
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('كلمة المرور الحالية غير صحيحة.')
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': 'كلمتا المرور غير متطابقتين.'})
        user = self.context['request'].user
        try:
            validate_password(attrs['new_password'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)})
        return attrs


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """Admin creating a user. Always a regular, active user; password required."""

    password = serializers.CharField(write_only=True, required=True)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=30)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'is_active', 'password']
        read_only_fields = ['id']

    def validate_username(self, value):
        value = value.strip()
        if _username_taken(value):
            raise serializers.ValidationError('اسم المستخدم مستخدم بالفعل.')
        return value

    def validate_email(self, value):
        value = normalize_email(value)
        if _email_taken(value):
            raise serializers.ValidationError('البريد الإلكتروني مستخدم بالفعل.')
        return value

    def validate_password(self, value):
        if not value:
            raise serializers.ValidationError('كلمة المرور مطلوبة.')
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        phone = validated_data.pop('phone', '')
        validated_data.pop('is_active', None)  # new users are always active
        user = User(**validated_data)
        user.is_active = True
        user.is_staff = False       # new accounts are regular users
        user.is_superuser = False
        user.set_password(password)
        user.save()
        set_phone(user, phone)
        return user


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """Admin editing a user: name, email, username, phone, active flag."""

    phone = serializers.CharField(required=False, allow_blank=True, max_length=30)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'is_active']
        read_only_fields = ['id']

    def validate_username(self, value):
        value = value.strip()
        if _username_taken(value, exclude_pk=self.instance.pk):
            raise serializers.ValidationError('اسم المستخدم مستخدم بالفعل.')
        return value

    def validate_email(self, value):
        value = normalize_email(value)
        if _email_taken(value, exclude_pk=self.instance.pk):
            raise serializers.ValidationError('البريد الإلكتروني مستخدم بالفعل.')
        return value

    def update(self, instance, validated_data):
        phone = validated_data.pop('phone', None)
        instance = super().update(instance, validated_data)
        set_phone(instance, phone)
        return instance
