# Business Card Platform

منصة كاملة لإدارة الكروت الشخصية بدل الاعتماد على Excel كقاعدة بيانات.

## الاختيار التقني

- **Frontend:** Next.js responsive، مناسب للموبايل والداشبورد.
- **Backend:** Django + Django REST Framework.
- **Database:**
  - محليًا: SQLite افتراضيًا لتسهيل التشغيل.
  - إنتاجيًا: PostgreSQL، وهو الأنسب للبحث، التوسّع، النسخ الاحتياطي، والاستضافة.
- **AI:** Google Gemini API لاستخراج بيانات الكرت من الصور.
- **Storage:** الصور تُحفظ داخل `backend/media` محليًا. في الإنتاج يمكن نقلها إلى S3 أو Cloudinary.

## الأقسام

1. **قسم الرفع** `/upload`
   - تصوير الوجه الأمامي والخلفي من الموبايل.
   - استخراج البيانات.
   - زيارة الموقع ومحاولة استخراج نشاط الشركة.
   - منع تكرار الكرت قبل حفظه.
   - حفظ السجل تلقائيًا داخل قاعدة البيانات.

2. **قسم العرض والبحث** `/dashboard`
   - عرض كل الكروت.
   - بحث شامل في الاسم، الشركة، الرقم، الإيميل، الموقع، النشاط والنص الخام.
   - فلاتر حسب نشاط الشركة وحالة المراجعة.
   - إحصائيات عامة.
   - تصدير النتائج إلى Excel عند الحاجة، لكن التخزين الأساسي أصبح Database.

## التشغيل المحلي بدون Docker

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

ضع مفتاح Gemini داخل `backend/.env`:

```env
GEMINI_API_KEY=your_real_gemini_key
GEMINI_MODEL=gemini-2.5-flash
```

### Frontend

افتح Terminal آخر:

```bash
cd frontend
copy .env.example .env
npm install
npm run dev
```

افتح:

```text
http://localhost:3000
```

من الموبايل على نفس Wi-Fi افتح:

```text
http://IP-اللابتوب:3000
```

وعدّل `frontend/.env` ليشير إلى IP اللابتوب:

```env
NEXT_PUBLIC_API_BASE_URL=http://IP-اللابتوب:8000/api
```

وعدّل `backend/.env`:

```env
ALLOWED_HOSTS=127.0.0.1,localhost,0.0.0.0,IP-اللابتوب
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://IP-اللابتوب:3000
```

## التشغيل باستخدام Docker

```bash
copy backend\.env.example backend\.env
copy frontend\.env.example frontend\.env
docker compose up --build
```

لتفعيل PostgreSQL في Docker ضع داخل `backend/.env`:

```env
DATABASE_URL=postgres://business_cards:business_cards@postgres:5432/business_cards
```

## الاستضافة المقترحة لاحقًا

- **Render / Railway / Fly.io:** لتشغيل Django API وPostgreSQL.
- **Vercel:** لتشغيل Next.js.
- **Supabase أو Neon:** PostgreSQL جاهز ومدار.
- **Cloudinary أو S3:** تخزين صور الكروت.
- **Google Drive:** مناسب للنسخ الاحتياطي أو تصدير Excel تلقائي، لكنه ليس بديلًا قويًا عن قاعدة بيانات.

## أفكار تطوير إضافية

- تسجيل دخول وصلاحيات مستخدمين.
- صفحة تفاصيل لكل كرت مع تعديل الحقول يدويًا.
- Tags وتصنيف العملاء حسب القطاع أو المدينة.
- كشف تكرار أكثر ذكاءً بتشابه الاسم والشركة وليس فقط الإيميل/الرقم.
- رفع Batch لمجموعة صور دفعة واحدة.
- مزامنة تلقائية مع Google Contacts أو CRM.
- Backup يومي إلى Google Drive بصيغة Excel.

## تحديث الهوية البصرية

تم تعديل واجهة Next.js لتتبع هوية SAMIROCK:
- توب بار داكن مع شعار/اسم سامي روك وعبارة Beyond The Edge.
- لوحة ألوان أسود/أبيض/ذهبي مستوحاة من الكرت.
- أزرار، كروت، جداول، حالات، وإحصائيات بنفس الهوية.
- إصلاح توافق ESLint مع Next.js بتثبيت `eslint@8.57.1`.

إذا كان لديك `node_modules` قديم داخل frontend احذفه ثم أعد التثبيت:

```powershell
cd frontend
Remove-Item -Recurse -Force node_modules
Remove-Item -Force package-lock.json
npm install
npm run dev
```

## إصلاح CORS و favicon

