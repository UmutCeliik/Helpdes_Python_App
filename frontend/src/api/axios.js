// frontend/src/api/axios.js
import axios from 'axios';

// Temel URL'leri burada tanımlayabiliriz veya boş bırakabiliriz
// const API_BASE_URL = 'http://localhost:8000'; // Örnek

const apiClient = axios.create({
  // baseURL'i ayarlayarak tüm göreceli isteklerin doğru ana adrese gitmesini sağlıyoruz.
  baseURL: '/',
  headers: {
    'Content-Type': 'application/json',
  }
});

apiClient.interceptors.request.use(
  (config) => {
    const { keycloak } = require('@/services/keycloak.service'); // veya import yolu nasılsa
    if (keycloak && keycloak.authenticated && keycloak.token) {
      config.headers['Authorization'] = `Bearer ${keycloak.token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Yapılandırılmış instance'ı export et
export default apiClient;