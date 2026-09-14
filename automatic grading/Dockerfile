FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt requirements-ocr.txt requirements-pdf.txt ./
# CPU wheels avoid unnecessarily shipping CUDA libraries on a small server.
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements-ocr.txt
RUN useradd --create-home --uid 10001 grading && mkdir -p /app/data && chown grading:grading /app/data
COPY --chown=grading:grading app ./app
COPY --chown=grading:grading static ./static
COPY --chown=grading:grading tools ./tools
COPY --chown=grading:grading run.py ./run.py
USER grading
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health',timeout=4)"
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8001"]
