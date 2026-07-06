from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from django.conf import settings
from google import genai
from google.genai import types

from .normalization import normalize_website

ABOUT_WORDS = (
    'about', 'about-us', 'who-we-are', 'company', 'profile', 'overview', 'our-story',
    'من-نحن', 'عن-الشركة', 'عن', 'نبذة',
)
SERVICE_WORDS = (
    'services', 'service', 'what-we-do', 'solutions', 'products', 'product', 'industries',
    'خدمات', 'منتجات', 'حلول', 'قطاعات', 'مشاريع',
)
COMMON_PATHS = (
    '/ar/about', '/ar/about-us', '/ar/services', '/ar/solutions', '/من-نحن', '/عن-الشركة', '/خدمات',
    '/about', '/about-us', '/who-we-are', '/company-profile', '/services', '/solutions', '/products',
)
INVESTMENT_TYPE_KEYWORDS = [
    ('مؤسسة الحلج و الاقطان', ('cotton', 'spinning', 'ginning', 'yarn', 'textile fibers', 'أقطان', 'قطن', 'حلج')),
    ('المؤسسة العامة للصناعات الهندسية', ('engineering', 'industrial equipment', 'machinery', 'mechanical', 'electrical equipment', 'معدات', 'آلات', 'هندسية', 'هندسة', 'ميكانيك', 'كهربائية')),
    ('المؤسسة العامة للصناعات النسيجية', ('textile', 'garment', 'fabric', 'woven', 'knitwear', 'نسيج', 'ألبسة', 'أقمشة', 'غزل')),
    ('المؤسسة العامة للصناعات الكيميائية', ('chemical', 'pharma', 'pharmaceutical', 'detergent', 'paint', 'plastic', 'fertilizer', 'كيميائية', 'دوائية', 'منظفات', 'دهانات', 'بلاستيك', 'أسمدة')),
    ('مؤسسة الصناعات الغذائية', ('food', 'beverage', 'dairy', 'bakery', 'snack', 'agro food', 'غذائية', 'أغذية', 'مشروبات', 'ألبان', 'مخبوزات')),
    ('المؤسسة العامة للتبغ', ('tobacco', 'cigarette', 'cigar', 'smoking', 'تبغ', 'سجائر')),
    ('هيئة ادارة المعادن النبيلة وهيئة المواصفات و المقاييس', ('gold', 'silver', 'precious metals', 'assay', 'hallmark', 'standards', 'quality', 'metrology', 'testing', 'mining', 'geological', 'معادن', 'ذهب', 'فضة', 'مواصفات', 'مقاييس', 'جودة', 'اعتماد', 'تعدين')),
    ('مديرية المدن و المناطق الصناعية', ('industrial city', 'industrial zone', 'industrial estate', 'factory zone', 'مدينة صناعية', 'منطقة صناعية', 'استثمار صناعي')),
    ('مديرية الاشراف على التاهيل الفني', ('technical training', 'vocational', 'rehabilitation', 'skills development', 'training center', 'تأهيل فني', 'تدريب مهني', 'مركز تدريب')),
    ('مركز الاختبارات و الابحاث', ('laboratory', 'lab', 'research', 'r&d', 'quality control', 'analysis', 'اختبارات', 'أبحاث', 'مخبر', 'مختبر', 'تحليل')),
]


@dataclass
class PageText:
    url: str
    title: str
    text: str
    score: int


def _candidate_urls(url: str) -> list[str]:
    normalized = normalize_website(url)
    parsed = urlparse(normalized)
    host_path = (parsed.netloc + parsed.path).rstrip('/')
    out = []
    for scheme in ('https', 'http'):
        out.append(f'{scheme}://{host_path}'.rstrip('/'))
        if parsed.netloc and not parsed.netloc.startswith('www.'):
            out.append(f'{scheme}://www.{host_path}'.rstrip('/'))
    return list(dict.fromkeys([x for x in out if x]))


