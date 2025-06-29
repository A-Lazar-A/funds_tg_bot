FROM python:3.11-slim

# Установить системные зависимости для pyzbar и Pillow
RUN apt-get update && apt-get install -y \
    libzbar0 \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Установить рабочую директорию
WORKDIR /app

# Копировать зависимости
COPY requirements.txt .

# Установить зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копировать исходный код
COPY . .

# Указать переменные окружения (или используйте docker-compose)
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "bot.py"] 