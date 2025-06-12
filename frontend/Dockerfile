# frontend/Dockerfile
# --- 1. AŞAMA: Build Aşaması ---
FROM node:20-alpine AS build

# Çalışma dizinini /app olarak ayarlıyoruz
WORKDIR /app

# package.json ve package-lock.json dosyalarını kopyalıyoruz
# Docker'ın build context'i (docker-compose.yml'deki 'frontend' klasörü)
# burası olduğu için, doğrudan bu klasörün içindeki dosya adlarını kullanıyoruz.
# Yani: Helpdes_Python_App-main/frontend/package*.json dosyalarını
# konteyner içindeki /app dizinine kopyala.
COPY package*.json ./

# Bağımlılıkları kuruyoruz
RUN npm install

# Tüm proje dosyalarını (frontend klasörünün tamamını) /app dizinine kopyala
# '.' mevcut çalışma dizinini (şu anda /app) ve build context'inin kökünü (frontend klasörü) temsil eder.
# Yani: Helpdes_Python_App-main/frontend/ dizinindeki tüm içeriği
# konteyner içindeki /app dizinine kopyala.
COPY . .

# Vue projesini derleyip /app/dist klasörüne statik dosyaları oluşturuyoruz
RUN npm run build

# --- 2. AŞAMA: Serve Aşaması ---
# Son imajımız için hafif bir Nginx web sunucusu kullanıyoruz
FROM nginx:stable-alpine

# Build aşamasında oluşturduğumuz /app/dist klasörünün içindeki dosyaları
# Nginx'in web root dizinine kopyalıyoruz
COPY --from=build /app/dist /usr/share/nginx/html

# Vue Router'ın History Modu'nda düzgün çalışması için Nginx konfigürasyonunu kopyalıyoruz
# Yine, build context'i 'frontend' klasörü olduğu için, 'nginx.conf' o klasörün içindedir.
# Yani: Helpdes_Python_App-main/frontend/nginx.conf dosyasını
# konteyner içindeki /etc/nginx/conf.d/default.conf yoluna kopyala.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Konteynerin 80 portunu dinleyeceğini belirtiyoruz
EXPOSE 80

# Nginx sunucusunu başlatıyoruz
CMD ["nginx", "-g", "daemon off;"]