def _clean_html(html: str):
    soup = BeautifulSoup(html or '', 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'svg', 'iframe', 'form', 'footer']):
        tag.decompose()
    title = ''
    if soup.title and soup.title.string:
        title = ' '.join(soup.title.string.split())
    main = soup.find('main') or soup.find('article') or soup.body or soup
    text = ' '.join(main.get_text(' ').split())
    return text, title, soup


def _score_link(label: str, href: str) -> int:
    hay = f'{label} {href}'.lower()
    score = 0
    if any(word in hay for word in ABOUT_WORDS):
        score += 100
    if any(word in hay for word in SERVICE_WORDS):
        score += 80
    return score


def _important_links(base_url: str, soup: BeautifulSoup, limit: int = 10) -> list[str]:
    parsed_base = urlparse(base_url)
    scored = []
    for anchor in soup.find_all('a', href=True):
        label = ' '.join(anchor.get_text(' ').split())
        href = str(anchor.get('href', '')).strip()
        if not href or href.startswith(('mailto:', 'tel:', 'javascript:')):
            continue
        joined = urljoin(base_url, href).split('#')[0].rstrip('/')
        parsed_joined = urlparse(joined)
        if parsed_joined.netloc and parsed_joined.netloc != parsed_base.netloc:
            continue
        score = _score_link(label, href)
        if score > 0:
            scored.append((score, joined))

    origin = f'{parsed_base.scheme}://{parsed_base.netloc}'
    for path in COMMON_PATHS:
        scored.append((_score_link(path, path) - 10, urljoin(origin, path).rstrip('/')))

    scored.sort(key=lambda item: item[0], reverse=True)
    links: list[str] = []
    for _, link in scored:
        if link and link not in links and link != base_url.rstrip('/'):
            links.append(link)
        if len(links) >= limit:
            break
    return links


def fetch_website_text(url: str, timeout: float = 12.0) -> tuple[str, str]:
    if not url:
        return '', 'لا يوجد موقع.'

    headers = {'User-Agent': 'Mozilla/5.0 BusinessCardPlatform/1.0', 'Accept-Language': 'ar,en;q=0.9'}
    errors = []
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers, verify=False) as client:
        for candidate in _candidate_urls(url):
            try:
                res = client.get(candidate)
                res.raise_for_status()
                text, title, soup = _clean_html(res.text)
                pages = [PageText(str(res.url), title, text[:5000], 40)] if text else []
                for index, link in enumerate(_important_links(str(res.url), soup)):
                    try:
                        page_res = client.get(link)
                        page_res.raise_for_status()
                        page_text, page_title, _ = _clean_html(page_res.text)
                        if len(page_text) >= 80:
                            pages.append(PageText(str(page_res.url), page_title, page_text[:6000], 120 - index))
                    except Exception:
                        continue
                if pages:
                    pages.sort(key=lambda page: page.score, reverse=True)
                    body = ' '.join([f'--- PAGE {page.title or page.url} URL {page.url} --- {page.text}' for page in pages[:6]])
                    return re.sub(r'\s+', ' ', body)[:18000], f'تم تحليل الموقع: {res.url}'
                errors.append(f'{candidate}: بلا نص واضح')
            except Exception as exc:
                errors.append(f'{candidate}: {type(exc).__name__}')

    return '', 'تعذرت زيارة الموقع: ' + ' | '.join(errors[:4])