في هذه النسخة تم تعديل الواجهة لتستخدم المسار المحلي `/api` بدل الاتصال المباشر بـ `http://127.0.0.1:8000/api` من المتصفح. Next.js يقوم بتمرير الطلبات إلى Django عبر `next.config.mjs`، وهذا يمنع مشكلة CORS أثناء التطوير المحلي.

بعد التحديث:

Backend:
```powershell
cd backend
python manage.py runserver 0.0.0.0:8000
```

Frontend:
```powershell
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

إذا كان المشروع مفتوحًا أصلًا، أوقف backend و frontend ثم شغلهما من جديد حتى تُقرأ الإعدادات الجديدة.

ملاحظة: رسالة React DevTools في Console ليست خطأ، وهي تظهر طبيعيًا في وضع التطوير.

## تحديث الواجهة المبسطة بالهوية الخضراء

تم تبسيط الواجهة إلى قسمين فقط:

1. `/upload` لرفع صور الكرت وتتبع مراحل العملية.
2. `/dashboard` لعرض جدول البيانات والبحث والتصفية.

تم اعتماد هوية وزارة الاقتصاد والصناعة بالألوان:
- الأخضر الداكن للتوب بار.
- الذهبي للأزرار الأساسية والفواصل.
- الخلفية الكريمية والبطاقات البيضاء.

ملاحظات Console:
- رسالة React DevTools ليست خطأ.
- رسائل `Unchecked runtime.lastError` غالبًا من إضافة في المتصفح وليست من المشروع.
- رسائل Fast Refresh تظهر فقط أثناء التطوير وليست خطأ.


## إصلاح v2: مشكلة redirects عند الرفع

تم إصلاح مشكلة Django التالية:
`You called this URL via POST, but the URL doesn't end in a slash...`

التعديلات:
- توحيد روابط API في الواجهة لإضافة `/` تلقائيًا.
- إضافة مسارات Django تعمل مع slash وبدون slash.
- تعطيل `APPEND_SLASH` لتجنب فقدان بيانات POST.
- التأكد أن `NEXT_PUBLIC_BACKEND_URL` يشير إلى Django فقط: `http://127.0.0.1:8000`.

بعد استبدال النسخة، أوقف السيرفرين وشغلهما من جديد.

## تحديث الموبايل وأرقام الهاتف

- تم إصلاح اتجاه أرقام الهاتف داخل الداشبورد حتى تظهر بصيغة صحيحة مثل `+963930884644` بدل انعكاس الرقم بسبب اتجاه الصفحة RTL.
- أصبحت الأرقام تظهر كأزرار قابلة للضغط من الموبايل، والضغط عليها يفتح الاتصال مباشرة.
- تم تحويل جدول الداشبورد على الشاشات الصغيرة إلى بطاقات responsive مناسبة للموبايل، خصوصًا شاشات مثل Samsung S24 Ultra.
- تم إضافة `suppressHydrationWarning` لتقليل تحذيرات المتصفح الناتجة عن إضافات Chrome التي تضيف attributes مثل `fdprocessedid`.

ملاحظة: رسائل `Unchecked runtime.lastError: The message port closed before a response was received` غالبًا من إضافة في Chrome وليست من التطبيق. جرّب فتح الموقع في Incognito بدون إضافات للتأكد.

## تحديث احترافي: PostgreSQL + استيراد Excel القديم

تمت إضافة مسار عملي لترحيل المشروع من الاعتماد على SQLite/Excel إلى قاعدة PostgreSQL تعمل على اللابتوب كسيرفر محلي عبر Docker Compose.

الملفات المهمة:

- `backend/cards/management/commands/import_cards_excel.py`: أمر Django لاستيراد ملف Excel القديم إلى جدول `BusinessCard`.
- `backend/cards/services/card_data.py`: توحيد تنظيف البيانات وتجهيزها بين API والاستيراد.
- `backend/.env.server.example`: إعدادات backend جاهزة لسيرفر اللابتوب.
- `frontend/.env.server.example`: إعدادات frontend جاهزة لسيرفر اللابتوب.
- `docs/EXCEL_IMPORT_AR.md`: شرح تفصيلي لاستيراد Excel.
- `docs/LAPTOP_SERVER_SETUP_AR.md`: شرح تفصيلي لتشغيل اللابتوب كسيرفر.

أسرع تشغيل:

```bash
cp backend/.env.server.example backend/.env
cp frontend/.env.server.example frontend/.env.local
docker compose up --build -d
```

استيراد Excel:

```bash
docker compose exec backend python manage.py import_cards_excel /app/imports/cards.xlsx --dry-run
docker compose exec backend python manage.py import_cards_excel /app/imports/cards.xlsx --clear
```
