# Local-dev image only. PythonAnywhere (the actual production target) does
# not run Docker — see README "Deploying to PythonAnywhere". This image
# exists so `docker-compose up` gives a one-command local environment with
# GDAL/GEOS/PostGIS client libraries already present, which are the fiddly
# part of a GeoDjango setup.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        libproj-dev \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
