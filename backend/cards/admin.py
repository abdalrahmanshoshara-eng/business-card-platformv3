from django.contrib import admin
from .models import BusinessCard

@admin.register(BusinessCard)
class BusinessCardAdmin(admin.ModelAdmin):
    list_display = ('sequence_number', 'person_name', 'company_name', 'job_title', 'confidence', 'needs_review', 'created_at')
    search_fields = ('person_name', 'company_name', 'job_title', 'company_activity', 'website', 'raw_text')
    list_filter = ('needs_review', 'status', 'created_at')
    readonly_fields = ('sequence_number', 'duplicate_hash', 'created_at', 'updated_at')
