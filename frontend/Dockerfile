# frontend/Dockerfile
# --- 1. AŞAMA: Build Aşaması ---
FROM node:20-alpine AS build

# Debug: WORKDIR öncesi kök dizini (build context'i) göster
RUN echo "--- DEBUG (Dockerfile): Before WORKDIR /app. Current dir: $(pwd) ---"
RUN ls -lA 
RUN echo "-------------------------------------------------------------------"

# Çalışma dizinini /app olarak ayarlıyoruz
WORKDIR /app

# Debug: WORKDIR sonrası /app dizinini göster
RUN echo "--- DEBUG (Dockerfile): After WORKDIR /app. Current dir: $(pwd) ---"
RUN ls -lA 
RUN echo "--------------------------------------------------------------------"

# package.json ve package-lock.json dosyalarını kopyalıyoruz
COPY package*.json ./

# Debug: COPY package*.json sonrası /app dizinini göster
RUN echo "--- DEBUG (Dockerfile): After COPY package*.json ---"
RUN ls -lA 
RUN echo "----------------------------------------------------"

# Bağımlılıkları kuruyoruz
RUN npm install

# Debug: npm install sonrası /app dizinini göster
RUN echo "--- DEBUG (Dockerfile): After npm install ---"
RUN ls -lA 
RUN echo "---------------------------------------------"

# Tüm proje dosyalarını (Dockerfile'ın bulunduğu dizindeki her şeyi) kopyalıyoruz
COPY . . 

# Debug: COPY . . sonrası /app dizinini göster
RUN echo "--- DEBUG (Dockerfile): After COPY . . ---"
RUN ls -lA 
RUN echo "------------------------------------------"

# Vue projesini derleyip /app/dist klasörüne statik dosyaları oluşturuyoruz
RUN npm run build

# Debug: npm run build sonrası /app dizinini göster
RUN echo "--- DEBUG (Dockerfile): After npm run build ---"
RUN ls -lA 
RUN echo "-----------------------------------------------"

# --- 2. AŞAMA: Serve Aşaması ---
FROM nginx:stable-alpine

# Debug: İlk Serve aşaması. Current dir: $(pwd)
RUN echo "--- DEBUG (Dockerfile): Serve Stage 1. Current dir: $(pwd) ---"
RUN ls -lA
RUN echo "-------------------------------------------------------------"

# Build aşamasında oluşturduğumuz /app/dist klasörünün içindeki dosyaları
# Nginx'in web root dizinine kopyalıyoruz
COPY --from=build /app/dist /usr/share/nginx/html

# Debug: COPY --from=build sonrası Nginx root dizinini göster
RUN echo "--- DEBUG (Dockerfile): After COPY --from=build to /usr/share/nginx/html ---"
RUN ls -lA /usr/share/nginx/html
RUN echo "--------------------------------------------------------------------------"

# Nginx konfigürasyonunu kopyalıyoruz
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Debug: COPY nginx.conf sonrası Nginx conf dizinini göster
RUN echo "--- DEBUG (Dockerfile): After COPY nginx.conf to /etc/nginx/conf.d ---"
RUN ls -lA /etc/nginx/conf.d
RUN echo "--------------------------------------------------------------------"

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]