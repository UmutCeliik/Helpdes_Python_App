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

# Nginx'in varsayılan conf.d dizinindeki default.conf dosyasını kullanmak yerine,
# kendi nginx.conf dosyamızı direkt Nginx'in ana konfigürasyon dizinine kopyalıyoruz
# ve bunu şablon olarak işaretliyoruz.
COPY frontend/nginx.conf /etc/nginx/nginx.conf.template

# RUN chown ve RUN chmod satırları burada artık gerekli değil, çünkü doğrudan /etc/nginx/conf.d'ye yazmayacağız
# Nginx varsayılan olarak /etc/nginx/nginx.conf'u okur.
# Daha önceki 'conf.d' dizini izin sorunları yaratıyordu.

EXPOSE 80
# envsubst ile şablonu işleyip doğrudan /etc/nginx/nginx.conf'a yazıyoruz
# Bu dosya genellikle Nginx container'ı içinde root tarafından yazılabilir.
CMD ["/bin/sh", "-c", "envsubst < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && nginx -g 'daemon off;'"]