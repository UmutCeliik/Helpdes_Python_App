// frontend/src/stores/userManagementStore.js
import { ref } from 'vue';
import { defineStore } from 'pinia';
import apiClient from '@/api/axios'; // Axios istemcimiz

// user_service'in çalıştığı portu ve base path'i.
// Bu bilgiyi bir config dosyasından veya .env'den almak daha iyi olabilir,
// şimdilik doğrudan tanımlıyoruz.
const USER_SERVICE_BASE_URL = 'http://localhost:8001'; // user_service port 8001'de çalışıyor

export const useUserManagementStore = defineStore('userManagement', () => {
  // --- State ---
  const users = ref([]); // Admin tarafından listelenecek kullanıcılar
  const totalUsers = ref(0); // Toplam kullanıcı sayısı (sayfalama için)
  const isLoadingUsers = ref(false); // Kullanıcı listesi yüklenirken
  const usersError = ref(null); // Kullanıcı listesi yükleme hatası

  const isDeletingUser = ref(false);
  const deleteUserError = ref(null);
  const isProcessingUser = ref(false); // Genel create/update loading flag
  const processUserError = ref(null);  // Genel create/update error message
  const createdUser = ref(null);     // Başarıyla oluşturulan kullanıcıyı tutmak için (opsiyonel)
  

  // --- Actions ---

  /**
   * user_service'ten kullanıcı listesini çeker (general-admin için).
   * @param {number} page - İstenen sayfa numarası (1'den başlar)
   * @param {number} limit - Sayfa başına kullanıcı sayısı
   */
  async function fetchUsers(page = 1, limit = 10) {
    isLoadingUsers.value = true;
    usersError.value = null;
    const skip = (page - 1) * limit;

    try {
      const url = `${USER_SERVICE_BASE_URL}/admin/users?skip=${skip}&limit=${limit}`;
      console.log('UserManagementStore: Requesting users from URL:', url);
      
      // apiClient (axios instance) Authorization header'ını otomatik ekleyecektir (main.js'deki interceptor sayesinde).
      const response = await apiClient.get(url);

      if (response.data && Array.isArray(response.data.items) && typeof response.data.total === 'number') {
        users.value = response.data.items;
        totalUsers.value = response.data.total;
        console.log('UserManagementStore: Users fetched successfully:', users.value.length, 'Total:', totalUsers.value);
      } else {
        console.error('UserManagementStore: Unexpected response format from /admin/users', response.data);
        users.value = [];
        totalUsers.value = 0;
        usersError.value = 'Kullanıcı verileri alınırken beklenmedik bir formatla karşılaşıldı.';
      }
    } catch (err) {
      console.error('UserManagementStore: Error fetching users:', err.response || err.message || err);
      let errorMessage = 'Kullanıcı listesi yüklenirken bir hata oluştu.';
      if (err.response && err.response.data && err.response.data.detail) {
        errorMessage = typeof err.response.data.detail === 'string' 
                       ? err.response.data.detail 
                       : JSON.stringify(err.response.data.detail);
      } else if (err.message) {
        errorMessage = err.message;
      }
      usersError.value = errorMessage;
      users.value = [];
      totalUsers.value = 0;
    } finally {
      isLoadingUsers.value = false;
    }
  }

  /**
   * Belirtilen ID'ye sahip kullanıcıyı user_service üzerinden siler.
   * @param {string} userId - Silinecek kullanıcının ID'si
   * @returns {Promise<boolean>} - Silme işlemi başarılıysa true, değilse false döner.
   */
  async function deleteUser(userId) {
    isDeletingUser.value = true;
    deleteUserError.value = null; // Önceki silme hatalarını temizle
    usersError.value = null; // Genel hatayı da temizleyebiliriz

    try {
      const url = `${USER_SERVICE_BASE_URL}/admin/users/${userId}`;
      console.log('UserManagementStore: Deleting user with ID:', userId, 'at URL:', url);
      
      await apiClient.delete(url); // Backend 204 No Content dönecek, response body'si olmayacak

      console.log('UserManagementStore: User deleted successfully from backend (ID):', userId);
      return true; // Başarılı
    } catch (err) {
      console.error('UserManagementStore: Error deleting user:', err.response || err.message || err);
      let errorMessage = 'Kullanıcı silinirken bir hata oluştu.';
      if (err.response && err.response.data && err.response.data.detail) {
        errorMessage = typeof err.response.data.detail === 'string' 
                       ? err.response.data.detail 
                       : JSON.stringify(err.response.data.detail);
      } else if (err.message) {
        errorMessage = err.message;
      }
      deleteUserError.value = errorMessage; // Silmeye özel hata state'ini ayarla
      usersError.value = errorMessage; // Genel hata state'ini de ayarlayabiliriz, component hangisini kullanıyorsa.
      return false; // Başarısız
    } finally {
      isDeletingUser.value = false;
    }
  }

  /**
   * Yeni bir kullanıcı oluşturur (general-admin için).
   * @param {object} userData - AdminUserCreateRequest Pydantic modeline uygun kullanıcı verileri
   * @returns {Promise<object|null>} - Başarılı olursa oluşturulan kullanıcı objesini, değilse null döner.
   */
  async function createUser(userData) {
    isProcessingUser.value = true;
    processUserError.value = null;
    createdUser.value = null;
    usersError.value = null; // Genel hatayı da temizle

    try {
      const url = `${USER_SERVICE_BASE_URL}/admin/users`;
      console.log('UserManagementStore: Creating user with data:', userData, 'at URL:', url);
      
      const response = await apiClient.post(url, userData);
      
      createdUser.value = response.data; // Backend user_models.User dönecek
      console.log('UserManagementStore: User created successfully:', createdUser.value);
      return createdUser.value; 
    } catch (err) {
      console.error('UserManagementStore: Error creating user:', err.response || err.message || err);
      let errorMessage = 'Kullanıcı oluşturulurken bir hata oluştu.';
      if (err.response && err.response.data && err.response.data.detail) {
        errorMessage = typeof err.response.data.detail === 'string' 
                       ? err.response.data.detail 
                       : JSON.stringify(err.response.data.detail);
      } else if (err.message) {
        errorMessage = err.message;
      }
      processUserError.value = errorMessage;
      usersError.value = errorMessage; // Genel hata için de set edebiliriz
      return null;
    } finally {
      isProcessingUser.value = false;
    }
  }

  return {
    // State
    users,
    totalUsers,
    isLoadingUsers,
    usersError,
    isDeletingUser,
    deleteUserError,
    isProcessingUser,
    processUserError,
    createdUser,
    // Actions
    fetchUsers,
    deleteUser,
    createUser,
  };
});