// frontend/src/stores/auth.js
import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { keycloak } from '@/services/keycloak.service'; // <-- GLOBAL KEYCLOAK INSTANCE'INI BURADA IMPORT EDİN

const AUTH_SERVICE_BACKEND_URL = 'http://localhost:8002';

export const useAuthStore = defineStore('auth', () => {
  const storeKeycloakInstance = ref(null); // Store içinde tutulan referans (opsiyonel, debug için)
  const isAuthenticated = ref(false);
  const userProfile = ref(null);
  const token = ref(null);
  const idToken = ref(null);
  const refreshToken = ref(null);
  const tokenParsed = ref(null);
  const idTokenParsed = ref(null);
  const isLoading = ref(true);
  const authError = ref(null);

  const isLoggedIn = computed(() => isAuthenticated.value);
  const user = computed(() => userProfile.value);
  const userRoles = computed(() => {
    if (tokenParsed.value && tokenParsed.value.roles) {
      return tokenParsed.value.roles;
    }
    if (tokenParsed.value && tokenParsed.value.realm_access && tokenParsed.value.realm_access.roles) {
      return tokenParsed.value.realm_access.roles;
    }
    return [];
  });
  const userId = computed(() => tokenParsed.value?.sub || null);
  const accessToken = computed(() => token.value);

  function setKeycloakAuth(kcInstanceFromInit) { // Bu, main.js'den gelen global keycloak instance'ıdır
    console.log("AuthStore: setKeycloakAuth ÇAĞRILDI. kcInstanceFromInit mevcut mu?:", !!kcInstanceFromInit);
    if (kcInstanceFromInit) {
      console.log("AuthStore: setKeycloakAuth içindeki kcInstanceFromInit.authenticated durumu:", kcInstanceFromInit.authenticated);
      console.log("AuthStore: kcInstanceFromInit.token var mı?:", !!kcInstanceFromInit.token);
    }

    storeKeycloakInstance.value = kcInstanceFromInit; // Global instance'ı store'da referans olarak sakla

    if (kcInstanceFromInit && kcInstanceFromInit.authenticated) {
      isAuthenticated.value = kcInstanceFromInit.authenticated;
      token.value = kcInstanceFromInit.token;
      idToken.value = kcInstanceFromInit.idToken;
      refreshToken.value = kcInstanceFromInit.refreshToken;
      tokenParsed.value = kcInstanceFromInit.tokenParsed;
      idTokenParsed.value = kcInstanceFromInit.idTokenParsed;

      kcInstanceFromInit.loadUserProfile()
        .then(profile => {
          userProfile.value = profile;
          console.log("AuthStore: Kullanıcı profili yüklendi", profile);
        })
        .catch(error => {
          console.error("AuthStore: Kullanıcı profili yüklenemedi", error);
          userProfile.value = {
            username: tokenParsed.value?.preferred_username,
            email: tokenParsed.value?.email,
            firstName: tokenParsed.value?.given_name,
            lastName: tokenParsed.value?.family_name,
          };
        });
      authError.value = null;
    } else {
      // Eğer init sonrası authenticated değilse, sadece ilgili bayrakları güncelle,
      // global keycloak instance hala login/logout için kullanılabilir durumda.
      isAuthenticated.value = false;
      userProfile.value = null;
      token.value = null;
      idToken.value = null;
      refreshToken.value = null;
      tokenParsed.value = null;
      idTokenParsed.value = null;
      // authError.value = null; // Eski bir hatayı temizlemeyebiliriz, kullanıcı görmeli
      console.warn("AuthStore: setKeycloakAuth içinde kcInstanceFromInit authenticated değil.");
    }
    isLoading.value = false; // Keycloak init veya update tamamlandı
    console.log("AuthStore: Keycloak auth state güncellendi. Store isAuthenticated:", isAuthenticated.value);
  }

  function clearAuthState() { // Bu fonksiyon logout sonrası veya kritik hatalarda çağrılabilir
    storeKeycloakInstance.value = null; // Sadece store'daki referansı temizle
    isAuthenticated.value = false;
    userProfile.value = null;
    token.value = null;
    idToken.value = null;
    refreshToken.value = null;
    tokenParsed.value = null;
    idTokenParsed.value = null;
    authError.value = null;
    isLoading.value = false; // Genellikle logout bir async işlem değildir, ama init için true idi
    console.log("AuthStore: Auth state TEMİZLENDİ.");
  }

 // frontend/src/stores/auth.js
async function login(options = {}) {
  // Doğrudan import edilen global 'keycloak' nesnesini kullan
  if (keycloak && typeof keycloak.login === 'function') {
    try {
      isLoading.value = true;
      authError.value = null; // Önceki hataları temizle
      console.log("AuthStore: keycloak.login() çağrılıyor...");

      const loginOptions = {
        // redirectUri olarak uygulamanın kökünü kullanın.
        // Bu URI'nin Keycloak client'ınızdaki "Valid Redirect URIs" listesinde olması gerekir.
        // Örneğin: http://localhost:5173/
        // Sizin paylaştığınız ekran görüntüsünde http://localhost:5173/ ve http://localhost:5173/* zaten vardı.
        redirectUri: window.location.origin + '/',
        ...options
      };
      
      console.log("AuthStore: keycloak.login() şu seçeneklerle çağrılıyor:", loginOptions);
      await keycloak.login(loginOptions);
      // Tarayıcı Keycloak'a yönlenir. Bu satırdan sonraki kod hemen çalışmayabilir.
    } catch (error) {
      console.error("AuthStore: Keycloak login başlatma hatası", error);
      // Hata mesajını burada "Login işlemi başlatılamadı." olarak set ediyorduk, bu doğru.
      authError.value = "Login işlemi başlatılamadı."; 
      isLoading.value = false;
    }
  } else {
    console.error("AuthStore: Global Keycloak instance veya login fonksiyonu bulunamadı.");
    authError.value = "Kimlik doğrulama servisi düzgün başlatılamamış.";
    isLoading.value = false;
  }
}

  async function logout(options = {}) {
    // Doğrudan import edilen global 'keycloak' nesnesini kullan
    if (keycloak && typeof keycloak.logout === 'function') {
      try {
        isLoading.value = true; // Opsiyonel
        authError.value = null;
        console.log("AuthStore: keycloak.logout() çağrılıyor...");
        await keycloak.logout(options);
        // Tarayıcı logout için Keycloak'a yönlenir ve sonra geri gelir.
        // Geri dönüşte check-sso çalışır, setKeycloakAuth çağrılır ve isAuthenticated false olur.
        // clearAuthState() doğrudan burada çağrılabilir veya setKeycloakAuth'un false durumuna bırakılabilir.
        // Şimdilik clearAuthState() çağırmayalım, setKeycloakAuth halletsin.
      } catch (error) {
        console.error("AuthStore: Keycloak logout hatası", error);
        authError.value = "Logout işlemi başarısız.";
        isLoading.value = false;
      }
    } else {
      console.error("AuthStore: Global Keycloak instance veya logout fonksiyonu bulunamadı.");
      authError.value = "Kimlik doğrulama servisi düzgün başlatılamamış.";
      isLoading.value = false;
    }
  }

  return {
    storeKeycloakInstance, // Bu store'daki referans
    isAuthenticated,
    isLoggedIn,
    user,
    userRoles,
    userId,
    accessToken,
    token,
    idToken,
    refreshToken,
    tokenParsed,
    idTokenParsed,
    isLoading,
    authError,
    setKeycloakAuth,
    login,
    logout,
    clearAuthState,
  };
});