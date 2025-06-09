# Temel olarak hafif bir Python imajı kullanıyoruz
FROM python:3.11-slim

# Proje kodunun yaşayacağı ana dizin
WORKDIR /app

# Python'a, modülleri ararken /app dizinine de bakmasını söylüyoruz.
# BU SATIR ÇOK ÖNEMLİ.
ENV PYTHONPATH=/app

# Önce SADECE bu servisin bağımlılıklarını kuruyoruz
# Not: 'service_name' kısmını her Dockerfile'da ilgili servis adıyla değiştirin.
COPY ./auth_service/requirements.txt /app/auth_service/
RUN pip install --no-cache-dir -r /app/auth_service/requirements.txt

# Şimdi SADECE bu servisin kodunu kendi klasörüne kopyalıyoruz
# Not: 'service_name' kısmını her Dockerfile'da ilgili servis adıyla değiştirin.
COPY ./auth_service /app/auth_service

# Çalışma dizinini servis klasörüne taşıyoruz.
# Bu, alembic.ini dosyasının doğru yerde bulunmasını sağlar.
WORKDIR /app/auth_service

# Konteyneri çalıştıracak olan komut.
# Not: 'service_name' kısmını her Dockerfile'da ilgili servis adıyla değiştirin.
# auth_service için 'alembic upgrade head &&' kısmını kaldırın.
CMD ["uvicorn", "auth_service.main:app", "--host", "0.0.0.0", "--port", "8000"]