<template>
  <v-container fluid>
    <v-row justify="center">
      <v-col cols="12" md="8" lg="7">
        <v-btn
          variant="text"
          prepend-icon="mdi-arrow-left"
          @click="goBack"
          class="mb-4"
        >
          Kullanıcı Listesine Dön
        </v-btn>
        <h1 class="text-h5 font-weight-medium mb-6">Kullanıcı Düzenle</h1>

        <v-progress-linear
          indeterminate
          color="primary"
          v-if="isLoadingUserDetails"
          class="mb-4"
        ></v-progress-linear>

        <v-alert
          v-if="userDetailsError"
          type="error"
          density="compact"
          closable
          @update:modelValue="clearUserDetailsError"
          class="mb-4"
        >
          Kullanıcı bilgileri yüklenirken hata: {{ userDetailsError }}
        </v-alert>

        <v-card elevation="2" v-if="currentUserDetails && !isLoadingUserDetails && !userDetailsError">
          <v-card-text>
            <v-form @submit.prevent="handleUpdateUser" ref="editUserForm">
              <v-text-field
                v-model="editableUser.email"
                label="E-posta Adresi (Değiştirilemez)"
                type="email"
                variant="outlined"
                class="mb-4"
                prepend-inner-icon="mdi-email-outline"
                disabled
              ></v-text-field>

              <v-text-field
                v-model="editableUser.full_name"
                label="Tam Adı"
                variant="outlined"
                :rules="fullNameRules"
                required
                class="mb-4"
                prepend-inner-icon="mdi-account-outline"
                :disabled="isUpdatingUser"
              ></v-text-field>

              <v-select
                v-model="editableUser.roles"
                :items="availableKeycloakRoles"
                label="Keycloak Rolleri"
                multiple
                chips
                closable-chips
                variant="outlined"
                class="mb-4"
                prepend-inner-icon="mdi-shield-account-outline"
                :rules="rolesRules"
                :disabled="isUpdatingUser"
              ></v-select>

              <v-select
                v-model="editableUser.tenant_id"
                :items="tenantItems"
                item-title="name"
                item-value="id"
                label="Tenant (Şirket) Ata (Opsiyonel)"
                variant="outlined"
                clearable
                class="mb-4"
                prepend-inner-icon="mdi-domain"
                :loading="isLoadingTenants"
                :disabled="isUpdatingUser"
              ></v-select>

              <v-checkbox
                v-model="editableUser.is_active"
                label="Kullanıcı Aktif (Enabled)"
                color="primary"
                class="mb-4"
                :disabled="isUpdatingUser"
              ></v-checkbox>

              <v-alert
                v-if="updateUserError"
                type="error"
                density="compact"
                variant="tonal"
                closable
                class="mb-4"
                @update:modelValue="clearUpdateUserError"
              >
                {{ updateUserError }}
              </v-alert>

              <v-alert
                v-if="successMessage"
                type="success"
                density="compact"
                variant="tonal"
                closable
                class="mb-4"
                @update:modelValue="successMessage = ''"
              >
                {{ successMessage }}
              </v-alert>

              <v-btn
                :loading="isUpdatingUser"
                :disabled="isUpdatingUser"
                type="submit"
                color="primary"
                block
                size="large"
              >
                Değişiklikleri Kaydet
              </v-btn>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useUserManagementStore } from '@/stores/userManagementStore';
import { useTenantStore } from '@/stores/tenantStore';
import { storeToRefs } from 'pinia';

const route = useRoute();
const router = useRouter();
const userManagementStore = useUserManagementStore();
const tenantStore = useTenantStore();

// User Management Store'dan state ve action'lar
const { 
  currentUserDetails, 
  isLoadingUserDetails, 
  userDetailsError,
  isProcessingUser: isUpdatingUser, // isProcessingUser'ı isUpdatingUser olarak kullanabiliriz
  processUserError: updateUserError, // processUserError'ı updateUserError olarak kullanabiliriz
} = storeToRefs(userManagementStore);
const { fetchUserDetails, updateUser } = userManagementStore;

// Tenant Store'dan state ve action'lar
const { tenants, isLoading: isLoadingTenants } = storeToRefs(tenantStore);
const { fetchTenants } = tenantStore;

// Düzenlenebilir kullanıcı verileri için lokal ref
const editableUser = ref({
  email: '',
  full_name: '',
  roles: [],
  is_active: true,
  tenant_id: null,
});

const editUserForm = ref(null);
const successMessage = ref('');
const userId = ref(route.params.userId);

// Keycloak rolleri (AdminUserCreateView'den benzer)
const availableKeycloakRoles = ref(['customer-user', 'agent', 'helpdesk-admin']); // 

const tenantItems = computed(() => {
  return tenants.value.map(tenant => ({
    id: tenant.id,
    name: tenant.name,
  }));
});

// Form validasyon kuralları (AdminUserCreateView'den benzer)
const fullNameRules = [
  v => !!v || 'Tam ad gerekli.',
  v => (v && v.length >= 2) || 'Tam ad en az 2 karakter olmalı.',
];
const rolesRules = [
  v => (v && v.length > 0) || 'En az bir rol seçilmelidir.',
];

onMounted(async () => {
  userManagementStore.userDetailsError = null; // Önceki hataları temizle
  userManagementStore.processUserError = null;
  await fetchTenants(1, 1000); // Tenant'ları yükle
  if (userId.value) {
    await fetchUserDetails(userId.value);
    // currentUserDetails yüklendikten sonra editableUser'ı doldur
  }
});

// currentUserDetails değiştiğinde editableUser'ı güncelle
watch(currentUserDetails, (newDetails) => {
  if (newDetails) {
    editableUser.value = { 
      email: newDetails.email, // E-posta backend'den gelecek
      full_name: newDetails.full_name,
      // Backend'den gelen roller Keycloak rol adları olmalı
      roles: newDetails.roles || [], 
      is_active: newDetails.is_active,
      // Backend'den gelen tenant_id (company.id)
      tenant_id: newDetails.company ? newDetails.company.id : null, 
    };
  }
}, { immediate: true, deep: true });


const handleUpdateUser = async () => {
  successMessage.value = '';
  userManagementStore.processUserError = null;

  const { valid } = await editUserForm.value.validate();
  if (!valid) return;

  const userDataToUpdate = {
    full_name: editableUser.value.full_name,
    is_active: editableUser.value.is_active,
    roles: editableUser.value.roles,
    tenant_id: editableUser.value.tenant_id,
  };

  const success = await updateUser(userId.value, userDataToUpdate);

  if (success) {
    successMessage.value = 'Kullanıcı başarıyla güncellendi! Listeye yönlendiriliyorsunuz...';
    setTimeout(() => {
      router.push({ name: 'AdminUserList' });
    }, 2000);
  }
};

const clearUserDetailsError = () => {
  userManagementStore.userDetailsError = null;
};
const clearUpdateUserError = () => {
  userManagementStore.processUserError = null;
};

const goBack = () => {
  router.push({ name: 'AdminUserList' });
};

</script>

<style scoped>
/* Gerekirse özel stiller */
</style>