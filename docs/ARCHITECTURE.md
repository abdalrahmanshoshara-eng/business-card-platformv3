# معمارية المنصة (Architecture)

منصة داخلية لأرشفة الكروت الشخصية: **Django + DRF** في الخلفية و**Next.js (App Router) + TypeScript** في الواجهة، تعمل على لابتوب كسيرفر داخل الشبكة المحلية.

## 1. بنية النظام

```
Next.js (frontend)  ──HTTP + Session Cookie──▶  Django REST (backend)  ──▶  DB (SQLite/PostgreSQL)
                                                                        └──▶  Gemini / Websites (Infra)
```

- Backend: **Modular Monolith** — تطبيقات Django مستقلة (`accounts`، `cards`) داخل مشروع واحد.
- Frontend: **Feature-Based** — `features/` للمنطق، `app/` لتركيب الصفحات، `lib/` و`components/` للمشترك.
- المصادقة: **Django Session Authentication** (Cookie) مع CSRF.

## 2. الوحدات (Modules)

- `config/` — إعدادات المشروع، الـURLs الرئيسية، الـmiddleware.
- `accounts/` — المستخدمون والمصادقة وإدارة المستخدمين (لا يحتوي models؛ يستخدم `django.contrib.auth.User`).
- `cards/` — نموذج الكرت، الـViewSet، الخدمات (services)، أوامر الإدارة، والاختبارات.

## 3. مسؤولية الطبقات

- **View / ViewSet**: يستقبل الطلب، يتحقق من الصلاحيات، يستدعي Serializer/Service، ويعيد Response فقط.
- **Serializer**: يتحقق من المدخلات والمخرجات ويطبّع الحقول (email l/trim، website). لا يحتوي منطق أعمال.
- **Service / Use Case**: منطق الأعمال (كشف التكرار، عزل الملكية، أمان الصور/Excel، زيارة المواقع).
- **Model**: البنية والقيود وثبات البيانات (`sequence_number`، `duplicate_hash` فريد لكل مالك).

تدفق الكتابة: `ViewSet → Serializer → Service → Model`.

خدمات `cards/services/`:
- `access.py` — `cards_for_user(user)` قاعدة العزل حسب الملكية.
- `duplicates.py` — كشف/تسجيل التكرار (مستخرَج من الـViewSet).
- `security.py` — تعقيم Excel، التحقق من الصور (MIME/الحجم/المحتوى)، منع SSRF.
- `card_data.py`, `normalization.py`, `natural_search.py` — تحضير وبحث البيانات.
- **Infrastructure Services**: `extractor.py` (Gemini)، `website_enrichment.py` (زيارة المواقع)، تصدير Excel داخل الـViewSet.

## 4. تدفق الطلب (مثال إنشاء كرت)

`POST /api/cards` → `BusinessCardViewSet.create` → Serializer validate → تحقق الصور → `find_duplicate_candidates(scoped)` → `serializer.save(owner=request.user)`.

## 5. المصادقة

- Session Authentication عبر Cookie من نوع **HttpOnly**، مع **CSRF** (رأس `X-CSRFToken`).
- تسجيل الدخول (`login()`) يدوّر مفتاح الجلسة؛ الخروج (`logout()`) ينهيها.
- تسجيل الدخول يقبل **username أو email** (case-insensitive) عبر `accounts/backends.py`.
- Cookies: `SameSite=Lax`. `Secure` يُضبط عبر `COOKIE_SECURE` (True خلف HTTPS، False على HTTP الداخلي).
- Endpoints تحت `/api/auth/`: `register`، `login`، `logout`، `me`، `profile`، `change-password`، `forgot-password`، `reset-password`، و`csrf`.
- Rate limiting (ScopedRateThrottle) على login/register/forgot.

## 6. الصلاحيات (Admin / User)

- **Admin** = `is_staff` أو `is_superuser`: يرى كل المستخدمين وكل الكروت، ينشئ/يفعّل/يعطّل المستخدمين، يصدّر الكل.
- **User**: يرى ويدير كروته فقط، ويعدّل ملفه ويغيّر كلمة مروره.
- افتراضياً `IsAuthenticated` على كل الـEndpoints (DRF default). إدارة المستخدمين محمية بـ`accounts/permissions.py::IsAdmin`.
- المستخدم لا يستطيع تعديل `is_staff/is_superuser` أو تحديد `owner` — تُتجاهل هذه الحقول من المدخلات.

