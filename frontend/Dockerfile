# frontend/Dockerfile
# --- 1. AŞAMA: Build Aşaması ---
FROM node:20-alpine AS build

# Çalışma dizinini /app olarak ayarlıyoruz
WORKDIR /app

# package.json ve package-lock.json dosyalarını kopyalıyoruz
COPY frontend/package*.json ./

# Bağımlılıkları kuruyoruz
RUN npm install

# Tüm proje dosyalarını kopyalıyoruz (frontend klasörünün tamamını)
COPY frontend/ .

# Vue projesini derleyip /app/dist klasörüne statik dosyaları oluşturuyoruz
RUN npm run build

# --- 2. AŞAMA: Serve Aşaması ---
FROM nginx:stable-alpine

# Build aşamasında oluşturduğumuz /app/dist klasörünün içindeki dosyaları
# Nginx'in web root dizinine kopyalıyoruz
COPY --from=build /app/dist /usr/share/nginx/html

# Ana Nginx konfigürasyon dosyamızı kopyalıyoruz
COPY frontend/nginx.conf /etc/nginx/nginx.conf

# Envsubst ile işlenecek uygulama konfigürasyon şablonunu kopyalıyoruz
COPY frontend/nginx.template /etc/nginx/nginx.template

# Nginx'in geçici dizinlerini önceden oluşturma komutunu kaldırıyoruz
# RUN mkdir -p /tmp/client_temp /tmp/proxy_temp ... ve chown satırını SİLİN.
# Nginx'in kendisinin bu dizinleri /tmp altında oluşturmasına izin vereceğiz.

EXPOSE 80
# Envsubst ile şablonu işleyip /tmp dizinine yazıyoruz
# Sonra Nginx'i başlatıyoruz. Ana nginx.conf dosyası /tmp'deki bu dosyayı include edecek.
CMD ["/bin/sh", "-c", "envsubst < /etc/nginx/nginx.template > /tmp/default.conf && nginx -g 'daemon off;'"]