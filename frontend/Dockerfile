# --- 1. AŞAMA: Build Aşaması ---
# Kodumuzu derlemek için Node.js ortamını kullanıyoruz ve bu aşamaya "build" adını veriyoruz
FROM node:20-alpine AS build

# Çalışma dizinini /app olarak ayarlıyoruz
WORKDIR /app

# package.json ve package-lock.json dosyalarını kopyalıyoruz
COPY frontend/package*.json ./

# Bağımlılıkları kuruyoruz
RUN npm install

# Tüm proje dosyalarını kopyalıyoruz
COPY frontend/ .

# Vue projesini derleyip /app/dist klasörüne statik dosyaları oluşturuyoruz
RUN npm run build

# --- 2. AŞAMA: Serve Aşaması ---
# Son imajımız için hafif bir Nginx web sunucusu kullanıyoruz
FROM nginx:stable-alpine

# Build aşamasında oluşturduğumuz /app/dist klasörünün içindeki dosyaları
# Nginx'in web root dizinine kopyalıyoruz
COPY --from=build /app/dist /usr/share/nginx/html

# Vue Router'ın History Modu'nda düzgün çalışması için Nginx konfigürasyonunu kopyalıyoruz
# (Bu dosyayı bir sonraki adımda oluşturacağız)
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Konteynerin 80 portunu dinleyeceğini belirtiyoruz
EXPOSE 80

# Nginx sunucusunu başlatıyoruz
CMD ["nginx", "-g", "daemon off;"]