## 7. عزل الكروت حسب المستخدم

كل العمليات (list/retrieve/create/update/delete/search/stats/export/duplicate/image) تمر عبر `cards_for_user`:

```python
if user.is_staff or user.is_superuser:
    qs = BusinessCard.objects.all()
else:
    qs = BusinessCard.objects.filter(owner=user)
```

الوصول المباشر لكرت مستخدم آخر يُعيد 404. `duplicate_hash` فريد **لكل مالك** (`UniqueConstraint(owner, duplicate_hash)`) حتى لا يُكشف تكرار يملكه غيرك. المالك يُؤخذ دوماً من `request.user`.

## 8. تنظيم Frontend

```
frontend/
├── app/            # صفحات فقط: login, profile, admin/users, dashboard, upload
├── features/
│   ├── auth/       # api.ts, AuthProvider.tsx (useAuth), Guard.tsx (RequireAuth)
│   └── users/      # api.ts لإدارة المستخدمين
├── lib/            # api.ts (fetchJson + CSRF + credentials)
└── components/     # SiteHeader, PageHero, UserMenu, ...
```

- الصفحات تركّب المكونات فقط؛ منطق المصادقة في `features/auth`.
- **لا يوجد تسجيل ذاتي**: صفحة `register` أُزيلت والحسابات يُنشئها المشرف. Endpoint الـBackend ما زال موجوداً لكنه مغلق بـ`PUBLIC_REGISTRATION_ENABLED=false`.
- `/login` شاشة كاملة بعمودين (نموذج + لوحة هوية تحمل الشعار)؛ لذلك `SiteHeader` يُخفي الشريط العلوي على هذا المسار فقط (`BARE_ROUTES`). أنماطها في القسم 21 من `globals.css`.
- طلبات API تمر عبر `lib/api.ts` (يرسل الكوكيز و`X-CSRFToken`).
- الحماية عبر `RequireAuth`/`RequireAuth admin` مع حالة تحميل وإعادة توجيه. الحماية الأساسية في الـBackend.
- **ممنوع** تخزين بيانات المصادقة في `localStorage/sessionStorage`.

## 9. إضافة Feature جديدة (Frontend)

أنشئ مجلداً تحت `features/<name>/` (api.ts + مكونات)، ثم صفحة رقيقة تحت `app/<route>/page.tsx` تستدعيه. أضف اختباراً عند وجود بنية اختبار.

## 10. إضافة API جديد (Backend)

1. المنطق في `cards/services/` أو تطبيق جديد.
2. Serializer للتحقق.
3. View/Action رقيقة تستدعي الخدمة وتطبّق الملكية عبر `cards_for_user`.
4. أضف المسار في `urls.py` (مع alias بدون slash عند الحاجة لأن `APPEND_SLASH=False`).

## 11. إضافة Migration

```
python manage.py makemigrations
python manage.py migrate
python manage.py makemigrations --check --dry-run   # للتحقق
```

لا تعدّل migration قديمة؛ أنشئ واحدة جديدة. تغييرات المخطط الحسّاسة تُنفَّذ على مراحل (كما في إضافة `owner` القابل لـnull ثم الإسناد).

## 12. قواعد الاختبارات

- Backend: `python manage.py test cards accounts`. كل Feature جديدة تحتاج اختباراً.
- تغطية أساسية: تسجيل الدخول (username/email)، العزل، الملكية، الصلاحيات، حماية الصور، كشف التكرار.
- Frontend: `npx tsc --noEmit` ثم `npm run build`.

## 13. أين لا يوضع Business Logic

- ليس في **Views/ViewSets** (تنسيق فقط)، ولا في **Serializers** (تحقق فقط)، ولا في **صفحات Next.js/المكونات**، ولا داخل **Migrations**. المكان الصحيح: `services/` (Backend) و`features/` (Frontend).

## 14. إعدادات التشغيل (داخلي/إنتاجي)

