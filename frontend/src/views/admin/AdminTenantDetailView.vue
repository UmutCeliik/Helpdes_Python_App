<template>
  <v-container>
    <v-row align="center" class="mb-4">
      <v-col cols="auto">
        <v-btn icon="mdi-arrow-left" :to="{ name: 'AdminTenantList' }" title="Tenant Listesine Geri Dön"></v-btn>
      </v-col>
      <v-col>
        <h1 class="text-h5">Tenant Detayları</h1>
      </v-col>
    </v-row>

    <v-progress-linear indeterminate color="primary" v-if="tenantStore.isLoadingDetails"></v-progress-linear>
    
    <v-alert v-if="tenantStore.detailsError" type="error" density="compact" closable class="mb-4" @update:modelValue="tenantStore.detailsError = null">
      Detaylar alınırken hata oluştu: {{ tenantStore.detailsError }}
    </v-alert>

    <v-card v-if="tenant && !tenantStore.isLoadingDetails && !tenantStore.detailsError">
      <v-card-title class="pb-0">
        Tenant: {{ tenant.name }}
      </v-card-title>
      <v-card-subtitle class="pt-0">
        ID: {{ tenant.id }}
      </v-card-subtitle>

      <v-list density="compact">
        <v-list-item>
          <v-list-item-title class="font-weight-bold">Adı:</v-list-item-title>
          <v-list-item-subtitle>{{ tenant.name }}</v-list-item-subtitle>
        </v-list-item>
        
        <v-list-item>
          <v-list-item-title class="font-weight-bold">Keycloak Grup ID:</v-list-item-title>
          <v-list-item-subtitle style="font-family: monospace;">{{ tenant.keycloak_group_id }}</v-list-item-subtitle>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="font-weight-bold">Statü:</v-list-item-title>
          <v-list-item-subtitle>
            <v-chip :color="tenant.status === 'active' ? 'green' : 'orange'" size="small" label>
              {{ tenant.status === 'active' ? 'Aktif' : 'Pasif' }}
            </v-chip>
          </v-list-item-subtitle>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="font-weight-bold">Oluşturulma Tarihi:</v-list-item-title>
          <v-list-item-subtitle>{{ formatDateTime(tenant.created_at) }}</v-list-item-subtitle>
        </v-list-item>

        <v-list-item>
          <v-list-item-title class="font-weight-bold">Güncellenme Tarihi:</v-list-item-title>
          <v-list-item-subtitle>{{ formatDateTime(tenant.updated_at) }}</v-list-item-subtitle>
        </v-list-item>
      </v-list>

      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" variant="tonal" @click="refreshDetails">Yenile</v-btn>
      </v-card-actions>
    </v-card>
    
    <div v-if="!tenant && !tenantStore.isLoadingDetails && !tenantStore.detailsError" class="text-center mt-5">
        <p>Tenant bilgileri bulunamadı veya yüklenemedi.</p>
    </div>
  </v-container>
</template>

<script setup>
import { onMounted, computed, watch } from 'vue';
import { useRoute } from 'vue-router'; // useRoute import edildi
import { useTenantStore } from '@/stores/tenantStore';
import { storeToRefs } from 'pinia'; // storeToRefs reaktif state'ler için

const route = useRoute(); // Mevcut route objesini almak için
const tenantStore = useTenantStore();

// Store'dan reaktif state'leri al
const { currentTenantDetails: tenant, isLoadingDetails, detailsError } = storeToRefs(tenantStore);

// Route parametresinden tenant ID'sini al (bu reaktif olmayabilir, bu yüzden watch da kullanacağız)
const tenantIdFromRoute = computed(() => route.params.id);

// Tarih formatlama yardımcı fonksiyonu
function formatDateTime(dateTimeString) {
  if (!dateTimeString) return 'N/A';
  try {
    return new Date(dateTimeString).toLocaleString('tr-TR', {
      year: 'numeric', month: 'long', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  } catch (e) {
    return dateTimeString;
  }
}

async function fetchDetails(id) {
  if (id) {
    console.log(`AdminTenantDetailView: Fetching details for tenant ID: ${id}`);
    await tenantStore.fetchTenantDetails(id);
  }
}

// Component yüklendiğinde tenant detaylarını çek
onMounted(() => {
  fetchDetails(tenantIdFromRoute.value);
});

// Eğer kullanıcı aynı component üzerindeyken farklı bir tenant ID'sine giderse
// (örn: tarayıcıda ID'yi manuel değiştirirse veya ileride bir "sonraki/önceki tenant" butonu olursa)
// props.id (veya route.params.id) değiştiğinde veriyi yeniden çek.
watch(tenantIdFromRoute, (newId) => {
  fetchDetails(newId);
});

function refreshDetails() {
    fetchDetails(tenantIdFromRoute.value);
}
</script>

<style scoped>
.v-list-item-title {
  font-weight: bold;
}
.v-card-subtitle {
  margin-top: -4px; /* Başlık ve alt başlık arasını biraz daraltmak için */
  padding-bottom: 8px;
}
</style>