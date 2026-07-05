from django.test import TestCase
from rest_framework.test import APIClient

from .models import BusinessCard
from .services.card_data import prepare_card_data
from .services.natural_search import derive_category, normalize_arabic, parse_natural_query


def make_card(**overrides):
    data = {
        'person_name': 'Test Person',
        'company_name': 'Test Co',
        'company_activity': '',
        'investment_type': '',
        'investment_type_other': '',
        'address': '',
        'emails': [],
        'mobile_numbers': [],
        'raw_text': '',
        'status': 'new',
    }
    data.update(overrides)
    prepared = prepare_card_data(data, infer_missing_investment=False)
    return BusinessCard.objects.create(**prepared)


class NormalizeArabicTests(TestCase):
    def test_hamza_variants_fold_together(self):
        self.assertEqual(normalize_arabic('الأمن'), normalize_arabic('الامن'))
        self.assertEqual(normalize_arabic('إسمنت'), normalize_arabic('اسمنت'))
        self.assertEqual(normalize_arabic('آلات'), normalize_arabic('الات'))

    def test_ta_marbuta_and_alef_maksura(self):
        self.assertEqual(normalize_arabic('حماة'), normalize_arabic('حماه'))
        self.assertEqual(normalize_arabic('مصطفى'), normalize_arabic('مصطفي'))

    def test_latin_lowercased(self):
        self.assertEqual(normalize_arabic('WATER'), 'water')


class ParseNaturalQueryTests(TestCase):
    def test_water_activity_arabic(self):
        parsed = parse_natural_query('عرضلي شركات المياه')
        self.assertEqual(parsed['activity_keyword'], 'مياه')
        self.assertEqual(parsed['text'], '')

    def test_electricity_english(self):
        parsed = parse_natural_query('show me electricity companies')
        self.assertEqual(parsed['activity_keyword'], 'كهرباء')

    def test_country_turkish(self):
        parsed = parse_natural_query('الشركات التركية')
        self.assertEqual(parsed['country'], 'تركيا')

    def test_city_damascus(self):
        parsed = parse_natural_query('بدي الشركات الموجودة في دمشق')
        self.assertEqual(parsed['city'], 'دمشق')

    def test_needs_review(self):
        parsed = parse_natural_query('عرض الكروت التي تحتاج مراجعة')
        self.assertEqual(parsed['status'], 'needs_review')

    def test_missing_email(self):
        parsed = parse_natural_query('عرضلي الشركات التي ليس لديها بريد الكتروني')
        self.assertTrue(parsed['missing_email'])

    def test_missing_phone_english(self):
        parsed = parse_natural_query('companies with no phone')
        self.assertTrue(parsed['missing_phone'])

    def test_plain_text_falls_back(self):
        parsed = parse_natural_query('SAMIROCK')
        self.assertIsNone(parsed['activity_keyword'])
        self.assertIsNone(parsed['city'])
        self.assertIsNone(parsed['country'])
        self.assertEqual(parsed['text'], 'SAMIROCK')

    def test_multiword_leftover_has_no_dangling_fragments(self):
        # "شركات" is stripped as a generic noun and "سيبراني" is recognized
        # as an activity keyword; "امن" remains as free text with no stray
        # "ال" fragment left behind.
        parsed = parse_natural_query('بدي شركات امن سيبراني')
        self.assertEqual(parsed['activity_keyword'], 'سيبراني')
        self.assertEqual(parsed['text'].split(), ['امن'])


class DeriveCategoryTests(TestCase):
    def test_blank_and_placeholder_map_to_unknown(self):
        self.assertEqual(derive_category(''), 'غير محدد')
        self.assertEqual(derive_category('نشاط غير محدد'), 'غير محدد')

    def test_dash_separated_takes_first_segment(self):
        self.assertEqual(
            derive_category('هندسية - شركة الإنشاءات والتخطيط المحدودة'),
            'هندسية',
        )

    def test_slash_separated_takes_first_segment(self):
        self.assertEqual(derive_category('تكنو فيست تركيا/استشارات تجارية'), 'تكنو فيست تركيا')

    def test_plain_value_used_as_is(self):
        self.assertEqual(derive_category('مقاولات'), 'مقاولات')


class NaturalSearchApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        make_card(company_name='Water Co', company_activity='شركة مياه وصرف صحي')
        make_card(company_name='Volt Co', company_activity='كهرباء وطاقة')
        make_card(company_name='Damascus Trading', address='دمشق - سوريا')
        make_card(company_name='Istanbul Textiles', address='اسطنبول - تركيا')
        make_card(company_name='No Email Co', emails=[], status='needs_review')
        make_card(
            company_name='CIPER',
            company_activity='اتصالات - مجال الأمن السيبراني',
        )
        make_card(
            company_name='Engineering Consult Co',
            company_activity='استشارات هندسية',
        )

    def test_search_water_companies(self):
        response = self.client.get('/api/cards/', {'q': 'عرضلي شركات المياه'})
        self.assertEqual(response.status_code, 200)
        names = [c['company_name'] for c in response.data['results']]
        self.assertIn('Water Co', names)
        self.assertNotIn('Volt Co', names)

    def test_search_turkish_companies(self):
        response = self.client.get('/api/cards/', {'q': 'الشركات التركية'})
        self.assertEqual(response.status_code, 200)
        names = [c['company_name'] for c in response.data['results']]
        self.assertIn('Istanbul Textiles', names)

    def test_search_damascus(self):
        response = self.client.get('/api/cards/', {'q': 'في دمشق'})
        self.assertEqual(response.status_code, 200)
        names = [c['company_name'] for c in response.data['results']]
        self.assertIn('Damascus Trading', names)

    def test_search_needs_review(self):
        response = self.client.get('/api/cards/', {'q': 'تحتاج مراجعة'})
        self.assertEqual(response.status_code, 200)
        names = [c['company_name'] for c in response.data['results']]
        self.assertIn('No Email Co', names)

    def test_search_cybersecurity_multiword_and_hamza_variant(self):
        # Regression test: user typed "امن" (no hamza) while the stored data
        # has "الأمن" (with hamza), and the phrase spans two words.
        response = self.client.get('/api/cards/', {'q': 'بدي شركات امن سيبراني'})
        self.assertEqual(response.status_code, 200)
        names = [c['company_name'] for c in response.data['results']]
        self.assertIn('CIPER', names)

    def test_search_engineering_compound_phrase(self):
        # Regression test: "استشارات هندسية" is not a single map entry, but
        # tokenized matching should still find "هندسية" in company_activity.
        response = self.client.get('/api/cards/', {'q': 'بدي شركات هندسية'})
        self.assertEqual(response.status_code, 200)
        names = [c['company_name'] for c in response.data['results']]
        self.assertIn('Engineering Consult Co', names)

    def test_stats_by_category(self):
        response = self.client.get('/api/cards/stats-by-category/')
        self.assertEqual(response.status_code, 200)
        categories = {item['category']: item['count'] for item in response.data}
        self.assertIn('شركة مياه وصرف صحي', categories)
        self.assertIn('غير محدد', categories)
        # "اتصالات - مجال الأمن السيبراني" is bucketed under "اتصالات".
        self.assertIn('اتصالات', categories)

    def test_category_filter_matches_bucket_not_substring(self):
        response = self.client.get('/api/cards/', {'category': 'اتصالات'})
        self.assertEqual(response.status_code, 200)
        names = [c['company_name'] for c in response.data['results']]
        self.assertIn('CIPER', names)
        self.assertNotIn('Engineering Consult Co', names)


class BusinessCardUpdateApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_patch_base_job_title_replaces_existing_bilingual_title(self):
        card = make_card(
            job_title='Old Arabic\nOld English',
            job_title_ar='Old Arabic',
            job_title_en='Old English',
        )

        response = self.client.patch(
            f'/api/cards/{card.id}',
            {'job_title': 'New Position'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.job_title, 'New Position')
        self.assertEqual(card.job_title_ar, 'New Position')
        self.assertEqual(card.job_title_en, '')

    def test_patch_base_job_title_can_clear_existing_bilingual_title(self):
        card = make_card(
            job_title='Old Arabic\nOld English',
            job_title_ar='Old Arabic',
            job_title_en='Old English',
        )

        response = self.client.patch(
            f'/api/cards/{card.id}',
            {'job_title': ''},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.job_title, '')
        self.assertEqual(card.job_title_ar, '')
        self.assertEqual(card.job_title_en, '')