- **داخلي (HTTP)**: `DEBUG=true` أو proxy؛ `COOKIE_SECURE=false`؛ `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` محدّدة بعنوان اللابتوب؛ Email = console backend.
- **إنتاجي (HTTPS خلف reverse proxy)**: `COOKIE_SECURE=true`، `DEBUG=false`، `SECRET_KEY` قوي، `ALLOWED_HOSTS` صحيح، قاعدة PostgreSQL عبر `DATABASE_URL`، SMTP عبر `EMAIL_*`.
- `PUBLIC_REGISTRATION_ENABLED=false` افتراضياً (منصة داخلية).

## 15. نقل الكروت القديمة (Legacy)

الكروت بلا مالك تظهر للـAdmin فقط. لإسنادها:

```
python manage.py assign_legacy_cards --username admin      # أو تلقائياً إن وُجد superuser واحد
python manage.py assign_legacy_cards --dry-run             # معاينة دون كتابة
```

لا يحذف الأمر أي كرت أو صورة.

## 16. مسار استخراج الكروت عبر Gemini (المحسّن)

### 16.1 رفع الصور
- الواجهة: `frontend/app/upload/page.tsx`. الوجه الأمامي **إلزامي**، الخلفي **اختياري**. زر استخراج واحد، معطّل أثناء الطلب، مع حارس `inFlightRef` لمنع الإرسال المزدوج (بما في ذلك React StrictMode).
- الواجهة تولّد **idempotency key** ثابتاً لكل محاولة وترسله في ترويسة `X-Idempotency-Key` وحقل `idempotency_key`.
- الـEndpoint: `POST /api/cards/extract` (`BusinessCardViewSet.extract`).

### 16.2 المعالجة المسبقة للصور
- `cards/services/image_processing.py`. تصحيح اتجاه EXIF، كشف حدود البطاقة وتصحيح المنظور بشكل محافظ (OpenCV مع fallback إلى PIL)، تصغير للضلع الأطول (بدون تكبير)، إزالة metadata، وحفظ JPEG بجودة قابلة للضبط مع سقف أعلى لحجم الملف (إعادة ضغط تلقائية حتى السقف دون النزول عن جودة 55).
- الإعدادات: `GEMINI_CARD_IMAGE_MAX_DIMENSION` (افتراضي 1800)، `GEMINI_CARD_IMAGE_QUALITY` (82)، `GEMINI_CARD_IMAGE_MAX_BYTES`.
- النسخة الأصلية المرفوعة تُحفظ كما هي على الكرت؛ المعالجة تُطبَّق على نسخة مؤقتة تُرسل إلى Gemini فقط.

### 16.3 منع التكرار (Idempotency)
- نموذج `ExtractionRequest` يحمل `(owner, idempotency_key)` **فريداً**، وبصمة `image_fingerprint` = SHA‑256 لمحتوى الوجه الأمامي (+ الخلفي إن وُجد) + `EXTRACTION_SCHEMA_VERSION`.
- الحالات: `pending → processing → completed | failed`، والانتقال ذرّي داخل `transaction.atomic()` مع `select_for_update`.
- الطلب المكرر بنفس المفتاح: أثناء `processing` يُعاد 202 دون استدعاء Gemini؛ بعد `completed` يُعاد الناتج المخزَّن (`result`).
- الصور المتطابقة بايت‑ببايت (بأي مفتاح) تُعيد استخدام ناتج سابق مكتمل عبر البصمة دون استدعاء جديد.
- طلب `processing` قديم (> `EXTRACTION_PROCESSING_STALE_SECONDS`) يُعاد استخدامه (worker متعطّل). لا يوجد اعتماد على حالة في الذاكرة.

