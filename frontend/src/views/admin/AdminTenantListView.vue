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

    <v-alert v-if="error" type="error" density="compact" closable class="mb-4" @update:modelValue="error = null">
      {{ error }}
    </v-alert>
    <v-alert v-if="updateError" type="error" density="compact" closable class="mb-4" @update:modelValue="updateError = null">
      Güncelleme Hatası: {{ updateError }}
    </v-alert>
    <v-alert v-if="deleteError" type="error" density="compact" closable class="mb-4" @update:modelValue="deleteError = null">
      Silme Hatası: {{ deleteError }}
    </v-alert>
     <v-alert v-if="actionSuccessMessage" type="success" density="compact" closable class="mb-4" @update:modelValue="actionSuccessMessage = ''">
      {{ actionSuccessMessage }}
    </v-alert>

    <v-card elevation="2">
      <v-card-title>
        Kayıtlı Tenantlar (Toplam: {{ totalTenants }})
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
          <tr v-if="isLoading">
             <td colspan="4" class="text-center pa-4">
                <v-progress-circular indeterminate color="primary"></v-progress-circular>
             </td>
          </tr>
          <tr v-else-if="!tenants || tenants.length === 0">
            <td colspan="4" class="text-center">Henüz kayıtlı tenant bulunmamaktadır.</td>
          </tr>
          <tr v-else v-for="tenant in tenants" :key="tenant.id">
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
                :loading="isUpdating && updatingTenantId === tenant.id"
                class="mr-2"
                variant="tonal"
              >
                {{ tenant.status === 'active' ? 'Pasif Yap' : 'Aktif Yap' }}
              </v-btn>
              
              <v-btn
                size="small"
                color="info"
                variant="text"
                icon="mdi-eye-outline"
                :to="{ name: 'AdminTenantDetail', params: { id: tenant.id } }"
                title="Tenant Detayları"
              ></v-btn>

              <v-btn
                size="small"
                color="error"
                variant="text"
                icon="mdi-delete-outline"
                @click="openDeleteDialog(tenant)"
                :disabled="isDeleting && tenantToDelete?.id === tenant.id"
                title="Tenant'ı Sil"
              ></v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>
  </v-container>

  <v-dialog v-model="deleteDialog" max-width="500px" persistent>
    <v-card v-if="tenantToDelete">
      <v-card-title class="text-h5 grey lighten-2" primary-title>
        Tenant Silme Onayı
      </v-card-title>
      <v-card-text class="py-4">
        <strong>{{ tenantToDelete.name }}</strong> adlı tenant'ı kalıcı olarak silmek istediğinizden emin misiniz? 
        <br><br>
        Bu işlem, Keycloak'taki ilişkili grubu da silecektir ve geri alınamaz.
      </v-card-text>
      <v-divider></v-divider>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn 
          color="blue-darken-1" 
          variant="text" 
          @click="closeDeleteDialog" 
          :disabled="isDeleting"
        >
          İptal
        </v-btn>
        <v-btn 
          color="red-darken-1" 
          variant="flat" 
          @click="handleDeleteTenant" 
          :loading="isDeleting"
        >
          Sil
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { useTenantStore } from '@/stores/tenantStore';
import { useNotificationStore } from '@/stores/notificationStore';
import { storeToRefs } from 'pinia';

const tenantStore = useTenantStore();
const notificationStore = useNotificationStore();

const { 
  tenants, 
  totalTenants,
  isLoading, 
  isUpdating, 
  isDeleting,
  error,
  updateError,
  deleteError
} = storeToRefs(tenantStore);

const { fetchTenants, updateTenant, deleteTenant } = tenantStore;

const actionSuccessMessage = ref('');
const updatingTenantId = ref(null);
const deleteDialog = ref(false);
const tenantToDelete = ref(null);

onMounted(() => {
  fetchTenants(1, 100);
});

async function toggleTenantStatus(tenant) {
  if (isUpdating.value && updatingTenantId.value === tenant.id) return; 
  updatingTenantId.value = tenant.id; 
  const newStatus = tenant.status === 'active' ? 'inactive' : 'active';
  
  const result = await updateTenant(tenant.id, { status: newStatus });
  if (result) {
    notificationStore.showNotification(`Tenant '${tenant.name}' statüsü başarıyla güncellendi.`, 'success');
  } else if (updateError.value) {
    notificationStore.showNotification(updateError.value, 'error');
  }
  updatingTenantId.value = null;
}

function openDeleteDialog(tenant) {
  tenantToDelete.value = tenant;
  tenantStore.deleteError = null;
  deleteDialog.value = true;
}

function closeDeleteDialog() {
  deleteDialog.value = false;
  setTimeout(() => { tenantToDelete.value = null; }, 300);
}

// BU FONKSİYON SADECE BİR KERE TANIMLANMIŞ OLMALI
async function handleDeleteTenant() {
  if (!tenantToDelete.value || !tenantToDelete.value.id) return;
  
  const deletedTenantName = tenantToDelete.value.name;
  const success = await deleteTenant(tenantToDelete.value.id);
  
  if (success) {
    notificationStore.showNotification(`'${deletedTenantName}' adlı tenant başarıyla silindi.`, 'success');
  } else if (deleteError.value) {
    notificationStore.showNotification(deleteError.value, 'error');
  }
  
  closeDeleteDialog();
}
</script>

<style scoped>
/* Sayfaya özel stiller */
.v-table th {
  font-weight: bold;
}
.v-btn + .v-btn {
  margin-left: 8px;
}
</style>