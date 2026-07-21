#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# إصدار شهادة HTTPS من Let's Encrypt لأول مرة.
# يُشغَّل مرة واحدة على السيرفر من داخل مجلد المشروع:
#     bash deploy/init-letsencrypt.sh
# الشرط: أن يكون الدومين موجّهاً (DNS A record) إلى IP هذا السيرفر،
#         وأن يكون المنفذان 80 و 443 مفتوحين.
# التجديد بعد ذلك يتم تلقائياً عبر حاوية certbot.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.prod.yml"

# قراءة المتغيّرات من .env في جذر المشروع
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

: "${DOMAIN:?ضع DOMAIN في ملف .env بجذر المشروع}"
: "${CERTBOT_EMAIL:?ضع CERTBOT_EMAIL في ملف .env بجذر المشروع}"

# ضعيه على 1 للاختبار (شهادة تجريبية بلا حدود)، ثم 0 للشهادة الحقيقية
STAGING="${CERTBOT_STAGING:-0}"

domains=("$DOMAIN" "www.$DOMAIN")
cert_path="/etc/letsencrypt/live/$DOMAIN"

echo "### 1) إنشاء شهادة مؤقتة (dummy) كي يقلع Nginx ..."
$COMPOSE run --rm --entrypoint "\
  sh -c 'mkdir -p $cert_path && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout $cert_path/privkey.pem \
    -out $cert_path/fullchain.pem \
    -subj \"/CN=localhost\"'" certbot

echo "### 2) تشغيل Nginx ..."
$COMPOSE up -d nginx

echo "### 3) حذف الشهادة المؤقتة ..."
$COMPOSE run --rm --entrypoint "\
  sh -c 'rm -rf /etc/letsencrypt/live/$DOMAIN \
    /etc/letsencrypt/archive/$DOMAIN \
    /etc/letsencrypt/renewal/$DOMAIN.conf'" certbot

echo "### 4) طلب الشهادة الحقيقية من Let's Encrypt ..."
domain_args=""
for d in "${domains[@]}"; do domain_args="$domain_args -d $d"; done

staging_arg=""
if [ "$STAGING" != "0" ]; then staging_arg="--staging"; fi

$COMPOSE run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $staging_arg \
    $domain_args \
    --email $CERTBOT_EMAIL \
    --rsa-key-size 4096 \
    --agree-tos \
    --no-eff-email \
    --force-renewal" certbot

echo "### 5) إعادة تحميل Nginx بالشهادة الجديدة ..."
$COMPOSE exec nginx nginx -s reload

echo "✅ تم إصدار الشهادة. افتحي: https://$DOMAIN"
