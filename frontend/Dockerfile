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

# Nginx'in varsayılan config dosyasını kaldırıyoruz.
# Bu dosya genellikle /etc/nginx/conf.d/default.conf adresinde bulunur.
# Bu adım, istenmeyen 301 yönlendirmelerini veya konfigürasyon çakışmalarını önleyecektir.
RUN rm /etc/nginx/conf.d/default.conf || true # Hata vermemesi için || true ekledik

# Build aşamasında oluşturduğumuz /app/dist klasörünün içindeki dosyaları
# Nginx'in web root dizinine kopyalıyoruz
COPY --from=build /app/dist /usr/share/nginx/html

# Ana Nginx konfigürasyon dosyamızı kopyalıyoruz (/etc/nginx/nginx.conf)
COPY frontend/nginx.conf /etc/nginx/nginx.conf

# Envsubst ile işlenecek uygulama konfigürasyon şablonunu kopyalıyoruz
COPY frontend/nginx.template /etc/nginx/nginx.template

EXPOSE 80
# Envsubst ile şablonu işleyip /tmp dizinine yazıyoruz
# Sonra Nginx'i başlatıyoruz. Ana nginx.conf dosyası /tmp'deki bu dosyayı include edecek.
CMD ["/bin/sh", "-c", "envsubst < /etc/nginx/nginx.template > /tmp/default.conf && nginx -g 'daemon off;'"]