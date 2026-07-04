from django.db import models
from django.utils import timezone


class BusinessCard(models.Model):
    STATUS_CHOICES = [
        ('new', 'جديد'),
        ('reviewed', 'تمت المراجعة'),
        ('needs_review', 'يحتاج مراجعة'),
    ]

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
    company_activity = models.TextField(blank=True, db_index=True)
    investment_type = models.CharField(max_length=255, blank=True, db_index=True)
    investment_type_other = models.CharField(max_length=255, blank=True)
    raw_text = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    needs_review = models.BooleanField(default=True, db_index=True)
    review_notes = models.TextField(blank=True)
    website_visit_note = models.TextField(blank=True)
    duplicate_hash = models.CharField(max_length=128, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', db_index=True)
    front_image = models.ImageField(upload_to='cards/front/', blank=True, null=True)
    back_image = models.ImageField(upload_to='cards/back/', blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-sequence_number']
        indexes = [
            models.Index(fields=['company_name', 'person_name']),
            models.Index(fields=['created_at', 'status']),
        ]

    def save(self, *args, **kwargs):
        if not self.sequence_number:
            last = BusinessCard.objects.order_by('-sequence_number').first()
            self.sequence_number = (last.sequence_number + 1) if last else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"#{self.sequence_number} {self.person_name or self.company_name or 'Business Card'}"
