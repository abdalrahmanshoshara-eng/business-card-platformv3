# تقرير إصلاح Business Card Platform

## ملخص المشاكل التي عولجت

1. `POST /api/cards` كان يفشل أو يرجع شكل response غير متوافق مع صفحة الإضافة اليدوية.
2. الإضافة اليدوية كانت ترسل الصور باسم `front` و `back` بينما backend يحفظ `front_image` و `back_image`.
3. `website` مثل `example.com` كان يمكن أن يسبب 400 قبل التطبيع.
4. أخطاء validation من Django/DRF لم تكن تظهر بوضوح في الواجهة.
5. Gemini كان يدعم قائمة مفاتيح بشكل جزئي فقط بدون runtime disable/cooldown واضح.
6. fallback الخاص بـ Gemini لم يكن يعمل في الحالات المطلوبة لأن `ExtractionError` كان يعاد رميه مباشرة.
7. prompt يحتوي نص عربي مشوه في `investment_type`.
8. تصنيف أخطاء Gemini كان واسعاً وقد يخلط بين invalid JSON و invalid API key.
9. website enrichment كان يمكن أن يستهلك Gemini إضافياً لتصنيف النشاط/نوع الاستثمار.
10. `sequence_number` كان معرضاً لتعارض عند الطلبات المتزامنة تحت Gunicorn.
11. معالجة الصور كانت قد تطبق perspective correction حتى عند كشف غير موثوق.

## الملفات المعدلة

- `backend/config/settings.py`
- `backend/cards/models.py`
- `backend/cards/serializers.py`
- `backend/cards/views.py`
- `backend/cards/services/extractor.py`
- `backend/cards/services/image_processing.py`
- `backend/cards/services/website_enrichment.py`
- `backend/.env.example`
- `backend/.env.server.example`
- `frontend/lib/api.ts`
- `frontend/app/upload/manual/page.tsx`
- `README.md`

## الملفات الجديدة

- `backend/cards/services/gemini_keys.py`
- `FIX_REPORT_AR.md`

## هل أضفت مكتبات جديدة؟

لا. لم تتم إضافة أي dependency جديدة إلى `requirements.txt` أو `package.json`.

## هل أضفت migrations؟

لا. لم أغير schema قاعدة البيانات، لذلك لا توجد migration جديدة مطلوبة.

## كيف يعمل multiple Gemini API keys الآن؟

الإعدادات:

```env
GEMINI_API_KEY=put-your-key-here
GEMINI_API_KEYS=put-key-1-here,put-key-2-here,put-key-3-here
GEMINI_KEY_COOLDOWN_SECONDS=60
GEMINI_MAX_REQUESTS_PER_CARD=3
```

- إذا كانت `GEMINI_API_KEYS` غير فارغة، يتم استخدامها كقائمة.
- إذا كانت فارغة، يتم استخدام `GEMINI_API_KEY` القديم.
- `gemini_keys.py` يدير المفاتيح في runtime memory لكل process.
- عند invalid key يتم تعطيل المفتاح داخل العملية.
- عند quota/rate limit يتم وضع المفتاح في cooldown.
- لا يتم تسجيل المفتاح نفسه نهائياً، فقط `selected_key_index` وسبب الفشل.

## كيف يمنع استهلاك كل المفاتيح بسبب كرت واحد؟

- يوجد حد عام: `GEMINI_MAX_REQUESTS_PER_CARD=3`.
- الطلب الطبيعي يستخدم request واحد يرسل front و back معاً.
- fallback يعمل فقط للحالات القابلة للاسترداد مثل timeout / socket reset / invalid JSON.
- لا يوجد fallback عند quota/rate limit أو invalid key أو location not supported.
- داخل محاولة Gemini الواحدة لا يتم تجربة المفتاح نفسه أكثر من مرة.

## كيف تعمل الإضافة اليدوية الآن؟

`POST /api/cards`:

- يعمل بدون Gemini API key.
- يعمل بدون صور.
- يقبل الصور باسم `front` و `back`.
- يقبل `mobile_numbers` و `emails` كـ JSON array أو نص مفصول بـ `|` أو comma أو أسطر.
- يحول `website` مثل `example.com` إلى `https://example.com` قبل الحفظ.
- يرجع دائماً عند النجاح:

```json
{
  "duplicate": false,
  "saved": true,
  "card": {},
  "message": "تم حفظ الكرت كسجل رقم ..."
}
```

