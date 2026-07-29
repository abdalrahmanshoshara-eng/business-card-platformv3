from decimal import Decimal

from django.contrib import admin
from django.db.models import Count, Sum
from django.utils import timezone

from .models import BusinessCard, CompanyDomainEnrichment, ExtractionRequest, GeminiUsageLog


@admin.register(BusinessCard)
class BusinessCardAdmin(admin.ModelAdmin):
    list_display = ('sequence_number', 'person_name', 'company_name', 'job_title', 'confidence', 'needs_review', 'created_at')
    search_fields = ('person_name', 'company_name', 'job_title', 'company_activity', 'website', 'raw_text')
    list_filter = ('needs_review', 'status', 'created_at')
    readonly_fields = ('sequence_number', 'duplicate_hash', 'review_fields', 'created_at', 'updated_at')


@admin.register(ExtractionRequest)
class ExtractionRequestAdmin(admin.ModelAdmin):
    list_display = ('idempotency_key', 'owner', 'status', 'card', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at')
    search_fields = ('idempotency_key', 'image_fingerprint')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CompanyDomainEnrichment)
class CompanyDomainEnrichmentAdmin(admin.ModelAdmin):
    list_display = ('canonical_domain', 'status', 'industry', 'model_name', 'enriched_at', 'refresh_after')
    list_filter = ('status',)
    search_fields = ('canonical_domain', 'company_name', 'industry')
    readonly_fields = ('created_at', 'updated_at', 'content_hash')


@admin.register(GeminiUsageLog)
class GeminiUsageLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'operation_type', 'request_status', 'model_name',
        'total_token_count', 'estimated_total_cost_usd', 'retry_number', 'owner',
    )
    list_filter = ('operation_type', 'request_status', 'model_name', 'created_at')
    search_fields = ('model_name', 'error_type', 'error_code')
    readonly_fields = [f.name for f in GeminiUsageLog._meta.fields]

    def changelist_view(self, request, extra_context=None):
        """Attach a compact usage/cost summary to the log list page.

        This reuses Django's default change_list template and simply surfaces the
        numbers via the message framework so no new dashboard/template is needed.
        """
        now = timezone.now()
        today = now.date()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        base = GeminiUsageLog.objects.all()

        def agg(qs):
            row = qs.aggregate(calls=Count('id'), tokens=Sum('total_token_count'), cost=Sum('estimated_total_cost_usd'))
            return row['calls'] or 0, row['tokens'] or 0, row['cost'] or Decimal('0')

        today_qs = base.filter(created_at__date=today)
        extraction_today = today_qs.filter(operation_type=GeminiUsageLog.OP_CARD_EXTRACTION)
        enrichment_today = today_qs.filter(operation_type=GeminiUsageLog.OP_WEBSITE_ENRICHMENT)

        calls_today, tokens_today, cost_today = agg(today_qs)
        _, _, cost_month = agg(base.filter(created_at__gte=month_start))
        cards_today = extraction_today.exclude(card__isnull=True).values('card').distinct().count()
        avg_card = (agg(extraction_today)[2] / max(1, extraction_today.count()))

        summary = (
            f'اليوم: {calls_today} استدعاء | كروت: {cards_today} | توكنات: {tokens_today} | '
            f'تكلفة اليوم ≈ ${cost_today:.4f} (استخراج ${agg(extraction_today)[2]:.4f} / إثراء ${agg(enrichment_today)[2]:.4f}) | '
            f'تكلفة الشهر ≈ ${cost_month:.4f} | متوسط الكرت ≈ ${avg_card:.4f} | '
            f'فشل: {today_qs.filter(request_status="failed").count()} | '
            f'إعادات محاولة: {today_qs.filter(retry_number__gt=0).count()} '
            f'(تكلفة تقديرية مبنية على metadata والأسعار المضبوطة، وليست الفاتورة النهائية من Google)'
        )
        self.message_user(request, summary)
        return super().changelist_view(request, extra_context=extra_context)
