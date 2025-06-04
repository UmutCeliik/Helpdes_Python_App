<template>
  <v-container>
    <v-row justify="center">
      <v-col cols="12" md="8" lg="6">
        <h1 class="text-h5 mb-6">Yeni Tenant Oluştur</h1>
        <v-card>
          <v-card-text>
            <v-form @submit.prevent="handleCreateTenant" ref="createTenantForm">
              <v-text-field
                v-model="tenantName"
                label="Tenant Adı"
                :rules="tenantNameRules"
                required
                variant="outlined"
                class="mb-4"
                :disabled="tenantStore.isCreating"
              ></v-text-field>

              <v-alert
                v-if="tenantStore.createError"
                type="error"
                density="compact"
                closable
                @update:modelValue="tenantStore.createError = null" 
                class="mb-4"
              >
                {{ tenantStore.createError }}
              </v-alert>

              <v-alert
                v-if="successMessage"
                type="success"
                density="compact"
                closable
                @update:modelValue="successMessage = ''"
                class="mb-4"
              >
                {{ successMessage }}
              </v-alert>

              <v-btn
                :loading="tenantStore.isCreating"
                :disabled="tenantStore.isCreating"
                type="submit"
                color="primary"
                block
                size="large"
              >
                Tenant Oluştur
              </v-btn>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { ref } from 'vue';
import { useTenantStore } from '@/stores/tenantStore';
import { useRouter } from 'vue-router';

const tenantStore = useTenantStore();
const router = useRouter();

const tenantName = ref('');
const successMessage = ref('');
const createTenantForm = ref(null); // Form referansı (v-form için)

const tenantNameRules = [
  v => !!v || 'Tenant adı gerekli.',
  v => (v && v.length >= 2) || 'Tenant adı en az 2 karakter olmalı.',
  v => (v && v.length <= 255) || 'Tenant adı en fazla 255 karakter olabilir.',
];

async function handleCreateTenant() {
  // Vuetify form validasyonunu kontrol et
  const { valid } = await createTenantForm.value.validate();
  if (!valid) {
    console.log("Form geçerli değil.");
    return;
  }

  successMessage.value = ''; // Önceki başarı mesajlarını temizle
  // tenantStore.createError zaten action içinde temizleniyor veya ayarlanıyor.

  const result = await tenantStore.createTenant({ name: tenantName.value });

  if (result) { // createTenant action'ı başarıyla true döndürdüyse
    successMessage.value = `Tenant '${tenantName.value}' başarıyla oluşturuldu! Liste sayfasına yönlendiriliyorsunuz...`;
    tenantName.value = ''; // Formu temizle
    // createTenantForm.value.reset(); // Formu tamamen resetle
    
    // Başarı mesajını gösterdikten sonra listeleme sayfasına yönlendir
    setTimeout(() => {
      router.push({ name: 'AdminTenantList' }); // /admin/tenants yoluna yönlendir
    }, 2000); // 2 saniye sonra
  }
  // Hata durumu zaten tenantStore.createError üzerinden v-alert ile gösterilecek.
}
</script>

<style scoped>
/* Gerekirse özel stiller */
</style>