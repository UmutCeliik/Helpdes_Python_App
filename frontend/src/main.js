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
import 'vuetify/styles'; // Vuetify temel stilleri
import { createVuetify } from 'vuetify'; // Vuetify oluşturucu
import * as components from 'vuetify/components'; // Tüm Vuetify bileşenleri
import * as directives from 'vuetify/directives'; // Tüm Vuetify direktifleri
import '@mdi/font/css/materialdesignicons.css'; // Material Design İkonları (Gerekli)

// Keycloak servisini import et
import { initKeycloak, keycloak } from './services/keycloak.service';

// Vuetify instance'ını oluştur
const vuetify = createVuetify({
  components, // Bileşenleri ekle
  directives, // Direktifleri ekle
  icons: {
    defaultSet: 'mdi', // Varsayılan ikon seti olarak mdi kullan
  },
  theme: {
    defaultTheme: 'dark', // 'light' 'dark'
    themes: {
      light: {
        colors: {
          primary: '#1976D2', // Örnek primary renk
          secondary: '#424242',
          accent: '#82B1FF',
          error: '#FF5252',
          info: '#2196F3',
          success: '#4CAF50',
          warning: '#FB8C00',
        },
      },
      // İsterseniz dark tema için de renkleri tanımlayabilirsiniz
      // dark: {
      //   colors: { ... }
      // }
    },
  },
});

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
          console.warn('Axios Interceptor: Keycloak token yenilenemedi (zaten geçerli olabilir veya refresh token süresi dolmuş). Logout tetikleniyor.');
          // keycloak.logout(); // Kullanıcıyı logout yap
        }
      } catch (e) {
        console.error('Axios Interceptor: Token yenileme sırasında kritik hata, logout.', e);
        // keycloak.logout(); // Hata durumunda logout yap
        return Promise.reject(new Error('Oturum yenilenemedi veya sonlandı. Lütfen tekrar giriş yapın.'));
      }
    }
    return Promise.reject(error);
  }
);
// --- Axios Interceptor'lar Sonu ---


// Keycloak'u başlat ve sonra Vue uygulamasını mount et
initKeycloak({ onLoad: 'check-sso' }) // initKeycloak'a sadece options objesini geçiyoruz
    .then((authenticated) => { // initKeycloak'tan dönen promise'i burada karşılıyoruz
        // Pinia store'a erişim için (app.use(pinia) çağrısından sonra olmalı)
        const authStore = useAuthStore();

        // authenticated durum ne olursa olsun setKeycloakAuth'u çağırıyoruz.
        // authStore bu duruma göre kendi iç state'ini ayarlayacak.
        // keycloak instance'ı global olarak keycloak.service.js'den import edildiği için
        // ve authStore içinde de bu global instance'a referans verilebileceği için
        // veya doğrudan keycloak objesini store'a set edebiliriz.
        authStore.setKeycloakAuth(keycloak); // keycloak instance'ını store'a iletiyoruz

        // Uygulamayı her zaman mount et
        // Router, store güncellendikten sonra kullanılmalı ki guard'lar doğru state'i görsün.
        app.use(router);
        app.use(vuetify);
        app.mount('#app');

        if (authenticated) {
            console.log("Main.js: Kullanıcı check-sso ile doğrulandı. Uygulama başlatıldı.");
        } else {
            console.log("Main.js: Kullanıcı check-sso ile doğrulanmadı. Uygulama başlatıldı. Login gerekebilir.");
            // Otomatik login'e yönlendirme burada yapılmıyor.
            // LoginView veya router guard'ları bu durumu ele alacak.
            // Örneğin, eğer router.currentRoute.value.meta.requiresAuth ise ve kullanıcı login değilse
            // router guard'ı login sayfasına yönlendirebilir veya authStore.login() çağırabilir.
        }
    })
    .catch((error) => {
        console.error("Main.js: Keycloak kritik başlatma hatası! Kimlik doğrulama olmadan devam ediliyor.", error);
        // Kritik bir hata durumunda bile uygulamayı mount etmeye çalışabiliriz,
        // ancak authStore'un doğru şekilde (kimlik doğrulanmamış olarak) ayarlandığından emin olalım.
        const authStore = useAuthStore(); // Pinia store'a erişim
        authStore.clearAuthState(); // Kimlik doğrulama state'ini temizle

        app.use(router); // Router'ı yine de kullanıma al
        app.use(vuetify);
        app.mount('#app'); // Uygulamayı mount et
    });