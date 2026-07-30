from django.conf import settings
from django.db import IntegrityError, models
from django.utils import timezone


class BusinessCard(models.Model):
    STATUS_CHOICES = [
        ('new', 'جديد'),
        ('reviewed', 'تمت المراجعة'),
        ('needs_review', 'يحتاج مراجعة'),
    ]

    # Nullable so legacy cards can be backfilled before enforcing ownership.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='business_cards',
        null=True,
        blank=True,
        db_index=True,
    )
    sequence_number = models.PositiveIntegerField(unique=True, editable=False, db_index=True)
    person_name = models.CharField(max_length=255, blank=True, db_index=True)
    person_name_ar = models.CharField(max_length=255, blank=True, db_index=True)
    person_name_en = models.CharField(max_length=255, blank=True, db_index=True)
    job_title = models.CharField(max_length=255, blank=True)
    job_title_ar = models.CharField(max_length=255, blank=True)
    job_title_en = models.CharField(max_length=255, blank=True)
    company_name = models.CharField(max_length=255, blank=True, db_index=True)
    company_name_ar = models.CharField(max_length=255, blank=True, db_index=True)
    company_name_en = models.CharField(max_length=255, blank=True, db_index=True)
    mobile_numbers = models.JSONField(default=list, blank=True)
    emails = models.JSONField(default=list, blank=True)
    website = models.URLField(max_length=500, blank=True)
    address = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True, db_index=True)
    company_activity = models.TextField(blank=True, db_index=True)
    investment_type = models.CharField(max_length=255, blank=True, db_index=True)
    investment_type_other = models.CharField(max_length=255, blank=True)
    raw_text = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    needs_review = models.BooleanField(default=True, db_index=True)
    review_notes = models.TextField(blank=True)
    # Names of fields Gemini flagged as low-confidence / conflicting so the UI
    # can highlight exactly what a human should double-check.
    review_fields = models.JSONField(default=list, blank=True)
    website_visit_note = models.TextField(blank=True)
    duplicate_hash = models.CharField(max_length=128, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', db_index=True)
    # Welcome-email send state (see accounts welcome-email feature). One-time by
    # default; a resend is explicit.
    WELCOME_NOT_SENT = 'not_sent'
    WELCOME_SENT = 'sent'
    WELCOME_FAILED = 'failed'
    WELCOME_STATUS_CHOICES = [
        (WELCOME_NOT_SENT, 'لم تُرسل'),
        (WELCOME_SENT, 'تم الإرسال'),
        (WELCOME_FAILED, 'فشل الإرسال'),
    ]
    welcome_status = models.CharField(max_length=20, choices=WELCOME_STATUS_CHOICES, default=WELCOME_NOT_SENT, db_index=True)
    welcome_sent_at = models.DateTimeField(null=True, blank=True)
    welcome_sent_to = models.EmailField(blank=True)
    welcome_error = models.TextField(blank=True)
    front_image = models.ImageField(upload_to='cards/front/', blank=True, null=True)
    back_image = models.ImageField(upload_to='cards/back/', blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-sequence_number']
        indexes = [
            models.Index(fields=['company_name', 'person_name']),
            models.Index(fields=['created_at', 'status']),
            # Main list query: scope by owner, order by sequence_number desc.
            models.Index(fields=['owner', '-sequence_number'], name='card_owner_seq_idx'),
        ]
        constraints = [
            # duplicate_hash is unique per owner so two different users may
            # each hold a card with the same contact info without leaking it.
            models.UniqueConstraint(
                fields=['owner', 'duplicate_hash'],
                name='uniq_owner_duplicate_hash',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.sequence_number:
            super().save(*args, **kwargs)
            return

        # Compute the next sequence number with a small retry loop so a unique
        # collision on sequence_number does not become a random 500.
        for attempt in range(5):
            last_number = (
                BusinessCard.objects.order_by('-sequence_number')
                .values_list('sequence_number', flat=True)
                .first()
            )
            self.sequence_number = (last_number or 0) + 1
            try:
                super().save(*args, **kwargs)
                return
            except IntegrityError as exc:
                # Only a sequence_number collision is retryable; any other
                # unique conflict (e.g. duplicate_hash) must surface as-is.
                if 'sequence_number' not in str(exc).lower() or attempt >= 4:
                    raise
                self.sequence_number = None

    def __str__(self):
        return f"#{self.sequence_number} {self.person_name or self.company_name or 'Business Card'}"


class ExtractionRequest(models.Model):
    """One card-extraction operation. Enforces idempotency so a double-click,
    a browser refresh, or a client timeout never bills Gemini twice for the same
    upload. The (owner, idempotency_key) pair is unique; the image fingerprint
    lets us short-circuit re-processing of byte-identical uploads for the owner.
    """

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'قيد الانتظار'),
        (STATUS_PROCESSING, 'قيد المعالجة'),
        (STATUS_COMPLETED, 'مكتمل'),
        (STATUS_FAILED, 'فشل'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='extraction_requests',
        null=True,
        blank=True,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=128, db_index=True)
    # SHA-256 over (front bytes [+ back bytes] + schema/pipeline version).
    image_fingerprint = models.CharField(max_length=128, blank=True, db_index=True)
    schema_version = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    card = models.ForeignKey(
        'BusinessCard',
        on_delete=models.SET_NULL,
        related_name='extraction_requests',
        null=True,
        blank=True,
    )
    # Cached response payload so a repeat of a completed request replays the
    # exact previous result without another Gemini call.
    result = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'idempotency_key'],
                name='uniq_owner_idempotency_key',
            ),
        ]
        indexes = [
            models.Index(fields=['owner', 'image_fingerprint'], name='extreq_owner_fp_idx'),
        ]

    def __str__(self):
        return f'ExtractionRequest {self.idempotency_key} [{self.status}]'


