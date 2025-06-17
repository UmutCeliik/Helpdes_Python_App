// frontend/src/stores/tenantStore.js
import { ref } from 'vue';
import { defineStore } from 'pinia';
import apiClient from '@/api/axios'; // Axios istemcimiz

// BU SATIRI TAMAMEN KALDIRIYORUZ.
// const USER_SERVICE_BASE_URL = 'http://localhost:8001'; 

// Tenant endpoint'leri user-service altında olduğu için ana Ingress yolunu burada tanımlıyoruz.
const TENANT_API_PATH = 'api/users/admin/tenants';

export const useTenantStore = defineStore('tenants', () => {
  // State
  const tenants = ref([]);
  const totalTenants = ref(0);
  const isLoading = ref(false);
  const isCreating = ref(false);
  const isUpdating = ref(false);
  const error = ref(null);
  const createError = ref(null);
  const updateError = ref(null);
  const currentTenantDetails = ref(null);
  const isLoadingDetails = ref(false);
  const detailsError = ref(null);
  const isDeleting = ref(false);
  const deleteError = ref(null);


  // Actions
  async function fetchTenants(page = 1, limit = 10) {
    isLoading.value = true;
    error.value = null;
    const skip = (page - 1) * limit;

    try {
      // URL'i göreceli path olarak güncelliyoruz.
      const url = `${TENANT_API_PATH}?skip=${skip}&limit=${limit}`;
      console.log('Requesting tenants from URL:', url);

      const response = await apiClient.get(url);

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
      // Hata yönetimi kodunuz aynı kalabilir...
      error.value = 'Tenant verileri alınamadı. Lütfen ağ bağlantınızı veya Ingress ayarlarını kontrol edin.';
      tenants.value = []; 
      totalTenants.value = 0;
    } finally {
      isLoading.value = false;
    }
  }

  async function createTenant(tenantData) {
    isCreating.value = true;
    createError.value = null;
    error.value = null;

    try {
      // URL'i göreceli path olarak güncelliyoruz.
      const url = `${TENANT_API_PATH}`;
      console.log('Creating tenant at URL:', url, 'with data:', tenantData);
      const response = await apiClient.post(url, tenantData);

      console.log('Tenant created successfully:', response.data);
      await fetchTenants(); // Listeyi yenile
      return true;
    } catch (err) {
      console.error('createTenant error:', err.response || err.message || err);
      // Hata yönetimi kodunuz aynı kalabilir...
      createError.value = err.response?.data?.detail || 'Tenant oluşturulamadı.';
      return false;
    } finally {
      isCreating.value = false;
    }
  }

  async function updateTenant(tenantId, updateData) {
    isUpdating.value = true;
    updateError.value = null;
    error.value = null; 

    try {
      // URL'i göreceli path olarak güncelliyoruz.
      const url = `${TENANT_API_PATH}/${tenantId}`;
      console.log(`Updating tenant ${tenantId} at URL: ${url} with data:`, updateData);
      const response = await apiClient.patch(url, updateData);

      console.log('Tenant updated successfully:', response.data);
      await fetchTenants();
      return true;
    } catch (err) {
      console.error(`updateTenant error for ID ${tenantId}:`, err.response || err.message || err);
      // Hata yönetimi kodunuz aynı kalabilir...
      updateError.value = err.response?.data?.detail || 'Tenant güncellenemedi.';
      return false;
    } finally {
      isUpdating.value = false;
    }
  }

  async function fetchTenantDetails(companyId) {
    isLoadingDetails.value = true;
    detailsError.value = null;
    currentTenantDetails.value = null;

    try {
      // URL'i göreceli path olarak güncelliyoruz.
      const url = `${TENANT_API_PATH}/${companyId}`;
      console.log(`Fetching tenant details for ID ${companyId} from URL: ${url}`);
      const response = await apiClient.get(url);
      currentTenantDetails.value = response.data;
      console.log('Tenant details fetched:', currentTenantDetails.value);
    } catch (err) {
      console.error(`fetchTenantDetails error for ID ${companyId}:`, err.response || err.message || err);
      // Hata yönetimi kodunuz aynı kalabilir...
      detailsError.value = err.response?.data?.detail || 'Tenant detayları alınamadı.';
    } finally {
      isLoadingDetails.value = false;
    }
  }

  async function deleteTenant(tenantId) {
    isDeleting.value = true;
    deleteError.value = null;
    try {
      // URL'i göreceli path olarak güncelliyoruz.
      const url = `${TENANT_API_PATH}/${tenantId}`;
      console.log('TenantStore: Deleting tenant with ID:', tenantId, 'at URL:', url);
      await apiClient.delete(url);
      
      console.log('TenantStore: Tenant deleted successfully from backend.');
      await fetchTenants(1, 10);
      return true;
    } catch (err) {
      console.error('TenantStore: Error deleting tenant:', err.response || err.message || err);
      deleteError.value = err.response?.data?.detail || 'Tenant silinirken bir hata oluştu.';
      return false;
    } finally {
      isDeleting.value = false;
    }
  }

  return {
    tenants,
    totalTenants,
    isLoading,
    isCreating,
    isUpdating,
    error,
    createError,
    updateError,
    currentTenantDetails,
    isLoadingDetails,
    detailsError,
    isDeleting,
    deleteError,
    fetchTenants,
    createTenant,
    updateTenant,
    fetchTenantDetails,
    deleteTenant,
  };
});
