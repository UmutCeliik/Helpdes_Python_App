// frontend/src/stores/tenantStore.js
import { ref } from 'vue';
import { defineStore } from 'pinia';
import apiClient from '@/api/axios'; // Axios istemcimiz
// user_service'in çalıştığı portu ve base path'i bilmemiz gerekiyor.
// user_service (admin endpoint'leri içeriyor) port 8001'de çalışıyor.
const USER_SERVICE_BASE_URL = 'http://localhost:8001'; 

export const useTenantStore = defineStore('tenants', () => {
  // State
  const tenants = ref([]);
  const totalTenants = ref(0);
  const isLoading = ref(false); // Genel yüklenme (listeleme için)
  const isCreating = ref(false); // Oluşturma için ayrı bir yüklenme durumu
  const error = ref(null); // Genel hata
  const createError = ref(null); // Oluşturma hatası
  const isUpdating = ref(false); // Güncelleme için yüklenme durumu
  const updateError = ref(null); // Güncelleme hatası
  const currentTenantDetails = ref(null); // Tek bir tenant'ın detayları için
  const isLoadingDetails = ref(false); // Detay yükleme durumu için
  const detailsError = ref(null); // Detay alma hatası için

  // Actions
  async function fetchTenants(page = 1, limit = 10) { // skip yerine page alıp skip'i hesaplayabiliriz
    isLoading.value = true;
    error.value = null;
    const skip = (page - 1) * limit; // Sayfa numarasından skip değerini hesapla

    try {
      // --- URL OLUŞTURMA KISMINI DÜZELTİN ---
      // Template literal (backtick ``) kullanarak değişkenleri doğru yerleştirin
      const url = `${USER_SERVICE_BASE_URL}/admin/tenants?skip=${skip}&limit=${limit}`;
      console.log('Requesting tenants from URL:', url); // Oluşturulan URL'i loglayın

      const response = await apiClient.get(url);
      // --- URL OLUŞTURMA KISMI DÜZELTİLDİ ---

      if (response.data && Array.isArray(response.data.items) && typeof response.data.total === 'number') {
        tenants.value = response.data.items;
        totalTenants.value = response.data.total;
        console.log('Tenants fetched:', tenants.value, 'Total:', totalTenants.value);
      } else {
        tenants.value = [];
        totalTenants.value = 0;
        console.error('fetchTenants: Unexpected response format', response.data);
        error.value = 'Tenant verileri alınırken beklenmedik bir formatla karşılaşıldı.';
      }
    } catch (err) {
      console.error('fetchTenants error:', err.response || err.message || err);
      let errorMessage = 'Tenant verileri alınamadı.';
      if (err.response && err.response.data && err.response.data.detail) {
        errorMessage = typeof err.response.data.detail === 'string' 
                       ? err.response.data.detail 
                       : JSON.stringify(err.response.data.detail);
      } else if (err.message) {
        errorMessage = err.message;
      }
      error.value = errorMessage;
      tenants.value = []; 
      totalTenants.value = 0;
    } finally {
      isLoading.value = false;
    }
  }

  async function createTenant(tenantData) { // tenantData bir obje olacak, örn: { name: 'Yeni Tenant Adı' }
    isCreating.value = true;
    createError.value = null; // Önceki oluşturma hatalarını temizle
    error.value = null; // Genel hatayı da temizleyebiliriz

    try {
      const url = `${USER_SERVICE_BASE_URL}/admin/tenants`;
      console.log('Creating tenant at URL:', url, 'with data:', tenantData);
      // apiClient (axios instance) Authorization header'ını otomatik ekleyecektir.
      const response = await apiClient.post(url, tenantData);

      console.log('Tenant created successfully:', response.data);
      // Başarılı oluşturma sonrası tenant listesini yenileyebiliriz.
      // Veya kullanıcıyı direkt listeleme sayfasına yönlendirip orada yenilenmesini sağlayabiliriz.
      // Şimdilik sadece başarılı olduğunu belirtelim, UI yönlendirme yapacak.
      await fetchTenants(); // Listeyi yenile
      return true; // Başarı durumunu döndür
    } catch (err) {
      console.error('createTenant error:', err.response || err.message || err);
      let errorMessage = 'Tenant oluşturulamadı.';
      if (err.response && err.response.data && err.response.data.detail) {
        errorMessage = typeof err.response.data.detail === 'string' 
                       ? err.response.data.detail 
                       : JSON.stringify(err.response.data.detail);
      } else if (err.message) {
        errorMessage = err.message;
      }
      createError.value = errorMessage; // Oluşturma hatasını ayarla
      return false; // Başarısızlık durumunu döndür
    } finally {
      isCreating.value = false;
    }
  }
  // --- YENİ EKlenen createTenant ACTION'I SONU ---

  async function updateTenant(tenantId, updateData) { // updateData bir obje olacak, örn: { status: 'inactive' } veya { name: 'Yeni Ad', status: 'active'}
    console.log('[tenantStore] updateTenant action started. Tenant ID:', tenantId, 'Update Data:', updateData);
    isUpdating.value = true;
    updateError.value = null;
    error.value = null; 

    try {
      const url = `${USER_SERVICE_BASE_URL}/admin/tenants/${tenantId}`;
      console.log(`Updating tenant ${tenantId} at URL: ${url} with data:`, updateData);
      const response = await apiClient.patch(url, updateData); // PATCH metodu kullanıyoruz

      console.log('Tenant updated successfully:', response.data);
      // Başarılı güncelleme sonrası listedeki ilgili tenant'ı güncelleyebiliriz
      // veya tüm listeyi yeniden çekebiliriz. Şimdilik listeyi yeniden çekelim.
      await fetchTenants(); // Güncel listeyi al
      return true;
    } catch (err) {
      console.error(`updateTenant error for ID ${tenantId}:`, err.response || err.message || err);
      let errorMessage = 'Tenant güncellenemedi.';
      if (err.response && err.response.data && err.response.data.detail) {
        errorMessage = typeof err.response.data.detail === 'string' 
                       ? err.response.data.detail 
                       : JSON.stringify(err.response.data.detail);
      } else if (err.message) {
        errorMessage = err.message;
      }
      updateError.value = errorMessage;
      return false;
    } finally {
      isUpdating.value = false;
    }
  }

  async function fetchTenantDetails(companyId) {
    isLoadingDetails.value = true;
    detailsError.value = null;
    currentTenantDetails.value = null; // Önceki detayı temizle

    try {
      const url = `${USER_SERVICE_BASE_URL}/admin/tenants/${companyId}`;
      console.log(`Fetching tenant details for ID ${companyId} from URL: ${url}`);
      const response = await apiClient.get(url);
      currentTenantDetails.value = response.data; // Yanıt doğrudan tenant objesini içermeli
      console.log('Tenant details fetched:', currentTenantDetails.value);
    } catch (err) {
      console.error(`fetchTenantDetails error for ID ${companyId}:`, err.response || err.message || err);
      let errorMessage = 'Tenant detayları alınamadı.';
      if (err.response && err.response.data && err.response.data.detail) {
         errorMessage = typeof err.response.data.detail === 'string' 
                       ? err.response.data.detail 
                       : JSON.stringify(err.response.data.detail);
      } else if (err.message) {
        errorMessage = err.message;
      }
      detailsError.value = errorMessage;
    } finally {
      isLoadingDetails.value = false;
    }
  }

  return {
    tenants,
    totalTenants,
    isLoading,
    error,
    fetchTenants,
    isCreating,
    createError,
    createTenant,
    isUpdating,
    updateError,
    updateTenant,
    currentTenantDetails,
    isLoadingDetails,
    detailsError,
    fetchTenantDetails,
  };
});