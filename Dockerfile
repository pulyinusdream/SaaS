FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 KJANCY_DATA_DIR=/data KJANCY_BIND=0.0.0.0 PORT=8080
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 kjancy \
    && useradd --uid 10001 --gid 10001 --no-create-home kjancy \
    && mkdir /data && chown 10001:10001 /data
COPY --chown=10001:10001 kjancy/ ./kjancy/
COPY --chown=10001:10001 marketing/ ./marketing/
COPY --chown=10001:10001 serve.py backup.py ./
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python", "-c", "import os,urllib.request,urllib.parse; host=urllib.parse.urlsplit(os.environ['KJANCY_PUBLIC_BASE_URL']).netloc; req=urllib.request.Request('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',headers={'Host':host}); response=urllib.request.urlopen(req,timeout=3); assert response.status==200"]
CMD ["python", "serve.py"]
