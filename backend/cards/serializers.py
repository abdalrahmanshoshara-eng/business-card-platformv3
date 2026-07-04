from rest_framework import serializers
from .models import BusinessCard

class BusinessCardSerializer(serializers.ModelSerializer):
    front_image_url = serializers.SerializerMethodField()
    back_image_url = serializers.SerializerMethodField()

    class Meta:
        model = BusinessCard
        fields = [
            'id', 'sequence_number',
            'person_name', 'person_name_ar', 'person_name_en',
            'job_title', 'job_title_ar', 'job_title_en',
            'company_name', 'company_name_ar', 'company_name_en',
            'mobile_numbers', 'emails', 'website', 'address', 'company_activity',
            'investment_type', 'investment_type_other',
            'raw_text', 'confidence', 'needs_review', 'review_notes', 'website_visit_note',
            'status', 'front_image', 'back_image', 'front_image_url', 'back_image_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'sequence_number', 'created_at', 'updated_at', 'front_image_url', 'back_image_url']

    def get_front_image_url(self, obj):
        if obj.front_image:
            return obj.front_image.url
        return ''

    def get_back_image_url(self, obj):
        if obj.back_image:
            return obj.back_image.url
        return ''