## كيف يتم التعامل مع الكرت المكرر؟

قبل حفظ الإضافة اليدوية يتم فحص:

- email
- phone بعد التنظيف
- website
- company + person
- website + company

إذا وجد duplicate قوي يرجع backend 409:

```json
{
  "detail": "يوجد كرت مشابه بنفس البريد أو رقم الهاتف أو نفس بيانات الشركة/الشخص.",
  "error_type": "duplicate_card",
  "duplicate_conflict": true,
  "duplicate_candidates": []
}
```

الواجهة تعرض الكروت المشابهة وزر "حفظ رغم التكرار". عند الضغط عليه يرسل `confirm_duplicate=true` ويحفظ سجل جديد مع hash مختلف لتجنب unique conflict.

## كيف يعمل تعديل المعلومات؟

`PATCH /api/cards/<id>/` لا يزال يدعم JSON. تم تحسين serializer لقبول:

- `website` كنص قابل للتطبيع.
- `mobile_numbers` و `emails` كقوائم أو strings مفصولة.
- رسائل validation واضحة عبر `fetchJson`.

تعديل النصوص لا يحذف الصور.

## كيف يعمل تعديل الصور؟

`PATCH /api/cards/<id>/` يدعم multipart/form-data. يمكن إرسال:

- `front` فقط.
- `back` فقط.
- الاثنين معاً.

تحديث الصور لا يمسح البيانات النصية.

## رسائل الخطأ الجديدة

أمثلة:

```json
{"detail":"تم الوصول إلى حد استخدام Gemini. يرجى المحاولة لاحقاً.","error_type":"gemini_rate_limit","recoverable":false}
```

```json
{"detail":"موقع استخدام Gemini API غير مدعوم حالياً من هذه الشبكة.","error_type":"gemini_location_not_supported","recoverable":false}
```

```json
{"detail":"لم يتم إعداد مفتاح Gemini API على الخادم.","error_type":"missing_gemini_api_key","recoverable":false}
```

```json
{"detail":"يوجد كرت مشابه بنفس البريد أو رقم الهاتف.","error_type":"duplicate_card","duplicate_conflict":true}
```

## أوامر التشغيل والتحقق

Backend:

```bash
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
```

Docker:

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs backend --tail=100
docker compose logs frontend --tail=100
```

اختبارات يدوية مقترحة:

1. إضافة كرت يدوي بدون صور وبدون Gemini key.
2. إضافة كرت يدوي بموقع مثل `example.com`.
3. إضافة نفس email أو phone مرتين للتأكد من ظهور duplicate warning.
4. الضغط على "حفظ رغم التكرار".
5. تعديل بيانات كرت من Dashboard.
6. تعديل front image فقط.
7. تعديل back image فقط.
8. رفع كرت AI بمفتاح Gemini صالح.
9. تجربة مفتاح invalid والتأكد من ظهور رسالة واضحة.
10. تجربة quota/rate limit والتأكد من عدم تشغيل fallback.

## ما تم تشغيله في هذه البيئة

نجح:

```bash
python -m py_compile backend/cards/models.py backend/cards/serializers.py backend/cards/views.py backend/cards/services/gemini_keys.py backend/cards/services/extractor.py backend/cards/services/image_processing.py backend/cards/services/website_enrichment.py backend/config/settings.py
cd frontend && node node_modules/typescript/bin/tsc --noEmit
```

لم أستطع تشغيل `python manage.py check` هنا لأن Django غير مثبت في بيئة التنفيذ الحالية، والـ `.venv` المرفق داخل المشروع هو بيئة Windows وليست Linux. يجب تشغيل أوامر Django محلياً أو داخل Docker.

## ملاحظات مهمة قبل التشغيل

- لا تضع ملف `.env` الحقيقي داخل Git أو ZIP. استخدم `backend/.env.server.example` لإنشاء `backend/.env` جديد.
- إذا كنت تدخل من IP مثل `172.20.3.94:3000`، أضفه إلى:
  - `ALLOWED_HOSTS`
  - `CORS_ALLOWED_ORIGINS`
  - `CSRF_TRUSTED_ORIGINS`
- تم الإبقاء على Gunicorn timeout في `docker-compose.yml` كما هو: `--timeout 300 --graceful-timeout 300 --log-file -`.