### 16.4 استدعاء Gemini (طلب واحد + Structured Output)
- `cards/services/extractor.py`. **استدعاء واحد فقط** يرسل الوجه (أو الوجهين معاً) في نفس الطلب — لا استدعاء لكل وجه ولا استدعاء دمج ثالث.
- **Structured Output حقيقي**: `response_schema=BusinessCardData` مع `response_mime_type='application/json'`. تُقرأ `response.parsed` أولاً ثم fallback إلى نص JSON، وتُعاد المصادقة عبر pydantic دائماً؛ أي مفاتيح غير متوقعة تُسقَط، والاستجابة غير المطابقة تُرفض بلا إنشاء كرت.
- ضبط التكلفة: `temperature=GEMINI_CARD_TEMPERATURE` (0)، `max_output_tokens=GEMINI_CARD_MAX_OUTPUT_TOKENS`، و`thinking_config.thinking_budget=GEMINI_CARD_THINKING_BUDGET` (0 = تعطيل التفكير لموديلات 2.5).
- تعدد مفاتيح `GEMINI_API_KEYS` في `gemini_keys.py` بـ**أولوية صارمة**: يُستخدم المفتاح الأول دائماً، ولا يُنتقل إلى التالي إلا إذا كان الأول **غير صالح** (يُعطَّل) أو **متجاوزاً للحد/الحصة 429** (تهدئة `GEMINI_KEY_COOLDOWN_SECONDS`)، أو جُرِّب في نفس الطلب. الأخطاء المؤقتة (503/timeout) لا تبدّل المفتاح بل يُعاد المحاولة عليه. عند نفاد كل المفاتيح تُعاد رسالة خطأ واضحة.

### 16.5 إدارة الأخطاء وإعادة المحاولة
- إعادة المحاولة للأخطاء المؤقتة فقط (`gemini_timeout`, `gemini_transient`, `extraction_parse_error`, `gemini_external_error`) بـ exponential backoff + jitter، محدودة بـ`GEMINI_CARD_MAX_RETRIES`.
- الأخطاء الدائمة (مفتاح غير صالح، صورة تالفة، permission denied) لا يُعاد استدعاؤها. لا تُعرض أخطاء Gemini الخام للمستخدم، ولا تُسجَّل المفاتيح أو الصور.

### 16.6 تسجيل الاستهلاك والتكلفة
- نموذج `GeminiUsageLog` + `cards/services/usage.py` (`log_gemini_usage`) يسجّل صفاً لكل عملية باستخدام **usage metadata الحقيقية** (input/output/total/thoughts/cached tokens)، مع `operation_type` (`card_extraction` / `website_enrichment`)، `request_count`، `retry_number`، `latency_ms`، والحالة.
- التكلفة تقديرية عبر `cards/services/pricing.py` باستخدام **Decimal** والأسعار المركزية في `settings.GEMINI_PRICING`. عند غياب metadata تُخزَّن التكلفة `NULL` مع `cost_note`. فشل حساب/تسجيل التكلفة **لا** يمنع حفظ الكرت.
- ملخص في لوحة إدارة `GeminiUsageLog` (استدعاءات اليوم، كروت، توكنات، تكلفة اليوم/الشهر، متوسط الكرت، الفاشلة، إعادات المحاولة، وفصل تكلفة الإثراء عن الاستخراج).
- **تنبيه**: هذه تكلفة تقديرية مبنية على metadata والأسعار المضبوطة، وليست الفاتورة النهائية من Google.

### 16.7 إثراء موقع الشركة (اختياري ومنفصل)
- **لا يبدأ تلقائياً** أثناء الاستخراج. Endpoints: `POST /api/cards/{id}/enrich` (مع `refresh=true` لإعادة التحديث) و`GET /api/cards/{id}/enrichment`.
- **خيار وقت الاستخراج**: يرسل المستخدم `visit_website=1` مع طلب `extract` ليطلب زيارة الموقع أثناء الاستخراج؛ يُملأ `company_activity` من نتيجة الإثراء إن كان فارغاً. إذا **لم تُطلب** الزيارة (أو بقي النشاط غير محدد) ونشاط الشركة غير معروف من الكرت، يُضبط `needs_review=True` ويُضاف `company_activity` إلى `review_fields`. الخيار جزء من بصمة الصورة، فتغييره على نفس الصورة يُنشئ عملية مستقلة.
- `cards/services/enrichment.py` يجلب صفحات محدودة (رئيسية/About/Services) عبر `website_enrichment.fetch_website_text` مع حماية **SSRF** (`security.is_public_http_url`: HTTP/HTTPS فقط، حجب loopback/private/link‑local/metadata)، ثم يستدعي Gemini باستخدام structured output ويسجّل الاستهلاك.