class GeminiUsageLog(models.Model):
    """Persistent, per-call record of Gemini usage and estimated cost.

    Costs are estimates derived from real usage metadata and the configured
    per-model prices (see services/pricing.py); they are stored as Decimal and
    left NULL (with a reason) when metadata or pricing is unavailable.
    """

    OP_CARD_EXTRACTION = 'card_extraction'
    OP_WEBSITE_ENRICHMENT = 'website_enrichment'
    OPERATION_CHOICES = [
        (OP_CARD_EXTRACTION, 'استخراج بطاقة'),
        (OP_WEBSITE_ENRICHMENT, 'إثراء من الموقع'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='gemini_usage_logs',
        null=True,
        blank=True,
        db_index=True,
    )
    card = models.ForeignKey(
        'BusinessCard',
        on_delete=models.SET_NULL,
        related_name='gemini_usage_logs',
        null=True,
        blank=True,
    )
    extraction_request = models.ForeignKey(
        'ExtractionRequest',
        on_delete=models.SET_NULL,
        related_name='usage_logs',
        null=True,
        blank=True,
    )
    model_name = models.CharField(max_length=100, blank=True)
    operation_type = models.CharField(max_length=32, choices=OPERATION_CHOICES, default=OP_CARD_EXTRACTION, db_index=True)
    request_status = models.CharField(max_length=20, default='completed', db_index=True)

    input_token_count = models.IntegerField(default=0)
    output_token_count = models.IntegerField(default=0)
    thoughts_token_count = models.IntegerField(null=True, blank=True)
    cached_token_count = models.IntegerField(null=True, blank=True)
    total_token_count = models.IntegerField(default=0)
    request_count = models.IntegerField(default=1)
    retry_number = models.IntegerField(default=0)

    estimated_input_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    estimated_output_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    estimated_total_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    currency = models.CharField(max_length=8, default='USD')
    cost_note = models.CharField(max_length=120, blank=True)

    latency_ms = models.IntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_type = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['operation_type', 'created_at'], name='usage_op_created_idx'),
        ]

    def __str__(self):
        return f'{self.operation_type} {self.request_status} {self.total_token_count}tok'


class CompanyDomainEnrichment(models.Model):
    """Cached company-website analysis keyed by canonical (registered) domain.

    Scoping decision: results are keyed by the *registered domain* (eTLD+1, e.g.
    ``example.com`` for ``www.example.com`` and ``careers.example.com``) and are
    shared system-wide, because company website data is public and non-sensitive.
    This means one enrichment serves every employee of the same company instead
    of re-analysing the site per card/owner. See ARCHITECTURE.md.
    """

    STATUS_NOT_REQUESTED = 'not_requested'
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_UNAVAILABLE = 'unavailable'
    STATUS_CHOICES = [
        (STATUS_NOT_REQUESTED, 'لم يُطلب'),
        (STATUS_PENDING, 'قيد الانتظار'),
        (STATUS_PROCESSING, 'قيد المعالجة'),
        (STATUS_COMPLETED, 'مكتمل'),
        (STATUS_FAILED, 'فشل'),
        (STATUS_UNAVAILABLE, 'غير متاح'),
    ]

    canonical_domain = models.CharField(max_length=255, unique=True, db_index=True)
    source_url = models.URLField(max_length=500, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    company_description = models.TextField(blank=True)
    industry = models.CharField(max_length=255, blank=True)
    services = models.JSONField(default=list, blank=True)
    products = models.JSONField(default=list, blank=True)
    countries = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=16, blank=True)
    raw_extracted_data = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    model_name = models.CharField(max_length=100, blank=True)
    schema_version = models.CharField(max_length=32, blank=True)
    content_hash = models.CharField(max_length=128, blank=True)
    last_error = models.TextField(blank=True)

    # Simple DB-level lock: a non-null lock timestamp means an enrichment is in
    # flight for this domain, so a concurrent request reuses/queues instead of
    # calling Gemini again.
    locked_at = models.DateTimeField(null=True, blank=True)

    enriched_at = models.DateTimeField(null=True, blank=True)
    refresh_after = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def is_fresh(self) -> bool:
        if self.status != self.STATUS_COMPLETED:
            return False
        if self.refresh_after is None:
            return True
        return timezone.now() < self.refresh_after

    def __str__(self):
        return f'{self.canonical_domain} [{self.status}]'
