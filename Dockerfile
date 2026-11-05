FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home --uid 10001 aivora
COPY src ./src
RUN mkdir /app/data && chown -R aivora:aivora /app
USER aivora
EXPOSE 8090
CMD ["python", "-m", "uvicorn", "aivora.main:app", "--host", "0.0.0.0", "--port", "8090"]
