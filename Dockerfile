FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Зависимости отдельным слоем: они меняются реже кода, и пересборка идёт по кешу
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

# Процесс работает не от root: если кто-то вылезет из приложения, ему достанется
# пользователь без прав
RUN useradd --create-home --uid 1000 budget && chown -R budget:budget /app
USER budget

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
