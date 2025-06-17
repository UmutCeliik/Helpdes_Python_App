// frontend/src/stores/auth.js
import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { keycloak } from '@/services/keycloak.service'; // <-- GLOBAL KEYCLOAK INSTANCE'INI BURADA IMPORT EDİN
import router from '@/router'; // router'ı import ettiğinizden emin olun

// BU SATIRI TAMAMEN KALDIRIYORUZ, ÇÜNKÜ ARTIK GEREKLİ DEĞİL.
// const AUTH_SERVICE_BACKEND_URL = 'http://localhost:8002';

export const useAuthStore = defineStore('auth', () => {
  const storeKeycloakInstance = ref(null);
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

  function setKeycloakAuth(kcInstanceFromInit) {
    console.log("AuthStore: setKeycloakAuth ÇAĞRILDI. kcInstanceFromInit mevcut mu?:", !!kcInstanceFromInit);
    if (kcInstanceFromInit) {
      console.log("AuthStore: setKeycloakAuth içindeki kcInstanceFromInit.authenticated durumu:", kcInstanceFromInit.authenticated);
      console.log("AuthStore: kcInstanceFromInit.token var mı?:", !!kcInstanceFromInit.token);
    }

    storeKeycloakInstance.value = kcInstanceFromInit;

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
      isAuthenticated.value = false;
      userProfile.value = null;
      token.value = null;
      idToken.value = null;
      refreshToken.value = null;
      tokenParsed.value = null;
      idTokenParsed.value = null;
      console.warn("AuthStore: setKeycloakAuth içinde kcInstanceFromInit authenticated değil.");
    }
    isLoading.value = false;
    console.log("AuthStore: Keycloak auth state güncellendi. Store isAuthenticated:", isAuthenticated.value);
  }

  function clearAuthState() {
    storeKeycloakInstance.value = null;
    isAuthenticated.value = false;
    userProfile.value = null;
    token.value = null;
    idToken.value = null;
    refreshToken.value = null;
    tokenParsed.value = null;
    idTokenParsed.value = null;
    authError.value = null;
    isLoading.value = false;
    console.log("AuthStore: Auth state TEMİZLENDİ.");
  }

  async function login(options = {}) {
    if (keycloak && typeof keycloak.login === 'function') {
      try {
        isLoading.value = true;
        authError.value = null;
        console.log("AuthStore: keycloak.login() çağrılıyor...");

        const loginOptions = {
          redirectUri: window.location.origin + '/',
          ...options
        };
        
        console.log("AuthStore: keycloak.login() şu seçeneklerle çağrılıyor:", loginOptions);
        await keycloak.login(loginOptions);
      } catch (error) {
        console.error("AuthStore: Keycloak login başlatma hatası", error);
        authError.value = "Login işlemi başlatılamadı."; 
        isLoading.value = false;
      }
    } else {
      console.error("AuthStore: Global Keycloak instance veya login fonksiyonu bulunamadı.");
      authError.value = "Kimlik doğrulama servisi düzgün başlatılamamış.";
      isLoading.value = false;
    }
  }

  async function logout() {
    if (keycloak && typeof keycloak.logout === 'function') {
      try {
        console.log("AuthStore: keycloak.logout() çağrılıyor...");
        const logoutOptions = {
          redirectUri: window.location.origin + '/login',
        };
        await keycloak.logout(logoutOptions);
      } catch (error) {
        console.error("AuthStore: Keycloak logout hatası", error);
        clearAuthState();
        router.push('/login');
      }
    } else {
      console.error("AuthStore: Keycloak instance veya logout fonksiyonu bulunamadı.");
      clearAuthState();
      router.push('/login');
    }
  }

  return {
    storeKeycloakInstance,
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