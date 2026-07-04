# تشغيل اللابتوب كسيرفر محلي للمشروع

## الخيار المعتمد

أفضل تشغيل على اللابتوب هو Docker Compose لأنه يشغل كل شيء معاً:

- PostgreSQL كقاعدة بيانات احترافية بديلة عن SQLite.
- Django Backend على المنفذ `8000`.
- Next.js Frontend على المنفذ `3000`.
- مجلد `backend/media` يبقى محفوظاً على الجهاز خارج الحاويات.
- مجلد `backend/imports` يستخدم لإدخال ملفات Excel إلى حاوية الباك إند.

## البرامج المطلوبة على اللابتوب

### Windows

1. Docker Desktop.
2. WSL2 إذا طلبه Docker Desktop.
3. Git for Windows.
4. محرر كود مثل VS Code.
5. متصفح Chrome أو Edge.

لا تحتاج تثبيت Python أو Node أو PostgreSQL يدوياً إذا ستستخدم Docker.

### macOS / Linux

1. Docker Desktop أو Docker Engine.
2. Git.
3. VS Code اختياري.

## تجهيز ملفات البيئة

انسخ الملفات التجريبية:

```bash
cp backend/.env.server.example backend/.env
cp frontend/.env.server.example frontend/.env.local
```

على Windows PowerShell:

```powershell
Copy-Item backend\.env.server.example backend\.env
Copy-Item frontend\.env.server.example frontend\.env.local
```

افتح `backend/.env` وعدل:

```env
ALLOWED_HOSTS=127.0.0.1,localhost,0.0.0.0,IP_اللابتوب
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://IP_اللابتوب:3000
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://IP_اللابتوب:3000
GEMINI_API_KEY=ضع_المفتاح_الحقيقي_هنا
```

اترك قاعدة البيانات هكذا داخل Docker:

```env
DATABASE_URL=postgres://business_cards:business_cards@postgres:5432/business_cards
```

## معرفة IP اللابتوب

### Windows

```powershell
ipconfig
```

ابحث عن IPv4 ضمن Wi-Fi، مثال:

```text
192.168.1.25
```

### macOS / Linux

```bash
ip addr
```

أو:

```bash
ifconfig
```

## تشغيل المشروع

من جذر المشروع:

```bash
docker compose up --build -d
```

ثم تأكد من حالة الخدمات:

```bash
docker compose ps
```

افتح من اللابتوب:

```text
http://localhost:3000
```

وافتح من الموبايل على نفس شبكة Wi-Fi:

```text
http://IP_اللابتوب:3000
```

مثال:

```text
http://192.168.1.25:3000
```

## تنفيذ migrations

ملف `docker-compose.yml` يشغل migrations تلقائياً عند بدء backend:

```bash
python manage.py migrate --noinput
```

إذا أردت تشغيلها يدوياً:

```bash
docker compose exec backend python manage.py migrate
```

## استيراد Excel القديم

ضع الملف داخل:

```text
backend/imports/cards.xlsx
```

ثم جرب بدون حفظ:

```bash
docker compose exec backend python manage.py import_cards_excel /app/imports/cards.xlsx --dry-run
```

ثم نفذ الاستيراد:

```bash
docker compose exec backend python manage.py import_cards_excel /app/imports/cards.xlsx --clear
```

## فتح الجدار الناري

إذا لم يفتح الموقع من الموبايل:

1. تأكد أن الموبايل واللابتوب على نفس Wi-Fi.
2. اسمح لـ Docker Desktop أو Node/Next.js عبر Windows Firewall على الشبكات الخاصة Private Networks.
3. افتح المنفذ `3000` على اللابتوب.
4. جرب مؤقتاً إيقاف VPN إن وجد.

## أوامر مهمة

إيقاف المشروع:

```bash
docker compose down
```

إيقاف المشروع مع حذف قاعدة البيانات بالكامل:

```bash
docker compose down -v
```

مشاهدة سجلات الباك إند:

```bash
docker compose logs -f backend
```

مشاهدة سجلات الواجهة:

```bash
docker compose logs -f frontend
```

نسخ احتياطي من PostgreSQL:

```bash
docker compose exec postgres pg_dump -U business_cards -d business_cards > backup.sql
```

استعادة نسخة احتياطية:

```bash
docker compose exec -T postgres psql -U business_cards -d business_cards < backup.sql
```

## ملاحظات أمنية

- هذا الإعداد مناسب كسيرفر داخل شبكة Wi-Fi، وليس كاستضافة عامة على الإنترنت.
- لا تنشر `backend/.env` على GitHub.
- إذا كان مفتاح Gemini موجوداً سابقاً داخل `.env` أو داخل ملف مضغوط، قم بتدويره من Google AI Studio واستبدله بمفتاح جديد.
- عند فتح المشروع للإنترنت لاحقاً، استخدم HTTPS وNginx أو استضافة حقيقية وقاعدة بيانات مُدارة.
