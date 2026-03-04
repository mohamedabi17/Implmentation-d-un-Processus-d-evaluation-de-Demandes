FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/decision/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/decision/ .

EXPOSE 8004

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
