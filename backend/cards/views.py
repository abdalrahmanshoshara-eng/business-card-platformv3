from __future__ import annotations

import os
import re
import tempfile

from django.db.models import Q
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from rest_framework import pagination, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import BusinessCard
from .serializers import BusinessCardSerializer
from .services.extractor import extract_business_card
from .services.image_processing import preprocess_image
from .services.normalization import duplicate_reason
from .services.card_data import INVESTMENT_TYPE_CHOICES, prepare_card_data
from .services.natural_search import apply_natural_search, derive_category, parse_natural_query

def _prepare_data(data: dict) -> dict:
    return prepare_card_data(data)



class BusinessCardPagination(pagination.PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class BusinessCardViewSet(viewsets.ModelViewSet):
    queryset = BusinessCard.objects.all().order_by('-sequence_number', '-id')
    serializer_class = BusinessCardSerializer
    pagination_class = BusinessCardPagination

    def get_queryset(self):
        qs = BusinessCard.objects.all()
        q = self.request.query_params.get('q', '').strip()
        if q:
            parsed = parse_natural_query(q)
            qs = apply_natural_search(qs, parsed)

        company = self.request.query_params.get('company', '').strip()
        if company:
            qs = qs.filter(
                Q(company_name__icontains=company) |
                Q(company_name_ar__icontains=company) |
                Q(company_name_en__icontains=company)
            )

        activity = self.request.query_params.get('activity', '').strip()
        if activity:
            qs = qs.filter(company_activity__icontains=activity)

        # Exact-match filter used by the "stats by category" panel, since
        # those buckets are derived (see derive_category) and don't always
        # equal the raw company_activity text.
        category = self.request.query_params.get('category', '').strip()
        if category:
            matching_ids = [
                card_id for card_id, activity_value in qs.values_list('id', 'company_activity')
                if derive_category(activity_value) == category
            ]
            qs = qs.filter(id__in=matching_ids)

        investment_type = self.request.query_params.get('investment_type', '').strip()
        if investment_type:
            qs = qs.filter(Q(investment_type__icontains=investment_type) | Q(investment_type_other__icontains=investment_type))

        needs_review = self.request.query_params.get('needs_review')
        if needs_review in {'true', 'false'}:
            qs = qs.filter(needs_review=(needs_review == 'true'))

        status_value = self.request.query_params.get('status', '').strip()
        if status_value:
            qs = qs.filter(status=status_value)

        sort_value = self.request.query_params.get('sort', 'newest').strip().lower()
        if sort_value == 'oldest':
            return qs.order_by('sequence_number', 'id')
        return qs.order_by('-sequence_number', '-id')

    def perform_create(self, serializer):
        data = _prepare_data(serializer.validated_data)
        serializer.save(**data)

    def perform_update(self, serializer):
        current = {
            field.name: getattr(serializer.instance, field.name)
            for field in BusinessCard._meta.fields
            if field.name not in {'id', 'sequence_number', 'created_at', 'updated_at', 'front_image', 'back_image'}
        }
        current.update(serializer.validated_data)
        data = prepare_card_data(current, touched_fields=set(serializer.validated_data))
        serializer.save(**data)

    @action(detail=False, methods=['post'], url_path='extract')
    def extract(self, request):
        front = request.FILES.get('front')
        back = request.FILES.get('back')
        if not front:
            return Response({'detail': 'يجب رفع صورة الوجه الأمامي.'}, status=status.HTTP_400_BAD_REQUEST)

        with tempfile.TemporaryDirectory() as tmpdir:
            front_path = os.path.join(tmpdir, front.name or 'front.jpg')
            with open(front_path, 'wb') as file_handle:
                for chunk in front.chunks():
                    file_handle.write(chunk)
            front_processed = preprocess_image(front_path)

            back_processed = None
            if back:
                back_path = os.path.join(tmpdir, back.name or 'back.jpg')
                with open(back_path, 'wb') as file_handle:
                    for chunk in back.chunks():
                        file_handle.write(chunk)
                back_processed = preprocess_image(back_path)

            try:
                extracted = extract_business_card(front_processed, back_processed).model_dump()
            except Exception as exc:
                msg = str(exc)
                if '429' in msg or 'RESOURCE_EXHAUSTED' in msg:
                    retry_seconds = None
                    m = re.search(r'retry[^\d]*(\d+(?:\.\d+)?)\s*s', msg, re.I)
                    if m:
                        retry_seconds = int(float(m.group(1))) + 1
                    detail = 'تم تجاوز الحد اليومي المجاني لـ Gemini API (20 طلب/يوم).'
                    if retry_seconds:
                        detail += f' يرجى الانتظار {retry_seconds} ثانية ثم المحاولة مجدداً.'
                    else:
                        detail += ' يرجى المحاولة لاحقاً.'
                    return Response({'detail': detail}, status=status.HTTP_429_TOO_MANY_REQUESTS)
                raise

        prepared = _prepare_data(extracted)
        existing = BusinessCard.objects.filter(duplicate_hash=prepared['duplicate_hash']).first()
        if not existing:
            for email in prepared.get('emails', []):
                existing = BusinessCard.objects.filter(emails__icontains=email).first()
                if existing:
                    break
        if not existing:
            for phone in prepared.get('mobile_numbers', []):
                digits = ''.join(char for char in phone if char.isdigit())
                if digits:
                    existing = BusinessCard.objects.filter(mobile_numbers__icontains=digits[-8:]).first()
                    if existing:
                        break

        if existing:
            return Response({
                'duplicate': True,
                'saved': False,
                'reason': duplicate_reason(prepared, existing),
                'existing_card': BusinessCardSerializer(existing, context={'request': request}).data,
                'extracted_data': extracted,
            }, status=status.HTTP_200_OK)

        front.seek(0)
        if back:
            back.seek(0)

        card = BusinessCard.objects.create(
            **prepared,
            status='needs_review' if prepared.get('needs_review') else 'new',
            front_image=front,
            back_image=back if back else None,
        )
        return Response({
            'duplicate': False,
            'saved': True,
            'card': BusinessCardSerializer(card, context={'request': request}).data,
            'message': f'تم حفظ الكرت كسجل رقم {card.sequence_number}',
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        qs = BusinessCard.objects.all()
        return Response({
            'total': qs.count(),
            'needs_review': qs.filter(needs_review=True).count(),
            'companies': qs.exclude(company_name='').values('company_name').distinct().count(),
            'with_email': qs.exclude(emails=[]).count(),
            'with_phone': qs.exclude(mobile_numbers=[]).count(),
        })

    @action(detail=False, methods=['get'], url_path='stats-by-category')
    def stats_by_category(self, request):
        """Count companies/cards grouped by specialty (activity or investment type).

        Category resolution per card:
        - field=activity (default): ``derive_category(company_activity)`` -
          the imported activity text is free-form (e.g. "هندسية - شركة
          الإنشاءات..." or "نشاط غير محدد"), so it is bucketed down to its
          leading segment to keep the panel compact instead of showing one
          row per company.
        - field=investment_type: the institutional investment_type choice,
          grouping custom values under "غير ذلك".

        Counting prefers distinct company_name values within a category so
        the same company imported on multiple cards isn't counted twice;
        cards with no company name are counted individually.
        """
        field = request.query_params.get('field', 'activity').strip().lower()
        qs = BusinessCard.objects.all().only(
            'company_activity', 'investment_type', 'investment_type_other', 'company_name'
        )

        buckets: dict[str, dict] = {}
        for card in qs:
            if field == 'investment_type':
                category = (card.investment_type or '').strip() or 'غير محدد'
            else:
                category = derive_category(card.company_activity)

            bucket = buckets.setdefault(category, {'companies': set(), 'blank_count': 0})
            name = (card.company_name or '').strip()
            if name:
                bucket['companies'].add(name)
            else:
                bucket['blank_count'] += 1

        result = [
            {'category': category, 'count': len(bucket['companies']) + bucket['blank_count']}
            for category, bucket in buckets.items()
        ]
        result.sort(key=lambda item: item['count'], reverse=True)
        return Response(result)

    @action(detail=False, methods=['get'], url_path='export-xlsx')
    def export_xlsx(self, request):
        wb = Workbook()
        ws = wb.active
        ws.title = 'جهات الاتصال'
        ws.sheet_view.rightToLeft = True

        headers = [
            ('#', 6),
            ('اسم الشخص', 28),
            ('المنصب (عربي)', 22),
            ('المنصب (إنجليزي)', 22),
            ('الشركة', 28),
            ('الموبايلات', 22),
            ('الإيميلات', 28),
            ('الموقع', 28),
            ('العنوان', 30),
            ('نشاط الشركة', 35),
            ('نوع الاستثمار', 35),
            ('تفاصيل الاستثمار', 30),
            ('يحتاج مراجعة', 14),
            ('تاريخ الإضافة', 18),
        ]

        header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
        header_font = Font(name='Arial', bold=True, color='FFFFFF', size=11)
        header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        thin_border = Border(
            left=Side(style='thin', color='AAAAAA'),
            right=Side(style='thin', color='AAAAAA'),
            top=Side(style='thin', color='AAAAAA'),
            bottom=Side(style='thin', color='AAAAAA'),
        )

        for col_idx, (header_text, col_width) in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header_text)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
            cell.border = thin_border
            ws.column_dimensions[get_column_letter(col_idx)].width = col_width

        ws.row_dimensions[1].height = 30
        ws.freeze_panes = 'A2'

        row_fill_even = PatternFill(start_color='EBF3FB', end_color='EBF3FB', fill_type='solid')
        data_font = Font(name='Arial', size=10)
        center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        right_align = Alignment(horizontal='right', vertical='center', wrap_text=True)

        for row_idx, card in enumerate(self.get_queryset(), start=2):
            row_fill = row_fill_even if row_idx % 2 == 0 else None
            row_data = [
                card.sequence_number,
                card.person_name,
                card.job_title_ar or '',
                card.job_title_en or '',
                card.company_name,
                ' | '.join(card.mobile_numbers or []),
                ' | '.join(card.emails or []),
                card.website,
                card.address,
                card.company_activity,
                card.investment_type,
                card.investment_type_other,
                'نعم' if card.needs_review else 'لا',
                card.created_at.strftime('%Y-%m-%d %H:%M'),
            ]
            for col_idx, value in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = data_font
                cell.border = thin_border
                if col_idx == 1:
                    cell.alignment = center_align
                else:
                    cell.alignment = right_align
                if row_fill:
                    cell.fill = row_fill
            ws.row_dimensions[row_idx].height = 20

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="business-cards.xlsx"'
        wb.save(response)
        return response


@api_view(['GET'])
def health(request):
    return Response({'ok': True, 'service': 'business-card-platform'})
