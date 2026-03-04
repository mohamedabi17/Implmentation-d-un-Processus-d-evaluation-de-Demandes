FROM python:3.11-slim

WORKDIR /app

# Copier les dépendances partagées
COPY shared/ /app/shared/

# Copier les requirements du service
COPY services/demandes/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code du service
COPY services/demandes/ .

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
