<template>
  <v-container fluid>
    <v-progress-linear
        indeterminate
        color="primary"
        v-if="isLoading"
        class="mb-4"
    ></v-progress-linear>

    <v-alert
        type="error"
        v-if="error"
        closable
        class="mb-4"
        @update:modelValue="error = null"
    >
      {{ error }}
    </v-alert>

    <div v-if="!isLoading && !error">
      <v-row>
        <v-col cols="12">
          <h1 class="text-h5 font-weight-medium mb-4">Ana Panel</h1>
        </v-col>

        <v-col cols="12" md="4">
          <v-card class="pa-3" elevation="2">
            <div class="d-flex align-center">
              <v-icon color="blue" size="x-large" class="mr-3">mdi-ticket-confirmation-outline</v-icon>
              <div>
                <div class="text-h6 font-weight-bold">{{ dashboardStats.open }}</div>
                <div class="text-caption">Açık Biletler</div>
              </div>
            </div>
          </v-card>
        </v-col>

        <v-col cols="12" md="4">
          <v-card class="pa-3" elevation="2">
            <div class="d-flex align-center">
              <v-icon color="orange" size="x-large" class="mr-3">mdi-clock-alert-outline</v-icon>
              <div>
                <div class="text-h6 font-weight-bold">{{ dashboardStats.pending }}</div>
                <div class="text-caption">İşlemde Olanlar</div>
              </div>
            </div>
          </v-card>
        </v-col>

        <v-col cols="12" md="4">
          <v-card class="pa-3" elevation="2">
            <div class="d-flex align-center">
              <v-icon color="green" size="x-large" class="mr-3">mdi-check-circle-outline</v-icon>
              <div>
                <div class="text-h6 font-weight-bold">{{ dashboardStats.resolved }}</div>
                <div class="text-caption">Çözülen Biletler</div>
              </div>
            </div>
          </v-card>
        </v-col>

        <v-col cols="12">
          <v-card elevation="2">
            <v-card-title>Son Biletler</v-card-title>
            <v-divider></v-divider>
             <v-card-text v-if="recentTickets.length === 0 && !isLoading">
                Gösterilecek bilet bulunamadı.
             </v-card-text>
            <v-table density="compact" v-else>
              <thead>
                <tr>
                  <th class="text-left">ID (Kısa)</th>
                  <th class="text-left">Konu</th>
                  <th class="text-left">Durum</th>
                  <th class="text-left">Oluşturma Tarihi</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="ticket in recentTickets" :key="ticket.id">
                  <td>{{ ticket.id.substring(0, 8) }}...</td>
                  <td>{{ ticket.title }}</td>
                  <td><v-chip :color="getStatusColor(ticket.status)" size="small">{{ ticket.status }}</v-chip></td>
                  <td>{{ formatDateTime(ticket.created_at) }}</td>
                </tr>
              </tbody>
            </v-table>
            <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn color="primary" variant="text" to="/tickets">Tüm Biletleri Gör</v-btn>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
    </div> </v-container>
</template>

<script>
// Script kısmı büyük ölçüde aynı kalıyor, sadece layout ile ilgili
// data (drawer) ve metodlar (handleLogout) kaldırıldı.
import { computed, onMounted } from 'vue'; // ref kaldırıldı
import { mapState, mapActions } from 'pinia';
// Auth store'u sadece kullanıcı adı için değil, belki başka kontroller için de tutabiliriz.
// import { useAuthStore } from '@/stores/auth';
import { useTicketStore } from '@/stores/ticketStore';

export default {
  name: 'DashboardView',
  // data bölümü kaldırıldı (drawer yok artık)
  computed: {
    // Auth Store'dan state map'leme (kullanıcı adı artık MainLayout'ta)
    // ...mapState(useAuthStore, ['user']),
    // userName() { ... } // Bu da MainLayout'a taşındı

    // Ticket Store'dan state map'leme (Aynı kalıyor)
    ...mapState(useTicketStore, ['recentTickets', 'dashboardStats', 'isLoading']),
     error: {
        get() {
            return useTicketStore().error;
        },
        set(value) {
            if (value === null) {
                useTicketStore().error = null;
            }
        }
     }
  },
  methods: {
    // Auth Store'dan action map'leme (logout MainLayout'ta)
    // ...mapActions(useAuthStore, ['logout']),
    // Ticket Store'dan action map'leme (Aynı kalıyor)
    ...mapActions(useTicketStore, ['fetchTickets']), // fetchDashboardData -> fetchTickets olmuştu

    // handleLogout() { ... } // MainLayout'a taşındı

    // getStatusColor ve formatDateTime metodları aynı kalıyor
    getStatusColor(status) {
      if (status === 'Açık') return 'blue';
      if (status === 'İşlemde') return 'orange';
      if (status === 'Çözüldü') return 'green';
      return 'grey';
    },
    formatDateTime(dateTimeString) {
      if (!dateTimeString) return '';
      try {
        const options = { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' };
        return new Date(dateTimeString).toLocaleString('tr-TR', options);
      } catch (e) { return dateTimeString; }
    }
  },
  mounted() {
    // Verileri çekme işlemi aynı kalıyor
    this.fetchTickets(); // fetchDashboardData -> fetchTickets olmuştu
    console.log("DashboardView (simplified) yüklendi, veri çekme işlemi başlatıldı.");
  }
};
</script>

<style scoped>
/* Bu bileşene özel stiller gerekirse buraya eklenebilir */
</style>