### 16.8 تخزين الإثراء حسب النطاق (Domain Cache)
- نموذج `CompanyDomainEnrichment` مفتاحه `canonical_domain` **فريد**.
- **قرار النطاق**: التخزين حسب **registered domain (eTLD+1)** عبر `tldextract` (مثال: `www.example.com` و`careers.example.com` → `example.com`). النتيجة **مشتركة على مستوى النظام** لأن بيانات موقع الشركة عامة وغير حسّاسة، فيُحلَّل الموقع مرة واحدة لكل الموظفين. (`cards/services/domains.py`).
- قبل التحليل يُبحث عن نتيجة ناجحة غير منتهية (`is_fresh()` عبر `refresh_after` = الآن + `WEBSITE_ENRICHMENT_TTL_DAYS`) وتُعاد دون Gemini. تغيّر المحتوى يُكتشف عبر `content_hash`.
- **قفل** لمنع التحليل المتوازي لنفس النطاق: `status=processing` + `locked_at` داخل `transaction.atomic()`؛ قفل قديم (> `LOCK_STALE_SECONDS`) قابل للاسترجاع.

### 16.9 أماكن الإعدادات وتحديث الأسعار
- كل إعدادات المسار مركزية في `config/settings.py` (كتلة "Card extraction tuning" و`GEMINI_PRICING`) وموثّقة في `backend/.env.example`. **لا** توضع مفاتيح API في الكود أو الواجهة.
- **تحديث أسعار موديل**: عدّل `_DEFAULT_GEMINI_PRICING` في `settings.py` أو مرّر `GEMINI_PRICING_JSON` (USD لكل مليون توكن، input/output). الأسعار قابلة للتعديل ولا تُفترض ثابتة.

### 16.10 تشغيل الاختبارات
```
cd backend
python manage.py test cards                     # يشمل cards/tests_pipeline.py
python run_checks.py makemigrations --check --dry-run
cd ../frontend && npx tsc --noEmit
```
اختبارات المسار في `cards/tests_pipeline.py` تُموّه Gemini بالكامل (لا تستهلك رصيداً) وتؤكد عدد استدعاءات Gemini الفعلي.

## 17. رسالة الترحيب (Welcome Email)

عند إضافة كرت جديد يمكن لليوزر إرسال رسالة ترحيب **بضغطة زر واحدة** من **بريده الخاص** إلى بريد الكرت.

### 17.1 الإعداد: بريد المُرسِل ونصّ الرسالة (كلاهما لكل يوزر)
كل حساب يملك رسالته: يبدأ على الخطاب الرسمي المعتمد، وله أن يعدّله كما يشاء أو يعيده إليه في أي وقت. تعديل حساب لا يمسّ رسائل أي حساب آخر.

