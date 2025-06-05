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
        <h1 class="text-h5 font-weight-medium mb-6">Yeni Kullanıcı Oluştur</h1>
        <v-card elevation="2">
          <v-card-text>
            <v-form @submit.prevent="handleCreateUser" ref="createUserForm">
              <v-text-field
                v-model="email"
                label="E-posta Adresi (Kullanıcı Adı)"
                type="email"
                variant="outlined"
                :rules="emailRules"
                required
                class="mb-4"
                prepend-inner-icon="mdi-email-outline"
                :disabled="isProcessingUser"
              ></v-text-field>

              <v-text-field
                v-model="fullName"
                label="Tam Adı"
                variant="outlined"
                :rules="fullNameRules"
                required
                class="mb-4"
                prepend-inner-icon="mdi-account-outline"
                :disabled="isProcessingUser"
              ></v-text-field>

              <v-text-field
                v-model="password"
                label="Başlangıç Şifresi"
                type="password"
                variant="outlined"
                :rules="passwordRules"
                required
                class="mb-4"
                prepend-inner-icon="mdi-lock-outline"
                :disabled="isProcessingUser"
              ></v-text-field>

              <v-select
                v-model="selectedRoles"
                :items="availableKeycloakRoles"
                label="Keycloak Rolleri"
                multiple
                chips
                closable-chips
                variant="outlined"
                class="mb-4"
                prepend-inner-icon="mdi-shield-account-outline"
                :rules="rolesRules"
                :disabled="isProcessingUser"
              ></v-select>
              
              <v-select
                v-model="selectedTenantId"
                :items="tenantItems"
                item-title="name"
                item-value="id"
                label="Tenant (Şirket) Ata (Opsiyonel)"
                variant="outlined"
                clearable
                class="mb-4"
                prepend-inner-icon="mdi-domain"
                :loading="isLoadingTenants"
                :disabled="isProcessingUser"
              ></v-select>

              <v-checkbox
                v-model="isActive"
                label="Kullanıcı Aktif (Enabled)"
                color="primary"
                class="mb-4"
                :disabled="isProcessingUser"
              ></v-checkbox>

              <v-alert
                v-if="processUserError"
                type="error"
                density="compact"
                variant="tonal"
                closable
                class="mb-4"
                @update:modelValue="clearProcessError"
              >
                {{ processUserError }}
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
                :loading="isProcessingUser"
                :disabled="isProcessingUser"
                type="submit"
                color="primary"
                block
                size="large"
              >
                Kullanıcıyı Oluştur
              </v-btn>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useUserManagementStore } from '@/stores/userManagementStore';
import { useTenantStore } from '@/stores/tenantStore'; // Tenant'ları çekmek için
import { storeToRefs } from 'pinia';

const router = useRouter();
const userManagementStore = useUserManagementStore();
const tenantStore = useTenantStore();

// User Management Store'dan state ve action'lar
const { isProcessingUser, processUserError, createdUser } = storeToRefs(userManagementStore);
const { createUser } = userManagementStore;

// Tenant Store'dan state ve action'lar
const { tenants, isLoading: isLoadingTenants, error: tenantError } = storeToRefs(tenantStore); // isLoading ismini değiştirdim
const { fetchTenants } = tenantStore;

// Form data refs
const createUserForm = ref(null); // Form referansı
const email = ref('');
const fullName = ref('');
const password = ref('');
const selectedRoles = ref([]); // Keycloak rol adları
const isActive = ref(true);
const selectedTenantId = ref(null); // Seçilen tenant'ın lokal DB ID'si

const successMessage = ref('');

// Form validasyon kuralları
const emailRules = [
  v => !!v || 'E-posta gerekli.',
  v => /.+@.+\..+/.test(v) || 'Geçerli bir e-posta adresi giriniz.',
];
const fullNameRules = [
  v => !!v || 'Tam ad gerekli.',
  v => (v && v.length >= 2) || 'Tam ad en az 2 karakter olmalı.',
];
const passwordRules = [
  v => !!v || 'Şifre gerekli.',
  v => (v && v.length >= 8) || 'Şifre en az 8 karakter olmalı.',
];
const rolesRules = [
  v => (v && v.length > 0) || 'En az bir rol seçilmelidir.',
];

// Keycloak'ta tanımlı olan ve atanabilecek realm rolleri
// Bu liste dinamik olarak backend'den de çekilebilir, şimdilik sabit.
// general-admin rolünü bir adminin başka bir kullanıcıya ataması genellikle istenmez,
// bu yüzden listeden çıkarılabilir veya özel bir kontrolle eklenebilir.
const availableKeycloakRoles = ref(['customer-user', 'agent', 'helpdesk-admin']); // [cite: 1512, 1513, 1514]

// Tenant dropdown için formatlanmış tenant listesi
const tenantItems = computed(() => {
  return tenants.value.map(tenant => ({
    id: tenant.id, // Tenant'ın lokal DB'deki UUID'si
    name: tenant.name,
  }));
});

// Component yüklendiğinde tenant listesini çek
onMounted(() => {
  fetchTenants(1, 1000); // Çok sayıda tenant olabileceği varsayımıyla limiti yüksek tutuyoruz.
                        // İdealde aranabilir bir select veya server-side select kullanılabilir.
  userManagementStore.processUserError = null; // Sayfa yüklenirken eski hataları temizle
  userManagementStore.createdUser = null;
});

const handleCreateUser = async () => {
  successMessage.value = '';
  userManagementStore.processUserError = null; // Önceki hatayı temizle

  const { valid } = await createUserForm.value.validate();
  if (!valid) {
    console.log("Yeni kullanıcı formu geçerli değil.");
    return;
  }

  const userData = {
    email: email.value,
    full_name: fullName.value,
    password: password.value,
    roles: selectedRoles.value,
    is_active: isActive.value,
    tenant_id: selectedTenantId.value, // null olabilir
  };

  const result = await createUser(userData);

  if (result) {
    successMessage.value = `Kullanıcı '${result.full_name}' (E-posta: ${result.email}) başarıyla oluşturuldu! Kullanıcı listesine yönlendiriliyorsunuz...`;
    // Formu temizle
    createUserForm.value.reset();
    email.value = ''; // v-form reset() bazen v-model'leri tam sıfırlamayabilir
    fullName.value = '';
    password.value = '';
    selectedRoles.value = [];
    isActive.value = true;
    selectedTenantId.value = null;
    
    setTimeout(() => {
      router.push({ name: 'AdminUserList' });
    }, 2500);
  }
  // Hata mesajı zaten store'daki processUserError state'i üzerinden gösterilecek
};

const clearProcessError = () => {
  userManagementStore.processUserError = null;
};

const goBack = () => {
  router.push({ name: 'AdminUserList' });
};

</script>

<style scoped>
/* Gerekirse özel stiller */
</style>