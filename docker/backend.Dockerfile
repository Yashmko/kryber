FROM python:3.12-slim

# FFmpeg (media extraction + rendering) and Node.js 22 (JavaScript runtime for
# yt-dlp's YouTube player-challenge solver — yt-dlp only enables Deno by
# default, so Kryber detects Node and passes --js-runtimes explicitly).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && node --version

WORKDIR /srv

COPY backend/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

COPY backend /srv/backend

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/srv/backend

WORKDIR /srv/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
