"""Fill printed_languages and salutations on cards extracted before those
fields existed.

New cards get both from the extractor, inside the Gemini call that already runs
per card. Legacy cards have neither, so their welcome email falls back to a
rule-based salutation that has to guess at gender and rank. This command asks
the model to write them properly, in batches, from the text already stored on
each card — no images, no re-extraction.

    python manage.py backfill_card_salutations --dry-run      # preview
    python manage.py backfill_card_salutations                # apply
    python manage.py backfill_card_salutations --limit 50     # first 50 only

Cards that already carry a salutation are skipped, so the command is safe to
re-run and safe to interrupt.
"""
from __future__ import annotations

import json
import logging
import re

from django.core.management.base import BaseCommand

from cards.models import BusinessCard
from cards.services.welcome_translate import call_gemini_json  # same key rotation

logger = logging.getLogger(__name__)

BATCH_SIZE = 10

PROMPT = """For each business-card record below, produce the opening salutation
of a FORMAL letter of appreciation sent by a government ministry, plus the
languages the card is printed in.

For every record return an object with these keys:
- "id": the record's id, unchanged.
- "printed_languages": ISO 639-1 codes of the languages the text appears to be
  written in, most prominent first (e.g. ["ar"], ["ar","en"], ["de"]).
- "salutation_ar": the Arabic salutation.
- "salutation_en": the English salutation.
- "salutation_native": the same salutation in the card's own language ONLY when
  that language is neither Arabic nor English; otherwise "".

Rules:
- Address a named person as a person; address a company, chamber, embassy or
  ministry with no personal name as an organisation.
- Honour printed rank and titles: minister/ambassador/CEO/Dr./Eng. must be
  reflected ("معالي الوزير"، "سعادة السفير"، "حضرة السيد المدير العام").
- Infer grammatical gender from the person's name for the Arabic form. When the
  name is genuinely ambiguous, address the organisation instead or use a neutral
  plural form.
- One line each, ending with a comma. No greeting words, no body text.
- Return "" for a record with no usable name.

Return JSON: {{"results": [ ... ]}}

RECORDS:
{records}
"""


class Command(BaseCommand):
    help = 'Fill printed_languages and salutations on cards that lack them.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving.')
        parser.add_argument('--limit', type=int, default=0, help='Process at most N cards.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        queryset = BusinessCard.objects.filter(salutation_ar='', salutation_en='').order_by('id')
        if limit:
            queryset = queryset[:limit]
        cards = list(queryset)
        if not cards:
            self.stdout.write(self.style.SUCCESS('No cards need backfilling.'))
            return

        self.stdout.write(f'{len(cards)} card(s) to process, {BATCH_SIZE} per request.')
        updated = failed = 0

        for start in range(0, len(cards), BATCH_SIZE):
            batch = cards[start:start + BATCH_SIZE]
            records = [
                {
                    'id': card.id,
                    'person_name': card.person_name,
                    'job_title': card.job_title,
                    'company_name': card.company_name,
                    'country': card.country,
                    'text': (card.raw_text or '')[:400],
                }
                for card in batch
            ]
            prompt = PROMPT.format(records=json.dumps(records, ensure_ascii=False, indent=1))
            try:
                payload = call_gemini_json(prompt)
            except Exception as exc:  # noqa: BLE001 — report and continue
                failed += len(batch)
                reason = re.sub(r'\s+', ' ', str(exc))[:160]
                self.stderr.write(self.style.WARNING(f'  batch at {start} failed: {reason}'))
                continue

            by_id = {card.id: card for card in batch}
            for result in (payload.get('results') or []):
                card = by_id.get(result.get('id'))
                if card is None:
                    continue
                card.salutation_ar = str(result.get('salutation_ar') or '').strip()[:255]
                card.salutation_en = str(result.get('salutation_en') or '').strip()[:255]
                card.salutation_native = str(result.get('salutation_native') or '').strip()[:255]
                languages = [
                    re.sub(r'[^a-z]', '', str(code).lower())[:2]
                    for code in (result.get('printed_languages') or [])
                ]
                card.printed_languages = [code for code in dict.fromkeys(languages) if len(code) == 2][:4]

                if dry_run:
                    self.stdout.write(
                        f'  #{card.sequence_number} {card.printed_languages} → {card.salutation_ar}'
                    )
                else:
                    card.save(update_fields=[
                        'salutation_ar', 'salutation_en', 'salutation_native',
                        'printed_languages', 'updated_at',
                    ])
                updated += 1

        verb = 'would update' if dry_run else 'updated'
        self.stdout.write(self.style.SUCCESS(f'{verb} {updated} card(s); {failed} failed.'))
