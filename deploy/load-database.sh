#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# تحميل نسخة قاعدة البيانات المنقولة داخل حاوية postgres على السيرفر.
# يُشغَّل على السيرفر من داخل مجلد المشروع:
#     bash deploy/load-database.sh db_dump_XXXX.sql
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

DUMP="${1:?مرّري اسم ملف النسخة، مثال: bash deploy/load-database.sh db_dump_20260720.sql}"
COMPOSE="docker compose -f deploy/docker-compose.prod.yml"

if [ -f .env ]; then set -a; . ./.env; set +a; fi
DB_USER="${POSTGRES_USER:-business_cards}"
DB_NAME="${POSTGRES_DB:-business_cards}"

echo "→ انتظار جاهزية قاعدة البيانات ..."
until $COMPOSE exec -T postgres pg_isready -U "$DB_USER" >/dev/null 2>&1; do
  sleep 2
done

echo "→ تحميل $DUMP إلى قاعدة البيانات $DB_NAME ..."
$COMPOSE exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" < "$DUMP"

echo "→ تطبيق أي هجرات (migrations) ناقصة ..."
$COMPOSE exec -T backend python manage.py migrate --noinput

echo "✅ تم تحميل قاعدة البيانات بنجاح."
echo "   لإنشاء مستخدم إدارة (اختياري): $COMPOSE exec backend python manage.py createsuperuser"