def _keyword_activity(page_text: str, card_text: str = '') -> str:
    combined = f'{page_text} {card_text}'
    lowered = combined.lower()
    if any(word in lowered for word in ('mining', 'geological', 'wells', 'tunnels')) or any(word in combined for word in ('التعدين', 'المسح الجيولوجي', 'الأنفاق', 'الآبار')):
        return 'أعمال التعدين وقطع الصخور، المسح الجيولوجي، الاستكشاف، حفر الآبار والأنفاق'

    mappings = [
        (('software', 'web development', 'it solutions', 'technology'), 'تطوير البرمجيات وحلول تقنية المعلومات'),
        (('marketing', 'branding', 'advertising', 'social media'), 'التسويق الرقمي وبناء وإدارة العلامات التجارية'),
        (('construction', 'contracting', 'civil works', 'infrastructure'), 'المقاولات والإنشاءات وأعمال البنية التحتية'),
        (('real estate', 'property', 'brokerage'), 'الخدمات العقارية والوساطة وإدارة الأملاك'),
        (('logistics', 'shipping', 'freight', 'transport'), 'الخدمات اللوجستية والشحن والنقل'),
    ]
    for keywords, label in mappings:
        if any(keyword in lowered for keyword in keywords):
            return label
    return ''


def infer_company_activity(company_name: str, website: str, page_text: str = '', card_text: str = '') -> str:
    deterministic = _keyword_activity(page_text, card_text)
    if deterministic:
        return deterministic
    if not getattr(settings, 'ALLOW_GEMINI_WEBSITE_CLASSIFICATION', False):
        return ''

    prompt = f"""
استخرج نشاط الشركة الحقيقي بالعربية من النص المتاح.
أرجع عبارة عربية واحدة فقط من 6 إلى 18 كلمة، بدون شرح.
لا تستخدم عبارات عامة مثل شركة متخصصة أو خدمات متنوعة.
اسم الشركة: {company_name or 'غير معروف'}
الموقع: {website or 'غير معروف'}
نص الموقع: {page_text[:15000] if page_text else 'غير متاح'}
نص الكرت: {card_text[:3000] if card_text else 'غير متاح'}
"""
    try:
        client = genai.Client(api_key=(getattr(settings, 'GEMINI_API_KEYS', []) or [getattr(settings, 'GEMINI_API_KEY', '')])[0])
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=120),
        )
        text = re.sub(r'\s+', ' ', getattr(response, 'text', '') or '').strip().strip('"')
        if len(text) < 20 or text in {'شركة متخصصة', 'خدمات متنوعة', 'غير معروف'}:
            return ''
        return text[:260]
    except Exception:
        return ''


def infer_investment_type(company_name: str, company_activity: str = '', page_text: str = '', card_text: str = '') -> tuple[str, str]:
    combined = ' '.join(filter(None, [company_name, company_activity, page_text[:5000], card_text[:3000]])).lower()
    for investment_type, keywords in INVESTMENT_TYPE_KEYWORDS:
        if any(keyword.lower() in combined for keyword in keywords):
            return investment_type, ''

    if not getattr(settings, 'ALLOW_GEMINI_WEBSITE_CLASSIFICATION', False):
        return 'غير ذلك', ''

    choices = '\n'.join(f'- {choice}' for choice, _ in INVESTMENT_TYPE_KEYWORDS)
    prompt = f"""
اختر نوع الاستثمار الأنسب حصراً من القائمة التالية وبالعربية فقط.
إذا لم يوجد تطابق واضح فأرجع: غير ذلك

{choices}
- غير ذلك

اسم الشركة: {company_name or 'غير معروف'}
نشاط الشركة: {company_activity or 'غير معروف'}
نص الموقع: {page_text[:6000] if page_text else 'غير متاح'}
نص الكرت: {card_text[:3000] if card_text else 'غير متاح'}
"""
    try:
        client = genai.Client(api_key=(getattr(settings, 'GEMINI_API_KEYS', []) or [getattr(settings, 'GEMINI_API_KEY', '')])[0])
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=80),
        )
        text = re.sub(r'\s+', ' ', getattr(response, 'text', '') or '').strip().strip('"')
        valid_choices = [choice for choice, _ in INVESTMENT_TYPE_KEYWORDS] + ['غير ذلك']
        if text in valid_choices:
            return text, ''
    except Exception:
        pass

    return 'غير ذلك', ''
