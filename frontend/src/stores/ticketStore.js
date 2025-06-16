import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import apiClient from '@/api/axios'; // Axios istemcimiz
import { useAuthStore } from './auth';

// Ticket Service URL'si (Proje planına göre Port 8000)
const TICKET_SERVICE_URL = 'http://127.0.0.1:8000';

export const useTicketStore = defineStore('tickets', () => {
  // --- State ---
  const tickets = ref([]); // Tüm bilet listesi
  const recentTickets = ref([]); // Dashboard'da gösterilecek son biletler
  const dashboardStats = ref({ // Dashboard özet istatistikleri
    open: 0,
    pending: 0,
    resolved: 0,
    total: 0,
  });
  const isLoading = ref(false); // Genel yüklenme durumu (liste için)
  const isCreating = ref(false); // Bilet oluşturma yüklenme durumu
  const error = ref(null); // Genel hata mesajı
  const createError = ref(null); // Bilet oluşturma hata mesajı
  const currentTicketDetails = ref(null); // Görüntülenen biletin detayları
  const isLoadingDetails = ref(false);      // Detay sayfası için yüklenme durumu
  const detailsError = ref(null);           // Detay sayfası için hata durumu

  // --- Actions ---

  async function fetchTickets() {
    isLoading.value = true;
    error.value = null;
    const authStore = useAuthStore();
    if (!authStore.isAuthenticated) {
        error.value = 'Veri çekmek için giriş yapmalısınız.';
        isLoading.value = false;
        tickets.value = [];
        recentTickets.value = [];
        dashboardStats.value = { open: 0, pending: 0, resolved: 0, total: 0 };
        return;
    }

    try {
      // URL'i Ingress path'ine göre göreceli olarak güncelliyoruz.
      // axios baseURL'i sayesinde bu, https://helpdesk.cloudpro.com.tr/api/tickets/ olarak tamamlanacaktır.
      const response = await apiClient.get('api/tickets/');
      const fetchedTickets = response.data;

      tickets.value = fetchedTickets;

      let openCount = 0;
      let pendingCount = 0;
      let resolvedCount = 0;
      fetchedTickets.forEach(ticket => {
        if (ticket.status === 'Açık') openCount++;
        else if (ticket.status === 'İşlemde') pendingCount++;
        else if (ticket.status === 'Çözüldü') resolvedCount++;
      });
      dashboardStats.value = { open: openCount, pending: pendingCount, resolved: resolvedCount, total: fetchedTickets.length };

      recentTickets.value = fetchedTickets.slice(0, 5);

      console.log("Bilet verileri başarıyla çekildi.");

    } catch (err) {
      console.error('Biletleri çekerken hata:', err.response || err.message || err);
      // ... (hata yönetimi kodunuz aynı kalabilir) ...
      if (err.response) {
          error.value = `Veri çekilemedi: ${err.response.data.detail || err.response.statusText}`;
      } else {
          error.value = 'Bilet verileri alınırken bir ağ sorunu oluştu. Lütfen Ingress bağlantınızı kontrol edin.';
      }
      tickets.value = [];
      recentTickets.value = [];
      dashboardStats.value = { open: 0, pending: 0, resolved: 0, total: 0 };
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Yeni bir destek bileti oluşturur.
   * @param {object} ticketData - { title: string, description: string }
   * @returns {Promise<boolean>} - Başarılı olursa true, olmazsa false döner.
   */
  async function createTicket(ticketData) {
    isCreating.value = true;
    createError.value = null;
    const authStore = useAuthStore();
    if (!authStore.isAuthenticated) {
      createError.value = 'Bilet oluşturmak için giriş yapmalısınız.';
      isCreating.value = false;
      return false;
    }

    try {
      console.log('Yeni bilet isteği gönderiliyor (store):', ticketData);
      // URL'i Ingress path'ine göre göreceli olarak güncelliyoruz.
      const response = await apiClient.post('api/tickets/', ticketData);

      if (response.status === 201) {
        console.log('Bilet başarıyla oluşturuldu (store):', response.data);
        const newTicket = response.data;
        tickets.value.unshift(newTicket);
        return true;
      } else {
        throw new Error(`Beklenmedik yanıt kodu: ${response.status}`);
      }
    } catch (err) {
      console.error('Bilet oluşturma hatası (store):', err.response || err);
      // ... (hata yönetimi kodunuz aynı kalabilir) ...
      if (err.response) {
        if (err.response.status === 401) {
          createError.value = 'Oturumunuz geçersiz veya süresi dolmuş. Lütfen tekrar giriş yapın.';
        } else if (err.response.status === 403) {
          createError.value = 'Bilet oluşturma yetkiniz yok.';
        } else if (err.response.data && err.response.data.detail) {
          createError.value = `Hata: ${err.response.data.detail}`;
        } else {
          createError.value = `Bilet oluşturulurken bir sunucu hatası oluştu (${err.response.status}).`;
        }
      } else {
        createError.value = 'Bilet oluşturulurken bir ağ hatası oluştu.';
      }
      return false;
    } finally {
      isCreating.value = false;
    }
  }
  async function fetchTicketDetails(ticketId) {
    isLoadingDetails.value = true;
    detailsError.value = null;
    currentTicketDetails.value = null;

    const authStore = useAuthStore();
    if (!authStore.isAuthenticated) {
      detailsError.value = 'Veri çekmek için giriş yapmalısınız.';
      isLoadingDetails.value = false;
      return;
    }

    try {
      console.log(`Bilet detayları çekiliyor: ${ticketId}`);
      // URL'i Ingress path'ine göre göreceli olarak güncelliyoruz.
      const response = await apiClient.get(`api/tickets/${ticketId}`);
      currentTicketDetails.value = response.data;
      console.log("Bilet detayları başarıyla çekildi:", response.data);
    } catch (err) {
      console.error(`Bilet detayları çekilirken hata (ID: ${ticketId}):`, err.response || err);
      detailsError.value = err.response?.data?.detail || 'Bilet detayları alınamadı.';
    } finally {
      isLoadingDetails.value = false;
    }
  }

  async function addComment(ticketId, commentData) {
    try {
      // URL'i Ingress path'ine göre göreceli olarak güncelliyoruz.
      const response = await apiClient.post(`api/tickets/${ticketId}/comments`, commentData);
      const newComment = response.data;

      if (currentTicketDetails.value && currentTicketDetails.value.comments) {
        currentTicketDetails.value.comments.push(newComment);
      }
      return true;
    } catch (err) {
      console.error("Yorum eklenirken hata:", err.response || err);
      return false;
    }
  }

  async function uploadAttachments(ticketId, files) {
    const formData = new FormData();
    files.forEach(file => {
      formData.append("files", file);
    });

    try {
      // URL'i Ingress path'ine göre göreceli olarak güncelliyoruz.
      const response = await apiClient.post(`api/tickets/${ticketId}/attachments`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      const newAttachments = response.data;

      if (currentTicketDetails.value && currentTicketDetails.value.attachments) {
        currentTicketDetails.value.attachments.push(...newAttachments);
      }
      return true;
    } catch (err) {
      console.error("Dosya yüklenirken hata:", err.response || err);
      return false;
    }
  }

  // Store'dan dışarıya açılacak state, getters ve actions
  return {
    tickets,
    recentTickets,
    dashboardStats,
    isLoading,
    isCreating,
    error,
    createError,
    fetchTickets,
    createTicket,
    currentTicketDetails,
    isLoadingDetails,
    detailsError,
    fetchTicketDetails,
    addComment,
    uploadAttachments,
  };
});
