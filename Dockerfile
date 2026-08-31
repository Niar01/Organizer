FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Copiar e instalar dependencias usando requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copiar el script
COPY organizer.py .

# 3. Estructura interna simulando el HOME de root
RUN mkdir -p /root/Downloads /root/.config/downloads-organizer

# 4. Ejecución del script
CMD ["python", "organizer.py", "--config", "/root/.config/downloads-organizer/config.json"]