- **بريد المُرسِل** في `Profile.sender_email`. الحفظ عبر `PATCH /api/auth/profile`، وهو الحقل الوحيد المسموح به هناك — إرسال حقول النصّ عبر هذا الـendpoint **يُرفض بـ400** لا يُتجاهل، كي لا يظنّ عميل قديم أنه حفظ نصًّا. `has_welcome_config()` = **بريد المُرسِل مضبوط** (النصّ له افتراضي دائمًا).
- **نصّ الرسالة** في `WelcomeLetter` (`accounts/models.py`) — **صف واحد لكل يوزر** (`OneToOneField` مع `CASCADE`، فيُحذف مع صاحبه)، فيه `subject_ar`/`body_ar`/`subject_en`/`body_en`. `load(user)` تُعيد كائنًا **غير محفوظ** لمن لم يخصّص، فقراءة النصّ أثناء الإرسال لا تكتب في قاعدة البيانات.
- **الصف موجود فقط عند التخصيص**: حقل فارغ = القالب المعتمد لتلك اللغة من `accounts/welcome_templates.py`. لذلك **إعادة الضبط تحذف الصف** ولا تنسخ القالب داخله، **وإفراغ كل الحقول عبر PATCH يعادل إعادة الضبط** (`reset_for`) بدل تثبيت صف من نصوص فارغة — فتبقى الرسالة متتبِّعة للقالب، وأي تصحيح لاحق عليه يصل كل من لم يخصّص.
- **الـEndpoints** (كلها لأي يوزر مسجَّل، ومحصورة بـ`request.user` فلا يقرأ حساب نصّ غيره ولا يعدّله): `GET`/`PATCH /api/auth/welcome-letter` و`POST /api/auth/welcome-letter/reset`. الاستجابة تحوي النصّ الفعّال + `is_customized` + `can_edit_letter` (دائمًا true) + `can_test_send` (**للمشرف فقط**).
- **اختبار الإرسال بقي للمشرف** (`IsAdmin` + throttle): يرسل إلى **عنوان اعتباطي**، وهو تشخيص لإعدادات بريد المنصة لا جزء من ملكية المستخدم لرسالته — فتحه للجميع يجعله قناة إرسال غير مقيّدة.
- **الواجهة**: للرسالة **صفحة مستقلة** `app/welcome-letter/page.tsx` ببند خاص في السايدبار («رسالة الترحيب»). تحوي «نصّ الرسالة» بحقوله الأربعة قابلة للتعديل لكل مستخدم + «حفظ» + **«إعادة الضبط للنصّ الرسمي»** بتأكيد صريح (معطَّل إن كانت الرسالة على الافتراضي أصلًا)، وبطاقة «اختبار الإرسال» تظهر عند `can_test_send` فقط. بديلًا عن صفحة `/welcome-test` التي أُزيلت ودُمجت هنا.
- **البروفايل** (`app/profile/page.tsx`): بطاقة «بريد المُرسِل» وحدها، مع رابط إلى صفحة الرسالة.
- **الأعمدة القديمة**: `Profile.welcome_subject`/`welcome_message` باقية بلا استخدام (كأعمدة `smtp_*`) تفاديًا لـmigration حذفي على بيانات موجودة. Migrations: `accounts/0004` (تفريغ الافتراضي القديم)، `0005` (إنشاء `WelcomeLetter` وحذف عمودَي اللغة الثانية اللذين لم يُنشرا قط)، `0006` (تحويل `WelcomeLetter` إلى صف لكل يوزر؛ يحذف صف «المنصة» السابق لأنه بلا معنى في الشكل الجديد — ومَن لا صفّ له يرسل الخطاب الرسمي، وهو ما كانت إعادة الضبط ستنتجه على أي حال).

### 17.2 مسار الإرسال (نافذة منبثقة + زر الجدول)
- **بعد استخراج كرت جديد فيه بريد**: تظهر نافذة وسط الشاشة (`components/WelcomePrompt.tsx`):
  - إن كان بريد المُرسِل مضبوطًا → «إرسال ترحيب» (أخضر) / «إلغاء».
  - إن لم يكن مضبوطًا → رسالة توضيحية مع «تعيين الإيميل الآن» (أخضر، ينقل إلى `/profile`) / «تجاهل».
- **جدول الكروت** (`app/dashboard`): عمود «الترحيب» لكل كرت — `تم الترحيب ✓` (أخضر) / `فشل الترحيب` (أحمر) / `إرسال ترحيب`. الضغط: إن كان مضبوطًا يُرسل مباشرةً ويحدّث الحالة؛ وإلا تظهر نافذة «تعيين الإيميل».
- الـEndpoint: `POST /api/cards/{id}/send-welcome`. يتحقق من الملكية (404 لغير المالك)، اكتمال الإعدادات (بريد المُرسِل، وإلا `welcome_not_configured`)، ووجود بريد على الكرت. مرة واحدة: `sent` يُعيد `already_sent` ما لم يُمرَّر `resend=true`.
- **الإرسال دائمًا من إيميل واحد للمنصة** (`settings.WELCOME_FROM_EMAIL` عبر `EMAIL_*`)، مع بريد اليوزر كاسم عرض في `From` وReply‑To. الحالة على الكرت: `welcome_status`/`welcome_sent_at`/`welcome_sent_to`/`welcome_error`.
- **زيارة الموقع**: أصبح الاستخراج **يزور موقع الشركة دائمًا** (بلا خيار) لتحديد النشاط؛ إن بقي النشاط غير محدد يُوسم الكرت «يحتاج مراجعة».

