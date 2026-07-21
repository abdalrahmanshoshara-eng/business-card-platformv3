#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# نقل المشروع من جهازك إلى السيرفر (الكود + صور الكروت + نسخة قاعدة البيانات).
# يُشغَّل من جهازك أنتِ (وليس السيرفر)، من داخل مجلد المشروع.
#
# على ويندوز: شغّليه داخل Git Bash أو WSL (لأنه يحتاج rsync/scp).
#   bash deploy/migrate-to-server.sh
#
# عدّلي القيم التالية أولاً حسب إعدادات SSH التي أُعطيت لك 👇
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── إعدادات الاتصال (عدّليها) ────────────────────────────────────────────────
SERVER_USER="root"                 # اسم المستخدم على السيرفر
SERVER_HOST="123.45.67.89"         # IP السيرفر أو الدومين
SERVER_PORT="22"                   # منفذ SSH
SSH_KEY=""                         # مسار المفتاح الخاص إن وُجد، مثال: ~/.ssh/id_rsa (اتركيه فارغاً لكلمة المرور)
REMOTE_DIR="/opt/business-card-platform"   # مكان المشروع على السيرفر

# ── قاعدة البيانات المحلية (كما في docker-compose.yml) ────────────────────────
LOCAL_DB_NAME="business_cards"
LOCAL_DB_USER="business_cards"
# ─────────────────────────────────────────────────────────────────────────────

SSH_OPTS="-p $SERVER_PORT"
if [ -n "$SSH_KEY" ]; then SSH_OPTS="$SSH_OPTS -i $SSH_KEY"; fi
RSYNC_SSH="ssh $SSH_OPTS"
REMOTE="$SERVER_USER@$SERVER_HOST"

echo "════════════════════════════════════════════"
echo "  1/4  أخذ نسخة من قاعدة البيانات المحلية"
echo "════════════════════════════════════════════"
DUMP="db_dump_$(date +%Y%m%d_%H%M%S).sql"
if docker compose ps postgres >/dev/null 2>&1 && \
   docker compose exec -T postgres pg_isready -U "$LOCAL_DB_USER" >/dev/null 2>&1; then
  echo "→ أخذ نسخة حيّة من حاوية postgres المحلية ..."
  docker compose exec -T postgres pg_dump -U "$LOCAL_DB_USER" -d "$LOCAL_DB_NAME" --clean --if-exists > "$DUMP"
else
  echo "⚠ حاوية postgres المحلية غير مشغّلة."
  if [ -f backup_before_reassign.sql ]; then
    echo "→ سأستخدم النسخة الجاهزة backup_before_reassign.sql بدلاً منها."
    cp backup_before_reassign.sql "$DUMP"
  else
    echo "✗ لا توجد نسخة قاعدة بيانات. شغّلي docker compose up -d postgres محلياً ثم أعيدي المحاولة."
    exit 1
  fi
fi
echo "✓ النسخة: $DUMP"

echo "════════════════════════════════════════════"
echo "  2/4  إنشاء المجلد على السيرفر"
echo "════════════════════════════════════════════"
$RSYNC_SSH "$REMOTE" "mkdir -p '$REMOTE_DIR'"

echo "════════════════════════════════════════════"
echo "  3/4  رفع الكود (بدون الملفات الثقيلة والأسرار)"
echo "════════════════════════════════════════════"
rsync -avz --delete -e "$RSYNC_SSH" \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/.next' \
  --exclude 'backend/.venv' \
  --exclude '**/__pycache__' \
  --exclude 'backend/db.sqlite3' \
  --exclude '*.log' \
  --exclude '.env' \
  --exclude 'backend/.env' \
  --exclude 'frontend/.env.local' \
  --exclude 'backend/media' \
  ./ "$REMOTE:$REMOTE_DIR/"

echo "→ رفع صور الكروت (media) ..."
rsync -avz -e "$RSYNC_SSH" backend/media/ "$REMOTE:$REMOTE_DIR/backend/media/"

echo "→ رفع نسخة قاعدة البيانات ..."
rsync -avz -e "$RSYNC_SSH" "$DUMP" "$REMOTE:$REMOTE_DIR/$DUMP"

echo "════════════════════════════════════════════"
echo "  ✅ 4/4  اكتمل الرفع"
echo "════════════════════════════════════════════"
cat <<EOF

الخطوات التالية على السيرفر (عبر SSH):

  ssh $SSH_OPTS $REMOTE
  cd $REMOTE_DIR

  # 1) جهّزي ملفات البيئة (مرة واحدة)
  cp deploy/env-root.example       .env               && nano .env
  cp deploy/env-backend.example    backend/.env       && nano backend/.env
  cp deploy/env-frontend.example   frontend/.env.local

  # 2) ابني وشغّلي كل الخدمات
  docker compose -f deploy/docker-compose.prod.yml up -d --build

  # 3) حمّلي قاعدة البيانات المنقولة
  bash deploy/load-database.sh $DUMP

  # 4) أصدري شهادة HTTPS (بعد توجيه الدومين للسيرفر)
  bash deploy/init-letsencrypt.sh

EOF
