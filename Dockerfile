FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system mantecato \
    && adduser --system --ingroup mantecato mantecato

COPY pyproject.toml ./
COPY apps ./apps
COPY cli ./cli
COPY core ./core
COPY mantecato ./mantecato
COPY manage.py ./manage.py
COPY static ./static
COPY templates ./templates

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && mkdir -p /app/staticfiles \
    && chown -R mantecato:mantecato /app

USER mantecato

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn mantecato.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout ${GUNICORN_TIMEOUT:-60} --access-logfile - --error-logfile -"]
