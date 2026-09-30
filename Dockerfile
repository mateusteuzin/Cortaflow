FROM python:3.11-slim
ENV ENVIRONMENT=production
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY sql sql
RUN groupadd --system cortaflow && useradd --system --gid cortaflow cortaflow \
    && mkdir -p /app/app/static/uploads \
    && chown -R cortaflow:cortaflow /app/app/static/uploads
USER cortaflow
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
