<template>
  <v-container>
    <v-row justify="space-between" align="center" class="mb-4">
      <v-col>
        <h1 class="text-h5">Tenant Yönetimi</h1>
      </v-col>
      <v-col class="text-right">
        <v-btn color="primary" :to="{ name: 'AdminTenantCreate' }" prepend-icon="mdi-plus-circle-outline">
          Yeni Tenant Oluştur
        </v-btn>
      </v-col>
    </v-row>

    <v-progress-linear indeterminate color="primary" v-if="tenantStore.isLoading"></v-progress-linear>
    
    <v-alert v-if="tenantStore.error" type="error" density="compact" closable class="mb-4" @update:modelValue="tenantStore.error = null">
      {{ tenantStore.error }}
    </v-alert>
    <v-alert v-if="tenantStore.updateError" type="error" density="compact" closable class="mb-4" @update:modelValue="tenantStore.updateError = null">
      Güncelleme Hatası: {{ tenantStore.updateError }}
    </v-alert>
     <v-alert v-if="actionSuccessMessage" type="success" density="compact" closable class="mb-4" @update:modelValue="actionSuccessMessage = ''">
      {{ actionSuccessMessage }}
    </v-alert>

    <v-card v-if="!tenantStore.isLoading && !tenantStore.error">
      <v-card-title>
        Kayıtlı Tenantlar (Toplam: {{ tenantStore.totalTenants }})
      </v-card-title>
      <v-divider></v-divider>
      
      <v-table density="compact" hover>
        <thead>
          <tr>
            <th class="text-left">Adı</th>
            <th class="text-left">Keycloak Grup ID</th>
            <th class="text-left">Statü</th>
            <th class="text-center">Aksiyonlar</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="tenantStore.tenants.length === 0">
            <td colspan="4" class="text-center">Henüz kayıtlı tenant bulunmamaktadır.</td>
          </tr>
          <tr v-for="tenant in tenantStore.tenants" :key="tenant.id">
            <td>{{ tenant.name }}</td>
            <td>
              <span style="font-family: monospace; font-size: 0.85em;">{{ tenant.keycloak_group_id }}</span>
            </td>
            <td>
              <v-chip :color="tenant.status === 'active' ? 'green' : 'orange'" size="small" label>
                {{ tenant.status === 'active' ? 'Aktif' : 'Pasif' }}
              </v-chip>
            </td>
            <td class="text-center">
              <v-btn
                size="small"
                :color="tenant.status === 'active' ? 'orange' : 'green'"
                @click="toggleTenantStatus(tenant)"
                :loading="tenantStore.isUpdating && updatingTenantId === tenant.id"
                class="mr-2"
                variant="tonal"
              >
                {{ tenant.status === 'active' ? 'Pasif Yap' : 'Aktif Yap' }}
              </v-btn>
              
              <v-btn
                size="small"
                color="info"
                variant="tonal"
                icon="mdi-eye-outline"
                :to="{ name: 'AdminTenantDetail', params: { id: tenant.id } }"
                title="Tenant Detayları"
              ></v-btn>
              </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>
  </v-container>
</template>

<script setup>
// ... (script setup kısmınız aynı kalıyor)
import { onMounted, ref } from 'vue';
import { useTenantStore } from '@/stores/tenantStore';

const tenantStore = useTenantStore();
const actionSuccessMessage = ref('');
const updatingTenantId = ref(null);

onMounted(() => {
  console.log('AdminTenantListView mounted, fetching tenants...');
  tenantStore.fetchTenants();
});

async function toggleTenantStatus(tenant) {
  if (tenantStore.isUpdating && updatingTenantId.value === tenant.id) return; 

  updatingTenantId.value = tenant.id; 
  actionSuccessMessage.value = ''; 
  const newStatus = tenant.status === 'active' ? 'inactive' : 'active';
  
  const result = await tenantStore.updateTenant(tenant.id, { status: newStatus });

  if (result) {
    actionSuccessMessage.value = `Tenant '${tenant.name}' statüsü başarıyla '${newStatus}' olarak güncellendi.`;
  }
  updatingTenantId.value = null; 
}
</script>

<style scoped>
/* Sayfaya özel stiller */
.v-table th {
  font-weight: bold;
}
/* Butonlar arasında biraz boşluk bırakmak için */
.v-btn + .v-btn {
  margin-left: 8px;
}
</style>