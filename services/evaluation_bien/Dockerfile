FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/evaluation_bien/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/evaluation_bien/ .

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
