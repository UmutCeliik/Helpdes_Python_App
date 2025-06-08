// frontend/src/views/admin/AdminTenantDetailView.vue
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

    <v-alert v-if="updateSuccessMessage" type="success" density="compact" closable class="mb-4" @update:modelValue="updateSuccessMessage = ''">
      {{ updateSuccessMessage }}
    </v-alert>
    <v-alert v-if="tenantStore.updateError" type="error" density="compact" closable class="mb-4" @update:modelValue="tenantStore.updateError = null">
      Güncelleme sırasında hata: {{ tenantStore.updateError }}
    </v-alert>

    <v-card v-if="tenant && !tenantStore.isLoadingDetails && !tenantStore.detailsError">
      <v-card-title class="pb-0 d-flex justify-space-between align-center">
        <span>Tenant: {{ tenant.name }}</span>
        <v-btn v-if="!editMode" color="info" variant="tonal" size="small" @click="toggleEditMode">
          <v-icon left>mdi-pencil</v-icon>
          Adı Düzenle
        </v-btn>
      </v-card-title>
      <v-card-subtitle class="pt-0">
        ID: {{ tenant.id }}
      </v-card-subtitle>

      <v-list density="compact">
        <v-list-item>
          <v-list-item-title class="font-weight-bold">Adı:</v-list-item-title>
          <v-list-item-subtitle v-if="!editMode">{{ tenant.name }}</v-list-item-subtitle>
          <v-form v-else @submit.prevent="handleNameUpdate" ref="tenantNameForm">
            <v-text-field
              v-model="editableTenantName"
              label="Yeni Tenant Adı"
              :rules="tenantNameRules"
              variant="outlined"
              density="compact"
              class="mt-2"
              :disabled="tenantStore.isUpdating"
              autofocus
            ></v-text-field>
            <div class="mt-2">
              <v-btn 
                color="primary" 
                type="submit" 
                class="mr-2"
                :loading="tenantStore.isUpdating"
                size="small"
              >Kaydet</v-btn>
              <v-btn 
                variant="tonal" 
                @click="cancelEditMode"
                :disabled="tenantStore.isUpdating"
                size="small"
              >İptal</v-btn>
            </div>
          </v-form>
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
        <v-btn color="primary" variant="text" @click="refreshDetails" :disabled="editMode">Yenile</v-btn>
      </v-card-actions>
    </v-card>
    
    <div v-if="!tenant && !tenantStore.isLoadingDetails && !tenantStore.detailsError" class="text-center mt-5">
        <p>Tenant bilgileri bulunamadı veya yüklenemedi.</p>
    </div>
  </v-container>
</template>

<script setup>
import { onMounted, computed, watch, ref } from 'vue'; // ref eklendi
import { useRoute } from 'vue-router';
import { useTenantStore } from '@/stores/tenantStore';
import { storeToRefs } from 'pinia';

const route = useRoute();
const tenantStore = useTenantStore();

const { 
  currentTenantDetails: tenant, 
  isLoadingDetails, 
  detailsError,
  isUpdating, // tenantStore'dan isUpdating (veya benzeri) state'i
  updateError  // tenantStore'dan updateError (veya benzeri) state'i
} = storeToRefs(tenantStore);

const editMode = ref(false);
const editableTenantName = ref('');
const tenantNameForm = ref(null); // Form referansı
const updateSuccessMessage = ref('');

const tenantIdFromRoute = computed(() => route.params.id);

function formatDateTime(dateTimeString) { /* ... (öncekiyle aynı) ... */ 
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
    updateSuccessMessage.value = ''; // Başarı mesajını temizle
    tenantStore.updateError = null;  // Önceki güncelleme hatalarını temizle
    await tenantStore.fetchTenantDetails(id);
  }
}

onMounted(() => {
  fetchDetails(tenantIdFromRoute.value);
});

watch(tenantIdFromRoute, (newId, oldId) => {
  if (newId !== oldId) {
    editMode.value = false; // Tenant değişirse düzenleme modundan çık
    fetchDetails(newId);
  }
});

watch(tenant, (newTenant) => {
  if (newTenant && !editMode.value) { // Sadece editMode kapalıyken ve tenant varsa senkronize et
    editableTenantName.value = newTenant.name;
  }
});

const tenantNameRules = [
  v => !!v || 'Tenant adı gerekli.',
  v => (v && v.length >= 2) || 'Tenant adı en az 2 karakter olmalı.',
  v => (v && v.length <= 255) || 'Tenant adı en fazla 255 karakter olabilir.',
];

function toggleEditMode() {
  editMode.value = !editMode.value;
  if (editMode.value && tenant.value) {
    editableTenantName.value = tenant.value.name; // Düzenleme moduna geçerken mevcut adı al
    updateSuccessMessage.value = ''; // Başarı mesajını temizle
    tenantStore.updateError = null;  // Hata mesajını temizle
  }
}

function cancelEditMode() {
  editMode.value = false;
  if (tenant.value) {
    editableTenantName.value = tenant.value.name; // İptal edince orijinal ada geri dön
  }
  tenantStore.updateError = null; // Hata mesajını temizle
}

async function handleNameUpdate() {
  if (!tenant.value || !tenant.value.id) return;
  
  const { valid } = await tenantNameForm.value.validate();
  if (!valid) return;

  updateSuccessMessage.value = '';
  tenantStore.updateError = null;

  const success = await tenantStore.updateTenant(tenant.value.id, { name: editableTenantName.value });

  if (success) {
    updateSuccessMessage.value = `Tenant adı başarıyla '${editableTenantName.value}' olarak güncellendi.`;
    // fetchDetails(tenant.value.id); // Veriyi yeniden çekerek store ve `tenant` ref'ini güncelle
    // VEYA store'daki updateTenant zaten currentTenantDetails'i güncelliyorsa gerek yok.
    // Şimdilik store'un güncellediğini varsayalım, fetchTenantDetails() bu işi yapacak.
    await fetchDetails(tenant.value.id); // Detayları yeniden çekerek formu ve başlığı güncelle
    editMode.value = false; 
  }
  // Hata mesajı zaten tenantStore.updateError üzerinden gösterilecek
}

function refreshDetails() {
  if (!editMode.value) { // Sadece düzenleme modunda değilsek yenile
     fetchDetails(tenantIdFromRoute.value);
  }
}
</script>

<style scoped>
.v-list-item-title {
  font-weight: bold;
}
.v-card-subtitle {
  margin-top: -4px;
  padding-bottom: 8px;
}
</style>