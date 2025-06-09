# Temel olarak hafif bir Python imajı kullanıyoruz
FROM python:3.11-slim

# Çalışma dizinini /app olarak ayarlıyoruz
WORKDIR /app

# Python'a /app dizininin de modül arama yollarına dahil olduğunu söylüyoruz.
# Bu, database_pkg gibi paylaşılan paketleri bulmasını sağlar.
ENV PYTHONPATH="/app"

# Önce SADECE projedeki TÜM requirements dosyalarını kopyalıyoruz
# Not: Buradaki yol, build bağlamının kök dizin olmasına göre ayarlandı.
COPY ./auth_service/requirements.txt /app/auth_service/
COPY ./ticket_service/requirements.txt /app/ticket_service/
COPY ./user_service/requirements.txt /app/user_service/
# ...Eğer başka servislerin requirements'ları varsa onlar da eklenebilir...

# Her servisin kendi gereksinimlerini kuruyoruz
RUN pip install --no-cache-dir -r /app/ticket_service/requirements.txt && \
    pip install --no-cache-dir -r /app/user_service/requirements.txt && \
    pip install --no-cache-dir -r /app/auth_service/requirements.txt

# Şimdi paylaşılan ve servise özel kodları kopyalıyoruz
COPY ./database_pkg /app/database_pkg
COPY ./auth_service /app/auth_service
COPY ./ticket_service /app/ticket_service
COPY ./user_service /app/user_service

# Konteyner dışından erişim için 8000 portunu açıyoruz
EXPOSE 8000

# Konteyneri çalıştıracak olan komut.
# BU KOMUT HER SERVİSİN KENDİ DOCKERFILE'INDA ÖZELLEŞTİRİLMELİDİR!
# Örnek ticket_service için:
CMD ["uvicorn", "user_service.main:app", "--host", "0.0.0.0", "--port", "8000"]