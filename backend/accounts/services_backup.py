"""Full data backup as a plain ``.sql`` file, and its restore.

The file holds DATA ONLY (no CREATE TABLE): the schema always comes from the
migrations, so a backup restores into any database migrated to the same
version. Restoring REPLACES every table's content with the backup's:

    1. python manage.py migrate
    2. python manage.py restore_sql_backup backup.sql --yes
       (or, on PostgreSQL:  psql -U <user> -d <db> -f backup.sql)

Generated with Django's own connection rather than ``pg_dump``: the backend
image ships no PostgreSQL client, and the same code backs up the local SQLite
database too. Only the SQL dialect of the database it was taken from is
emitted, so a PostgreSQL backup restores into PostgreSQL, SQLite into SQLite.

Not included: sessions (everyone signs in again after a restore — and session
keys are credentials), and uploaded media files (card images live on disk
under MEDIA_ROOT; back that folder up alongside).
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid
from typing import IO, Iterator

from django.apps import apps
from django.core.management.color import no_style
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder

# Restored as empty, never dumped.
SKIPPED_TABLES = {'django_session'}

ROWS_PER_INSERT = 100
FETCH_SIZE = 500


def _postgres() -> bool:
    return connection.vendor == 'postgresql'


def _backed_up_models() -> list:
    """Every concrete table Django manages (M2M link tables included), parents
    before the tables that reference them."""
    existing = set(connection.introspection.table_names())
    models = [
        model for model in apps.get_models(include_auto_created=True)
        if model._meta.managed and not model._meta.proxy and not model._meta.swapped
        and model._meta.db_table in existing
    ]
    ordered, seen = [], set()

    def visit(model, trail=()):
        if model in seen or model in trail:
            return
        for field in model._meta.local_concrete_fields:
            target = getattr(field.remote_field, 'model', None) if field.remote_field else None
            if target is not None and target is not model and target in models:
                visit(target, (*trail, model))
        seen.add(model)
        ordered.append(model)

    for model in sorted(models, key=lambda m: m._meta.db_table):
        visit(model)
    return ordered


def _literal(value) -> str:
    """A SQL literal for one value as the database driver returned it."""
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        if _postgres():
            return 'TRUE' if value else 'FALSE'
        return '1' if value else '0'
    if isinstance(value, (int, decimal.Decimal)):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        hexed = bytes(value).hex()
        return f"'\\x{hexed}'::bytea" if _postgres() else f"X'{hexed}'"
    if isinstance(value, (dict, list)):  # PostgreSQL json/jsonb come back decoded
        value = json.dumps(value, ensure_ascii=False)
    elif isinstance(value, (dt.datetime, dt.date, dt.time)):
        value = value.isoformat()
    elif isinstance(value, dt.timedelta):
        return f"'{value.total_seconds()} seconds'::interval" if _postgres() else str(
            int(value.total_seconds() * 1_000_000))
    elif isinstance(value, uuid.UUID):
        value = str(value)
    text = str(value).replace('\x00', '')
    return "'" + text.replace("'", "''") + "'"


def _header(models) -> Iterator[str]:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    yield '-- Business card platform — data backup'
    yield f'-- Taken: {now} · database: {connection.vendor}'
    yield '-- DATA ONLY. Restore into a database migrated to the same version:'
    yield '--   python manage.py migrate'
    yield '--   python manage.py restore_sql_backup <this file> --yes'
    yield '-- Restoring REPLACES the content of every table below.'
    yield '-- Card images are files under MEDIA_ROOT and are NOT in this backup.'
    latest = {}
    for app_label, name in MigrationRecorder(connection).applied_migrations():
        latest[app_label] = max(latest.get(app_label, ''), name)
    yield '-- Migrations: ' + ', '.join(f'{app}.{name}' for app, name in sorted(latest.items()))
    yield f'-- Tables: {len(models)}'
    yield ''


def iter_backup_sql(models=None) -> Iterator[str]:
    """The backup, line by line. Call inside a transaction for a consistent
    snapshot (see ``write_backup``)."""
    models = models if models is not None else _backed_up_models()
    quote = connection.ops.quote_name
    dumped = [m for m in models if m._meta.db_table not in SKIPPED_TABLES]
    wiped = [m._meta.db_table for m in models]

    yield from _header(dumped)
    if _postgres():
        yield "SET client_encoding = 'UTF8';"
        yield 'SET standard_conforming_strings = on;'
    yield 'BEGIN;'
    if _postgres():
        yield 'TRUNCATE TABLE ' + ', '.join(quote(t) for t in wiped) + ' RESTART IDENTITY CASCADE;'
    else:
        yield 'PRAGMA defer_foreign_keys = ON;'
        for table in reversed(wiped):
            yield f'DELETE FROM {quote(table)};'

    for model in dumped:
        table = model._meta.db_table
        columns = [field.column for field in model._meta.local_concrete_fields]
        column_sql = ', '.join(quote(c) for c in columns)
        pk = quote(model._meta.pk.column)
        yield ''
        yield f'-- {table}'
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT {column_sql} FROM {quote(table)} ORDER BY {pk}')
            batch: list[str] = []
            while True:
                rows = cursor.fetchmany(FETCH_SIZE)
                if not rows:
                    break
                for row in rows:
                    batch.append('(' + ', '.join(_literal(v) for v in row) + ')')
                    if len(batch) >= ROWS_PER_INSERT:
                        yield f'INSERT INTO {quote(table)} ({column_sql}) VALUES\n' + ',\n'.join(batch) + ';'
                        batch = []
            if batch:
                yield f'INSERT INTO {quote(table)} ({column_sql}) VALUES\n' + ',\n'.join(batch) + ';'

    # Move every id sequence past the restored rows (no-op on SQLite).
    reset = connection.ops.sequence_reset_sql(no_style(), dumped)
    if reset:
        yield ''
        yield from reset
    yield 'COMMIT;'
    yield ''


def write_backup(out: IO[bytes]) -> None:
    """Write the full backup to a binary file object, from one consistent
    snapshot of the database."""
    with transaction.atomic():
        if _postgres():
            with connection.cursor() as cursor:
                # Must be the transaction's first statement.
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        for line in iter_backup_sql():
            out.write(line.encode('utf-8'))
            out.write(b'\n')


def backup_filename(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now()
    return f'business-cards-backup-{now:%Y%m%d-%H%M}.sql'


def restore_backup(sql: str) -> None:
    """Run a backup file against the current database. The file carries its own
    BEGIN/COMMIT, so a failure leaves the database untouched."""
    if not sql.lstrip().startswith('-- Business card platform — data backup'):
        raise ValueError('هذا الملف ليس نسخة احتياطية من المنصة.')
    connection.ensure_connection()
    if _postgres():
        with connection.cursor() as cursor:
            try:
                cursor.execute(sql)
            except Exception:
                # Leave the session usable: the failed BEGIN block stays open otherwise.
                cursor.execute('ROLLBACK')
                raise
    else:
        raw = connection.connection  # sqlite3.Connection
        try:
            raw.executescript(sql)
        except Exception:
            raw.rollback()
            raise
