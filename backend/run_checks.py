import os
import sys

# Ensure we use sqlite for local checks regardless of .env and prevent loading .env file
os.environ.pop('DATABASE_URL', None)
os.environ['SKIP_LOAD_ENV'] = '1'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.management import execute_from_command_line

# Forward args, default to ['makemigrations','--check','--dry-run']
args = sys.argv[1:] or ['makemigrations','--check','--dry-run']
execute_from_command_line(['manage.py'] + args)
