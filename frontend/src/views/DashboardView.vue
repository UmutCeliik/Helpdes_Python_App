<template>
  <v-container fluid>
    <v-progress-linear
      indeterminate
      color="primary"
      v-if="ticketStore.isLoading"
      class="mb-4"
    ></v-progress-linear>

    <v-alert
      type="error"
      v-if="ticketStore.error"
      closable
      class="mb-4"
      @update:modelValue="ticketStore.error = null"
      density="compact"
    >
      {{ ticketStore.error }}
    </v-alert>

    <div v-if="!ticketStore.isLoading && !ticketStore.error">
      <v-row align="center" class="mb-4">
        <v-col>
          <h1 class="text-h4 font-weight-medium">Ana Panel</h1>
          <p class="text-medium-emphasis">Hoş geldiniz, {{ userName }}.</p>
        </v-col>
        <v-col class="text-right">
           <v-chip color="primary" label>
              <v-icon start icon="mdi-account-tie-outline"></v-icon>
              Rol: {{ userPrimaryRole }}
           </v-chip>
        </v-col>
      </v-row>
      
      <v-row v-if="isAdminOrAgent">
        <v-col cols="12" md="4">
          <v-card class="pa-2" elevation="2" variant="tonal" color="info">
            <div class="d-flex align-center">
              <v-avatar color="info" rounded="lg" size="56" class="mr-4 elevation-4">
                <v-icon size="x-large">mdi-ticket-confirmation-outline</v-icon>
              </v-avatar>
              <div>
                <div class="text-h5 font-weight-bold">{{ ticketStore.dashboardStats.open }}</div>
                <div class="text-body-2">Açık Biletler</div>
              </div>
            </div>
          </v-card>
        </v-col>

        <v-col cols="12" md="4">
          <v-card class="pa-2" elevation="2" variant="tonal" color="warning">
            <div class="d-flex align-center">
              <v-avatar color="warning" rounded="lg" size="56" class="mr-4 elevation-4">
                 <v-icon size="x-large">mdi-clock-alert-outline</v-icon>
              </v-avatar>
              <div>
                <div class="text-h5 font-weight-bold">{{ ticketStore.dashboardStats.pending }}</div>
                <div class="text-body-2">İşlemde Olanlar</div>
              </div>
            </div>
          </v-card>
        </v-col>

        <v-col cols="12" md="4">
          <v-card class="pa-2" elevation="2" variant="tonal" color="success">
            <div class="d-flex align-center">
              <v-avatar color="success" rounded="lg" size="56" class="mr-4 elevation-4">
                <v-icon size="x-large">mdi-check-circle-outline</v-icon>
              </v-avatar>
              <div>
                <div class="text-h5 font-weight-bold">{{ ticketStore.dashboardStats.resolved }}</div>
                <div class="text-body-2">Çözülen Biletler</div>
              </div>
            </div>
          </v-card>
        </v-col>
      </v-row>

      <v-row v-if="isAdminOrAgent">
        <v-col cols="12">
          <v-card elevation="2">
            <v-card-title>
              <v-icon start icon="mdi-history"></v-icon>
              Son Biletler
            </v-card-title>
            <v-divider></v-divider>
             <v-card-text v-if="ticketStore.recentTickets.length === 0 && !ticketStore.isLoading">
                Gösterilecek bilet bulunamadı.
             </v-card-text>
            <v-data-table
              v-else
              :headers="ticketHeaders"
              :items="ticketStore.recentTickets"
              :items-per-page="5"
              density="compact"
              hover
            >
              <template v-slot:item.status="{ item }">
                <v-chip :color="getStatusColor(item.status)" size="small" label>{{ item.status }}</v-chip>
              </template>
              <template v-slot:item.created_at="{ item }">
                <span class="text-caption">{{ formatDateTime(item.created_at) }}</span>
              </template>
               <template v-slot:item.actions>
                <v-btn size="small" variant="text" color="grey">Detay</v-btn>
              </template>
              <template #bottom></template> </v-data-table>
          </v-card>
        </v-col>
      </v-row>

      <v-row v-if="isCustomer">
        <v-col cols="12" md="6">
            <v-card class="text-center pa-8" elevation="2" to="/create-ticket" color="primary" variant="tonal">
                 <v-icon size="x-large" class="mb-4">mdi-plus-box-outline</v-icon>
                 <h2 class="text-h6">Yeni Destek Bileti Oluştur</h2>
                 <p class="text-body-2 mt-2">Sorularınız veya sorunlarınız için bize ulaşın.</p>
            </v-card>
        </v-col>
        <v-col cols="12" md="6">
            <v-card class="text-center pa-8" elevation="2" to="/tickets">
                 <v-icon size="x-large" class="mb-4">mdi-ticket-outline</v-icon>
                 <h2 class="text-h6">Biletlerimi Görüntüle</h2>
                 <p class="text-body-2 mt-2">Mevcut destek biletlerinizin durumunu takip edin.</p>
            </v-card>
        </v-col>
      </v-row>

    </div>
  </v-container>
</template>

<script setup>
import { computed, onMounted } from 'vue';
import { useTicketStore } from '@/stores/ticketStore';
import { useAuthStore } from '@/stores/auth';

const ticketStore = useTicketStore();
const authStore = useAuthStore();

// State ve Getter'lar
const userName = computed(() => authStore.userProfile?.name || authStore.userProfile?.preferred_username || 'Kullanıcı');
const userRoles = computed(() => authStore.userRoles || []);

const isAdminOrAgent = computed(() => 
  userRoles.value.includes('general-admin') || 
  userRoles.value.includes('helpdesk-admin') || 
  userRoles.value.includes('agent')
);

const isCustomer = computed(() => 
  userRoles.value.includes('customer-user') && !isAdminOrAgent.value
);

// Kullanıcının en "önemli" rolünü göstermek için basit bir mantık
const userPrimaryRole = computed(() => {
  if (userRoles.value.includes('general-admin')) return 'Genel Yönetici';
  if (userRoles.value.includes('helpdesk-admin')) return 'Yardım Masası Yöneticisi';
  if (userRoles.value.includes('agent')) return 'Agent';
  if (userRoles.value.includes('customer-user')) return 'Müşteri';
  return 'Tanımsız';
});

// v-data-table için başlıklar
const ticketHeaders = [
  { title: 'ID', key: 'id', sortable: false, width: '120px' },
  { title: 'Konu', key: 'title', sortable: true },
  { title: 'Durum', key: 'status', align: 'center', width: '120px' },
  { title: 'Oluşturma Tarihi', key: 'created_at', sortable: true, width: '180px' },
  { title: 'Aksiyonlar', key: 'actions', sortable: false, align: 'center', width: '100px' },
];

// Methods
const getStatusColor = (status) => {
  if (status === 'Açık') return 'info';
  if (status === 'İşlemde') return 'warning';
  if (status === 'Çözüldü') return 'success';
  return 'grey';
};

const formatDateTime = (dateTimeString) => {
  if (!dateTimeString) return '';
  try {
    const options = { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' };
    return new Date(dateTimeString).toLocaleString('tr-TR', options);
  } catch (e) { return dateTimeString; }
};

// Lifecycle Hook
onMounted(() => {
  console.log("DashboardView yüklendi, bilet verileri çekiliyor...");
  ticketStore.fetchTickets();
});

</script>

<style scoped>
/* Kartların içindeki metinlerin hizalaması için ek stiller */
.v-card .v-avatar {
    align-self: center;
}
.v-card > div {
    width: 100%;
}
</style>