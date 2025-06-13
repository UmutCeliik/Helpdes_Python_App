# Temel olarak hafif bir Python imajı kullanıyoruz
FROM python:3.11-slim

# Proje kodunun yaşayacağı ana dizin
WORKDIR /app

# Python'a, modülleri ararken /app dizinine de bakmasını söylüyoruz.
# BU SATIR ÇOK ÖNEMLİ.
ENV PYTHONPATH=/app

# Önce SADECE bu servisin bağımlılıklarını kuruyoruz
# Not: 'ticket_service' kısmını her Dockerfile'da ilgili servis adıyla değiştirin.
COPY ./ticket_service/requirements.txt /app/ticket_service/
RUN pip install --no-cache-dir -r /app/ticket_service/requirements.txt

# Şimdi SADECE bu servisin kodunu kendi klasörüne kopyalıyoruz
# Not: 'ticket_service' kısmını her Dockerfile'da ilgili servis adıyla değiştirin.
COPY ./ticket_service /app/ticket_service

# Çalışma dizinini servis klasörüne taşıyoruz.
# Bu, alembic.ini dosyasının doğru yerde bulunmasını sağlar.
WORKDIR /app/ticket_service

# Konteyneri çalıştıracak olan komut.
# Not: 'ticket_service' kısmını her Dockerfile'da ilgili servis adıyla değiştirin.
# auth_service için 'alembic upgrade head &&' kısmını kaldırın.
CMD ["sh", "-c", "alembic upgrade head && uvicorn ticket_service.main:app --host 0.0.0.0 --port 8000"]
# CMD ["uvicorn", "ticket_service.main:app", "--host", "0.0.0.0", "--port", "8000"]