from __future__ import annotations

import json
import re

from rest_framework import serializers

from .models import BusinessCard
from .services.normalization import normalize_website


class StringListField(serializers.ListField):
    child = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def to_internal_value(self, data):
        if data in (None, ''):
            return []
        if isinstance(data, str):
            value = data.strip()
            if not value:
                return []
            try:
                parsed = json.loads(value)
                data = parsed
            except json.JSONDecodeError:
                data = re.split(r'[|,\n]+', value)
        return super().to_internal_value(data)


class BusinessCardSerializer(serializers.ModelSerializer):
    mobile_numbers = StringListField(required=False, allow_empty=True)
    emails = StringListField(required=False, allow_empty=True)
    website = serializers.CharField(required=False, allow_blank=True, max_length=500)
    front_image_url = serializers.SerializerMethodField()
    back_image_url = serializers.SerializerMethodField()

    class Meta:
        model = BusinessCard
        fields = [
            'id', 'sequence_number',
            'person_name', 'person_name_ar', 'person_name_en',
            'job_title', 'job_title_ar', 'job_title_en',
            'company_name', 'company_name_ar', 'company_name_en',
            'mobile_numbers', 'emails', 'website', 'address', 'country', 'company_activity',
            'investment_type', 'investment_type_other',
            'raw_text', 'confidence', 'needs_review', 'review_notes', 'website_visit_note',
            'status', 'front_image', 'back_image', 'front_image_url', 'back_image_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'sequence_number', 'created_at', 'updated_at', 'front_image_url', 'back_image_url']
        extra_kwargs = {
            'front_image': {'required': False, 'allow_null': True},
            'back_image': {'required': False, 'allow_null': True},
            'confidence': {'required': False},
            'needs_review': {'required': False},
            'status': {'required': False},
        }

    def validate_website(self, value: str) -> str:
        return normalize_website(value)

    def get_front_image_url(self, obj):
        # Route through the ownership-checked endpoint, not the raw media path.
        if obj.front_image and obj.pk:
            return f'/api/cards/{obj.pk}/image/front'
        return ''

    def get_back_image_url(self, obj):
        if obj.back_image and obj.pk:
            return f'/api/cards/{obj.pk}/image/back'
        return ''
