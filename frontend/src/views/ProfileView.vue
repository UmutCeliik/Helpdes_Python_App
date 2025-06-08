<template>
  <v-container>
    <h1 class="text-h4 font-weight-medium mb-6">Profilim</h1>
    <v-row>
      <v-col cols="12" md="8">
        <v-card elevation="2">
          <v-card-text>
            <v-list density="compact">
              <v-list-item>
                <template v-slot:prepend>
                  <v-icon color="primary">mdi-account-outline</v-icon>
                </template>
                <v-list-item-title class="font-weight-bold">Tam Adı</v-list-item-title>
                <v-list-item-subtitle>{{ userProfile?.name || userProfile?.preferred_username }}</v-list-item-subtitle>
              </v-list-item>

              <v-divider class="my-2"></v-divider>

              <v-list-item>
                <template v-slot:prepend>
                  <v-icon color="primary">mdi-email-outline</v-icon>
                </template>
                <v-list-item-title class="font-weight-bold">E-posta Adresi</v-list-item-title>
                <v-list-item-subtitle>{{ userProfile?.email }}</v-list-item-subtitle>
              </v-list-item>
              
              <v-divider class="my-2"></v-divider>

              <v-list-item>
                 <template v-slot:prepend>
                  <v-icon color="primary">mdi-shield-account-outline</v-icon>
                </template>
                <v-list-item-title class="font-weight-bold">Roller</v-list-item-title>
                <v-list-item-subtitle>
                    <v-chip v-for="role in userRoles" :key="role" size="small" class="mr-1 mt-1">{{ role }}</v-chip>
                </v-list-item-subtitle>
              </v-list-item>

            </v-list>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="4">
          <v-card elevation="2">
              <v-card-title>Hesap Yönetimi</v-card-title>
              <v-card-text>
                  <p class="text-body-2 mb-4">Şifrenizi veya diğer hesap ayarlarınızı Keycloak üzerinden yönetebilirsiniz.</p>
                   <v-btn
                    color="primary"
                    @click="goToAccountManagement"
                    block
                    prepend-icon="mdi-open-in-new"
                   >
                    Hesabımı Yönet
                   </v-btn>
              </v-card-text>
          </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { computed } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { keycloak } from '@/services/keycloak.service'; // Keycloak instance'ını import ediyoruz

const authStore = useAuthStore();

// Store'daki mevcut kullanıcı bilgilerini kullanıyoruz.
// /users/me endpoint'inden dönen daha detaylı bilgi de kullanılabilir,
// ancak şimdilik token'daki bilgi yeterli.
const userProfile = computed(() => authStore.userProfile);
const userRoles = computed(() => authStore.userRoles);

const goToAccountManagement = () => {
  if (keycloak && keycloak.authenticated) {
    // Bu fonksiyon, kullanıcıyı Keycloak'un hesap yönetimi sayfasına yönlendirir.
    keycloak.accountManagement();
  }
};
</script>