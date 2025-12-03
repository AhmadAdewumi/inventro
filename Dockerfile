FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

#-- install system dependencies
#-- netcat used to wait for db, curl kept fpr heallthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    netcat-openbsd \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

#-- we copy the requirement.txt first so we only re install pip if requirements change
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

#-- copy the project code
COPY . .

#-- collect static files i.e js, html, css for whitenose
RUN python manage.py collectstatic --noinput

#-- create non root user
RUN useradd -m djangouser

#-- give permission to the app folder
RUN chown -R djangouser:djangouser /app
USER djangouser

#-- run the prod server using gunicorn, we bind 0.0.0.0 so external traffic can reach the container
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000"]