FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
COPY vendor/ vendor/
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

WORKDIR /app/src

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]