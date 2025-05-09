<script setup>
import { computed } from 'vue';
import { useAuthStore } from '@/stores/auth';

const authStore = useAuthStore();

// Store'daki isLoading ve authError state'lerini reaktif olarak kullanmak için computed property'ler
const isLoading = computed(() => authStore.isLoading);
const errorMessage = computed(() => authStore.authError);

const handleLogin = async () => {
  // Login denemesi öncesinde varsa eski hata mesajını temizle
  // authStore.clearAuthError(); // Eğer store'da böyle bir action tanımlarsak daha temiz olur
  // Şimdilik doğrudan store state'ini null yapabiliriz veya login action'ı bunu yapabilir.
  // authStore.authError = null; // Bu satırı ekleyebiliriz veya login action'ı içinde yapılabilir.
  // Şu anki authStore.login() zaten isLoading=true ve authError=null (başlangıçta) yapıyor olabilir.
  // Store'daki login action'ımız zaten isLoading ve authError'u yönetiyor.
  await authStore.login();
  // Bu çağrıdan sonra tarayıcı Keycloak login sayfasına yönlenmeli.
  // Eğer yönlenme öncesi bir hata olursa (örn: Keycloak instance hazır değilse),
  // authStore.isLoading ve authStore.authError store action'ı tarafından güncellenecektir.
};
</script>

<template>
  <v-container fluid class="fill-height grey-lighten-5">
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="6" lg="4">
        <v-card class="pa-4 pa-md-8" elevation="4">
          <v-card-title class="text-center text-h5 mb-6">
            <v-icon icon="mdi-lifebuoy" color="primary" class="mr-2"></v-icon>
            Firma Helpdesk
          </v-card-title>

          <v-card-text class="text-center">
            <p class="mb-6">
              Devam etmek için lütfen giriş yapınız.
            </p>

            <v-btn
              :loading="isLoading"
              :disabled="isLoading"
              @click="handleLogin"
              color="primary"
              block
              size="large"
              prepend-icon="mdi-login"
            >
              Keycloak ile Giriş Yap
            </v-btn>

            <v-alert
              v-if="errorMessage"
              type="error"
              density="compact"
              variant="tonal"
              class="mt-6"
              closable
              @update:modelValue="authStore.authError = null" >
              {{ errorMessage }}
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.fill-height {
  min-height: 100vh; /* Sayfanın tamamını kaplamasını sağla */
}
</style>