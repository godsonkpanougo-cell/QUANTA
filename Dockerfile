FROM python:3.12-slim

# Installer les dépendances système requises par WeasyPrint
# GTK, Pango, Cairo et leurs dépendances
RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libatk1.0-0 \
    libatk-bridge-2.0-0 \
    libatspi2.0-0 \
    libglib2.0-0 \
    libgobject-2.0-0 \
    libharfbuzz-0-0 \
    libffi-dev \
    libjpeg-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Créer le répertoire de travail
WORKDIR /app

# Copier les fichiers de dépendances
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste du code
COPY . .

# Créer le dossier /data pour la persistance SQLite
RUN mkdir -p /data

# Exposer le port (Railway utilise $PORT)
EXPOSE 8000

# Commande de démarrage
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
