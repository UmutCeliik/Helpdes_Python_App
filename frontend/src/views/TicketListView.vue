<template>
  <v-container fluid>
    <v-row align="center" class="mb-4">
      <v-col>
        <h1 class="text-h5 font-weight-medium">Destek Biletleri</h1>
      </v-col>
      <v-col class="text-right">
        <v-btn color="primary" to="/create-ticket" prepend-icon="mdi-plus-box">
          Yeni Bilet Oluştur
        </v-btn>
      </v-col>
    </v-row>

    <v-alert
        v-if="error"
        type="error"
        density="compact"
        variant="tonal"
        closable
        class="mb-4"
        @update:modelValue="clearError" 
    >
        {{ error }}
    </v-alert>

    <v-card elevation="2">
      <v-card-title class="d-flex align-center pe-2">
        Bilet Listesi
        <v-spacer></v-spacer>
        <v-text-field
            v-model="search"
            density="compact"
            label="Ara (Konu, ID...)"
            prepend-inner-icon="mdi-magnify"
            variant="outlined"
            flat
            hide-details
            single-line
        ></v-text-field>
      </v-card-title>

      <v-divider></v-divider>

      <v-data-table
        :headers="headers"
        :items="tickets" 
        :loading="isLoading"
        :search="search"
        item-value="id"
        class="elevation-0"
        hover
        loading-text="Biletler yükleniyor..."
        no-data-text="Gösterilecek bilet bulunamadı."
      >
        <template v-slot:item.id="{ item }">
          <span class="text-monospace">{{ item.id.substring(0, 8) }}</span>
        </template>

        <template v-slot:item.status="{ item }">
          <v-chip :color="getStatusColor(item.status)" size="small" label>{{ item.status }}</v-chip>
        </template>

        <template v-slot:item.created_at="{ item }">
          {{ formatDateTime(item.created_at) }}
        </template>

        <template v-slot:item.actions="{ item }">
          <v-icon small class="me-2" @click="viewTicket(item)">mdi-eye</v-icon>
        </template>

         <template v-slot:loading>
            <v-skeleton-loader type="table-row@5"></v-skeleton-loader>
         </template>

      </v-data-table>
    </v-card>

  </v-container>
</template>

<script>
// mapState ve mapActions importları kaldırıldı
import { ref, computed, onMounted } from 'vue';
import { useTicketStore } from '@/stores/ticketStore';
// import { useAuthStore } from '@/stores/auth'; // Şu an kullanılmıyor
import { useRouter } from 'vue-router';
// storeToRefs'i import et
import { storeToRefs } from 'pinia';

export default {
  name: 'TicketListView',
  setup() {
    const router = useRouter();
    const ticketStore = useTicketStore(); // Store instance'ını al
    const search = ref('');

    // --- Doğrudan Store Erişimi ---
    // State'i reaktif tutmak için storeToRefs kullanın
    const { tickets, isLoading, error } = storeToRefs(ticketStore);
    // Action'ları doğrudan store instance'ından alın
    const { fetchTickets } = ticketStore;

    // Hata mesajını temizlemek için fonksiyon
    const clearError = () => {
        ticketStore.error = null; // Doğrudan store state'ini güncelle
    };
    // --- Store Erişimi Sonu ---


    const headers = [
      { title: 'ID', key: 'id', align: 'start', sortable: false, width: '120px' },
      { title: 'Konu', key: 'title', align: 'start' },
      { title: 'Durum', key: 'status', align: 'center', width: '120px' },
      { title: 'Oluşturma Tarihi', key: 'created_at', align: 'start', width: '180px' },
      { title: 'Aksiyonlar', key: 'actions', sortable: false, align: 'center', width: '100px' },
    ];

    onMounted(() => {
      console.log("TicketListView mounted, fetching tickets..."); // Konsol logu eklendi
      fetchTickets(); // Store'dan alınan action'ı çağır
    });

    const getStatusColor = (status) => {
      if (status === 'Açık') return 'blue';
      if (status === 'İşlemde') return 'orange';
      if (status === 'Çözüldü') return 'green';
      return 'grey';
    };

    const formatDateTime = (dateTimeString) => {
      if (!dateTimeString) return '';
      try {
        const options = { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' };
        return new Date(dateTimeString).toLocaleString('tr-TR', options);
      } catch (e) { return dateTimeString; }
    };

    const viewTicket = (ticket) => {
      console.log("View ticket:", ticket.id);
      alert(`Bilet Detayları (${ticket.id.substring(0,8)}) henüz aktif değil.`);
    };

    // Template'de kullanılacak her şeyi return et
    return {
      search,
      headers,
      tickets, // storeToRefs sayesinde reaktif
      isLoading, // storeToRefs sayesinde reaktif
      error, // storeToRefs sayesinde reaktif
      fetchTickets, // Action
      clearError, // Hata temizleme metodu
      getStatusColor,
      formatDateTime,
      viewTicket,
    };
  }
};
</script>

<style scoped>
.v-data-table {
   border: 1px solid rgba(0, 0, 0, 0.12);
   border-radius: 4px;
}
.v-card-title .v-text-field {
  max-width: 300px;
}
</style>
