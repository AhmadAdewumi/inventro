#!/usr/bin/env bash
# Exit on error
set -o errexit

# 1. Install Dependencies
pip install -r requirements.txt

# 2. Collect Static Files (CSS/JS)
python manage.py collectstatic --no-input

# 3. Run Migrations
python manage.py migrate

# 4. Create Superuser (Auto-create if not exists)
#-- a hack for the first deployment so I don't get locked out
python manage.py shell -c "
from django.contrib.auth.models import User;
if not User.objects.filter(username='adewumi').exists():
    User.objects.create_superuser('adewumi', 'adewumi@gmail.com', 'adewumi123');
    print('Superuser created: adewumi/adewumi123')
"