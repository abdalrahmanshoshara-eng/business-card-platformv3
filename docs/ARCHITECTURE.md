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
├── app/            # صفحات فقط: login, register, profile, admin/users, dashboard, upload
├── features/
│   ├── auth/       # api.ts, AuthProvider.tsx (useAuth), Guard.tsx (RequireAuth)
│   └── users/      # api.ts لإدارة المستخدمين
├── lib/            # api.ts (fetchJson + CSRF + credentials)
└── components/     # PageHero, UserMenu, ...
```

- الصفحات تركّب المكونات فقط؛ منطق المصادقة في `features/auth`.
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
