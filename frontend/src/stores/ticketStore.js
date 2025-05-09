import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import apiClient from '@/api/axios'; // Axios istemcimiz
import { useAuthStore } from './auth'; // Gerekirse auth store'a erişim için

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

  // --- Getters ---
  // (Şimdilik basit getter'lar yeterli)

  // --- Actions ---

  /**
   * Backend'den bilet listesini çeker ve state'i günceller.
   * Dashboard için hem istatistikleri hesaplar hem de son biletleri alır.
   * Bu fonksiyon hem dashboard hem de bilet listesi sayfası için kullanılabilir.
   */
  async function fetchTickets() { // fetchDashboardData'yı fetchTickets olarak yeniden adlandıralım
    isLoading.value = true;
    error.value = null;
    const authStore = useAuthStore();
    if (!authStore.isAuthenticated) {
        error.value = 'Veri çekmek için giriş yapmalısınız.';
        isLoading.value = false;
        tickets.value = []; // Hata durumunda listeyi temizle
        recentTickets.value = [];
        dashboardStats.value = { open: 0, pending: 0, resolved: 0, total: 0 };
        return;
    }

    try {
      // Backend'den tüm biletleri çek (limit olmadan veya yüksek bir limitle)
      // Sıralama için backend'e parametre eklemek idealdir (?sort=-created_at)
      const response = await apiClient.get(`${TICKET_SERVICE_URL}/tickets/`);
      const fetchedTickets = response.data;

      // State'i güncelle
      tickets.value = fetchedTickets; // Tam listeyi sakla

      // İstatistikleri Hesapla
      let openCount = 0;
      let pendingCount = 0;
      let resolvedCount = 0;
      fetchedTickets.forEach(ticket => {
        if (ticket.status === 'Açık') openCount++;
        else if (ticket.status === 'İşlemde') pendingCount++;
        else if (ticket.status === 'Çözüldü') resolvedCount++;
      });
      dashboardStats.value = { open: openCount, pending: pendingCount, resolved: resolvedCount, total: fetchedTickets.length };

      // Son Biletleri Ayıkla (Dashboard için)
      recentTickets.value = fetchedTickets.slice(0, 5);

      console.log("Bilet verileri başarıyla çekildi.");

    } catch (err) {
      console.error('Biletleri çekerken hata:', err.response || err.message || err);
      if (err.message && err.message.includes('Oturum sonlandı')) {
           error.value = err.message;
      } else if (err.response && err.response.data && err.response.data.detail) {
          error.value = `Veri çekilemedi: ${err.response.data.detail}`;
      } else {
          error.value = 'Bilet verileri alınırken bir sorun oluştu.';
      }
      tickets.value = []; // Hata durumunda temizle
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
      return false; // Başarısız
    }

    try {
      console.log('Yeni bilet isteği gönderiliyor (store):', ticketData);
      const response = await apiClient.post(`${TICKET_SERVICE_URL}/tickets/`, ticketData);

      if (response.status === 201) {
        console.log('Bilet başarıyla oluşturuldu (store):', response.data);
        // Başarılı oluşturma sonrası bilet listesini yenileyebiliriz
        // veya sadece yeni bileti listeye ekleyebiliriz (daha verimli)
        // Şimdilik sadece başarılı olduğunu belirtelim.
        // await fetchTickets(); // Listeyi yenilemek için (opsiyonel)
        return true; // Başarılı
      } else {
        // Beklenmedik başarılı durum kodu
        throw new Error(`Beklenmedik yanıt kodu: ${response.status}`);
      }
    } catch (err) {
      console.error('Bilet oluşturma hatası (store):', err.response || err);
      if (err.response) {
        if (err.response.status === 401) {
          createError.value = 'Oturumunuz geçersiz veya süresi dolmuş. Lütfen tekrar giriş yapın.';
          // Interceptor logout yapmalı
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
      return false; // Başarısız
    } finally {
      isCreating.value = false;
    }
  }


  // Store'dan dışarıya açılacak state, getters ve actions
  return {
    tickets,
    recentTickets,
    dashboardStats,
    isLoading,
    isCreating, // Yeni state
    error,
    createError, // Yeni state
    fetchTickets, // Yeniden adlandırıldı
    createTicket, // Yeni action
  };
});