### 17.3 لغة الرسالة والتحية (`cards/services/welcome_text.py`)
- **لغات الكرت**: حقل `printed_languages` على `BusinessCard` يملؤه الاستخراج ضمن نداء Gemini نفسه (بلا نداء إضافي). للكروت القديمة يُستنتج من الحروف في نصّ الكرت.
- **قاعدة الإرسال**: العربية أساسية وتظهر دائمًا، وتليها لغة الكرت إن لم تكن عربية — **في بريد واحد**، العربية أولًا. كرت عربي ⇐ العربية وحدها؛ كرت ألماني ⇐ العربية + الألمانية.
- **التحية**: `salutation_ar` / `salutation_en` / `salutation_native` على الكرت، يولّدها الاستخراج مراعيةً الرتبة واللقب والجنس ونوع الجهة (شخص/شركة/سفارة/وزارة). الترتيب عند الإرسال: التحية المولَّدة ← قاعدة برمجية من اسم الجهة/الشخص ← «السادة الضيوف الكرام،». موضعها في النصّ هو الرمز `{{salutation}}`؛ حذفُه من نصّ مخصّص يعني إرساله حرفيًا بلا تحية. وكضمانة أخيرة يستبدل `send_welcome_email` أي رمز متبقٍّ بالتحية العامة، فلا يخرج بريد يحمل الرمز الخام مهما فشل ما قبله.
- **نصّ كل لغة** بالترتيب: نصّ مالك الكرت (`WelcomeLetter`) ← القالب المعتمد للغة (عربي/إنكليزي/فرنسي/ألماني/تركي/روسي/إسباني/صيني) ← ترجمة مخزَّنة في `WelcomeTranslation` عبر Gemini (مرة واحدة لكل لغة، `cards/services/welcome_translate.py`) ← النصّ الإنكليزي. **لا تُرسل رسالة فارغة أبدًا.**
- `manage.py backfill_card_salutations` يملأ اللغات والتحيّات للكروت القديمة دفعةً واحدة (10 كروت لكل نداء)، وهو آمن للتكرار.
- ترجمات القوالب غير العربية/الإنكليزية أُنشئت لهذه المنصة و**تحتاج مراجعة ناطق باللغة** قبل الاعتماد؛ الأصل العربي والإنكليزي من الوزارة.

### 17.4 التصميم البصري للبريد
بريد HTML رسمي (`_welcome_html`): شريط علوي أخضر بشعار الوزارة المضمَّن عبر CID من `accounts/assets/welcome-logo.png`، فاصل ذهبي، ثم **كتلة لكل لغة** (عنوانها هو عنوان الرسالة بتلك اللغة، واتجاهها RTL/LTR حسبها) يفصل بينها خط، ثم كتلة «مُرسَلة من: بريد اليوزر»، وتذييل الوزارة (يصبح ثنائي اللغة عند وجود كتلة لاتينية). نسخة نصية بديلة للعملاء بلا HTML. (ملاحظة: الشعار المضمّن عبر CID قد يظهر لدى بعض العملاء كمرفق `logo.png` قابل للتحميل وعند الرد؛ هذا سلوك متأصّل في الصور المضمّنة.)

### 17.5 الاختبارات
`cards/tests_welcome.py` + `cards/tests_pipeline.py` (بريد وGemini مموّهان): حفظ الإعدادات، إرسال ناجح من عنوان المنصة مع الشعار (CID) والاسم/Reply‑To، منع التكرار، الملكية، رفض مستلم خارج الكرت، قصر «اختبار الإرسال» على الأدمِن، زيارة الموقع دائمًا وملء النشاط، ووسم المراجعة عند غياب النشاط، إضافةً إلى: لغة الكرت (عربي وحده / عربي+إنكليزي / عربي+ألماني من القالب بلا نداء ترجمة / لغة بلا قالب تُترجَم مرة واحدة / فشل الترجمة يعود للإنكليزي)، والتحية (المولَّدة، لكل لغة تحيتها، الاحتياطية بالقواعد، والنصّ المخصّص بلا رمز يُرسل حرفيًا)، وملكية النصّ (أي يوزر يعدّل نصّه ويرسله، ونصّ حساب لا يتسرّب إلى مستلمي حساب آخر، وحذف اليوزر يحذف نصّه، وإفراغ الحقول = إعادة ضبط)، وإعادة الضبط (تُرجع الافتراضي، تحذف الصف، متكرّرة بلا أثر جانبي، ولا تمسّ نصّ غير صاحبها)، وضمانة عدم خروج الرمز الخام حتى عند فشل بناء الكتل.
