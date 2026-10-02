FROM python:3.12-slim

# ffmpeg isn't available on Render's native Python runtime, which is why this project
# deploys as a container instead of a plain "Python service" there.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p downloads temp

# Render (and most PaaS hosts) inject $PORT; gunicorn.conf.py already reads it.
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
