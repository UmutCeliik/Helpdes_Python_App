// frontend/src/main.js

// Temel Vue ve Stil dosyaları
import './assets/main.css'; // Genel stilleriniz
import { createApp } from 'vue';

// Pinia State Management
import { createPinia } from 'pinia';
import { useAuthStore } from './stores/auth'; // Auth store'unuz

// Vue Router
import App from './App.vue';
import router from './router';

// Axios API İstemcisi
import apiClient from './api/axios';

// Vuetify Kurulumu
import vuetify from './plugins/vuetify'; // YENİ IMPORT
// Keycloak servisini import et
import { initKeycloak, keycloak } from './services/keycloak.service';
// Vue uygulamasını oluştur
const app = createApp(App);

// Pinia'yı oluştur ve kullan
const pinia = createPinia();
app.use(pinia);

// --- Axios Interceptor'lar (Keycloak ile güncellenmiş) ---
// İstek (Request) Interceptor'ı
apiClient.interceptors.request.use(
  (config) => {
    // Keycloak doğrulanmışsa ve token varsa Authorization header'ını ekle
    if (keycloak && keycloak.authenticated && keycloak.token) {
      config.headers['Authorization'] = `Bearer ${keycloak.token}`;
      // console.log('Axios Interceptor: Keycloak token eklendi.'); // İsteğe bağlı loglama
    } else {
      // console.log('Axios Interceptor: Keycloak token bulunamadı, header eklenmedi.'); // İsteğe bağlı loglama
    }
    return config;
  },
  (error) => {
    console.error('Axios request interceptor hatası:', error);
    return Promise.reject(error);
  }
);

// Yanıt (Response) Interceptor'ı
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    // console.error('Axios response interceptor hatası:', error.response || error); // Daha detaylı loglama
    console.log('Axios response interceptor error object:', error); // Daha detaylı log
    if (error.response) {
      console.log('Axios response interceptor error.response.data:', error.response.data);
    } 
    // Token süresi dolmuşsa (401) ve Keycloak doğrulanmışsa token'ı yenilemeyi dene
    if (error.response && error.response.status === 401 && !originalRequest._retry && keycloak && keycloak.authenticated) {
      originalRequest._retry = true; // Tekrar deneme döngüsünü engelle
      try {
        console.log('Axios Interceptor: 401 alındı, Keycloak token yenileme deneniyor...');
        const refreshed = await keycloak.updateToken(30); // En az 5 saniye geçerli olsun
        if (refreshed) {
          console.log('Axios Interceptor: Keycloak token başarıyla yenilendi, orijinal istek tekrarlanıyor.');
          // Pinia store'daki token'ı da güncellemek iyi bir pratik olabilir (eğer store'da tutuyorsak)
          const authStore = useAuthStore();
          authStore.setKeycloakAuth(keycloak); // Bu, tokenParsed gibi şeyleri günceller

          // Orijinal isteğin header'ını yeni token ile güncelle
          if (keycloak.token) { // Yenilenmiş token'ın varlığını kontrol et
            originalRequest.headers['Authorization'] = `Bearer ${keycloak.token}`;
          }
          return apiClient(originalRequest); // Orijinal isteği tekrar gönder
        } else {
          // Token yenilenemedi (belki refresh token da geçersiz)
          console.warn('Axios Interceptor: Token yenilenemedi. Oturum sonlandırılıyor.');
          const authStore = useAuthStore();
          authStore.logout(); // Merkezi logout fonksiyonumuzu çağırıyoruz.
        }
      } catch (e) {
        console.error('Axios Interceptor: Token yenileme sırasında kritik hata. Oturum sonlandırılıyor.', e);
        const authStore = useAuthStore();
        authStore.logout(); // Hata durumunda da logout yap
        return Promise.reject(new Error('Oturum yenilenemedi veya sonlandı. Lütfen tekrar giriş yapın.'));
      }
    }
    return Promise.reject(error);
  }
);
// --- Axios Interceptor'lar Sonu ---


// Keycloak'u başlat ve sonra Vue uygulamasını mount et
initKeycloak({ onLoad: 'check-sso' }) // 
  .then((authenticated) => { // 
    const authStore = useAuthStore(); // 
    authStore.setKeycloakAuth(keycloak); // 

    app.use(router); // 
    app.use(vuetify); // YENİ IMPORT EDİLEN vuetify instance'ını kullan 
    app.mount('#app'); // 

    if (authenticated) { // 
        console.log("Main.js: Kullanıcı check-sso ile doğrulandı. Uygulama başlatıldı."); // 
    } else {
        console.log("Main.js: Kullanıcı check-sso ile doğrulanmadı. Uygulama başlatıldı. Login gerekebilir."); // 
    }
  })
  .catch((error) => {
    console.error("Main.js: Keycloak kritik başlatma hatası! Kimlik doğrulama olmadan devam ediliyor.", error); // 
    const authStore = useAuthStore(); 
    authStore.clearAuthState(); 

    app.use(router); 
    app.use(vuetify); // Hata durumunda bile Vuetify'ı kullanıma al
    app.mount('#app'); 
  });