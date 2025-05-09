// frontend/src/services/keycloak.service.js
import Keycloak from 'keycloak-js';

// Keycloak yapılandırması .env dosyasından veya doğrudan girilebilir.
// Vite .env değişkenlerini import.meta.env üzerinden okur.
// Örneğin, frontend/.env dosyanızda VITE_KEYCLOAK_URL, VITE_KEYCLOAK_REALM, VITE_KEYCLOAK_CLIENT_ID tanımlayabilirsiniz.
// Şimdilik doğrudan girelim, isterseniz .env kullanımına geçebiliriz.

const keycloakConfig = {
    url: 'http://keycloak.cloudpro.com.tr', // Keycloak sunucu adresiniz
    realm: 'helpdesk-realm',
    clientId: 'helpdesk-frontend' // auth_service'in de kullandığı client ID
};

const keycloak = new Keycloak(keycloakConfig);

/**
 * Keycloak'u başlatır.
 * @param {object} options - Keycloak init seçenekleri (örn: onLoad, checkLoginIframe).
 * @returns {Promise<boolean>} Kimlik doğrulama başarılıysa true döner.
 */
const initKeycloak = (options = {}) => { // onAuthenticated parametresi kaldırıldı
    return keycloak.init({
        onLoad: options.onLoad || 'check-sso',
        silentCheckSsoRedirectUri: window.location.origin + '/silent-check-sso.html',
        pkceMethod: 'S256',
        ...options
    })
    .then((authenticated) => {
        if (authenticated) {
            console.log("Keycloak Service: Kullanıcı doğrulandı (initKeycloak).");
            // Token refresh mekanizmasını ayarla
            setInterval(() => {
                keycloak.updateToken(70).then((refreshed) => {
                    if (refreshed) {
                        console.log('Keycloak Service: Token başarıyla yenilendi.');
                        // Pinia store'daki token'ı güncellemek için event emit edilebilir veya
                        // authStore.setKeycloakAuth(keycloak) tekrar çağrılabilir.
                        // Şimdilik sadece logluyoruz. main.js'deki authStore zaten keycloak instance'ına sahip.
                    }
                }).catch(() => {
                    console.error('Keycloak Service: Token yenileme hatası.');
                    // Yenileme başarısızsa logout yapmayı veya kullanıcıyı bilgilendirmeyi düşünebilirsiniz.
                    // keycloak.logout(); // Otomatik logout için
                });
            }, 60000); // Her 60 saniyede bir kontrol et
        } else {
            console.warn("Keycloak Service: Kullanıcı doğrulanmadı (initKeycloak).");
        }
        return authenticated; // Promise'i boolean 'authenticated' değeriyle resolve et
    })
    .catch((error) => {
        console.error("Keycloak Service: Başlatma hatası (initKeycloak). Raw error:", error);
        // Hata detaylarını daha iyi loglamak için
        if (error && (error.error || error.error_description)) {
             console.error("Keycloak Service: Hata detayları:", error.error, error.error_description);
        }
        throw error; // Hatayı tekrar fırlat ki main.js'deki .catch() yakalayabilsin
    });
};

// `silent-check-sso.html` dosyasını public klasörüne eklemeyi unutmayın.
// İçeriği sadece `<html><body></body></html>` olabilir.
// Bu dosya, iframe aracılığıyla sessiz token yenileme ve SSO kontrolü için gereklidir.

export { keycloak, initKeycloak };