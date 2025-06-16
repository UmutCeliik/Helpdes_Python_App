// frontend/src/main.js (NİHAİ ve DOĞRU HALİ)

// Temel Vue ve Stil dosyaları
import './assets/main.css';
import { createApp } from 'vue';

// Pinia State Management
import { createPinia } from 'pinia';
import { useAuthStore } from './stores/auth';

// Vue Router
import App from './App.vue';
import router from './router';

// Axios API İstemcisi
import apiClient from './api/axios';

// Vuetify Kurulumu
import vuetify from './plugins/vuetify';

// Keycloak servisi (Dosyanın en başında, doğru yöntem bu)
import { initKeycloak, keycloak } from './services/keycloak.service';


// Vue uygulamasını oluştur
const app = createApp(App);

// Pinia'yı oluştur ve kullan
const pinia = createPinia();
app.use(pinia);

// --- Axios Interceptor'lar (Token ekleme mekanizması) ---
apiClient.interceptors.request.use(
  (config) => {
    // Burada 'require' KULLANMIYORUZ.
    // Dosyanın başında import ettiğimiz 'keycloak' objesini doğrudan kullanıyoruz.
    if (keycloak && keycloak.authenticated && keycloak.token) {
      config.headers['Authorization'] = `Bearer ${keycloak.token}`;
    }
    return config;
  },
  (error) => {
    console.error('Axios request interceptor hatası:', error);
    return Promise.reject(error);
  }
);

apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    console.log('Axios response interceptor error object:', error);
    if (error.response) {
      console.log('Axios response interceptor error.response.data:', error.response.data);
    }
    // Token yenileme mantığı
    if (error.response && error.response.status === 401 && !originalRequest._retry && keycloak && keycloak.authenticated) {
      originalRequest._retry = true;
      try {
        console.log('Axios Interceptor: 401 alındı, Keycloak token yenileme deneniyor...');
        const refreshed = await keycloak.updateToken(30);
        if (refreshed) {
          console.log('Axios Interceptor: Keycloak token başarıyla yenilendi, orijinal istek tekrarlanıyor.');
          const authStore = useAuthStore();
          authStore.setKeycloakAuth(keycloak);

          if (keycloak.token) {
            originalRequest.headers['Authorization'] = `Bearer ${keycloak.token}`;
          }
          return apiClient(originalRequest);
        } else {
          console.warn('Axios Interceptor: Token yenilenemedi. Oturum sonlandırılıyor.');
          const authStore = useAuthStore();
          authStore.logout();
        }
      } catch (e) {
        console.error('Axios Interceptor: Token yenileme sırasında kritik hata. Oturum sonlandırılıyor.', e);
        const authStore = useAuthStore();
        authStore.logout();
        return Promise.reject(new Error('Oturum yenilenemedi veya sonlandı. Lütfen tekrar giriş yapın.'));
      }
    }
    return Promise.reject(error);
  }
);

// --- Vue Uygulamasını Başlatma ---
initKeycloak({ onLoad: 'check-sso' })
  .then((authenticated) => {
    const authStore = useAuthStore();
    authStore.setKeycloakAuth(keycloak);

    app.use(router);
    app.use(vuetify);
    app.mount('#app');

    if (authenticated) {
      console.log("Main.js: Kullanıcı check-sso ile doğrulandı. Uygulama başlatıldı.");
    } else {
      console.log("Main.js: Kullanıcı check-sso ile doğrulanmadı. Uygulama başlatıldı. Login gerekebilir.");
    }
  })
  .catch((error) => {
    console.error("Main.js: Keycloak kritik başlatma hatası! Kimlik doğrulama olmadan devam ediliyor.", error);
    const authStore = useAuthStore();
    authStore.clearAuthState();

    app.use(router);
    app.use(vuetify);
    app.mount('#app');
  });
