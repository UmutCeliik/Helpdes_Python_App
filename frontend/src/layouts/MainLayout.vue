<template>
  <v-app>
    <v-navigation-drawer
      v-model="drawer"
      app
      clipped-left 
      color="grey-lighten-4"
    >
      <v-list dense nav>
        <v-list-subheader>MENÜ</v-list-subheader>
        <v-list-item
          v-for="(item, i) in menuItems"
          :key="i"
          :to="item.route"
          link
          color="primary"
          exact 
        >
          <template v-slot:prepend>
            <v-icon :icon="item.icon"></v-icon>
          </template>
          <v-list-item-title>{{ item.title }}</v-list-item-title>
        </v-list-item>
      </v-list>
      <template v-slot:append>
        <div class="pa-2">
          <v-btn block color="primary" @click="handleLogout">
            <v-icon left>mdi-logout</v-icon>
            Çıkış Yap
          </v-btn>
        </div>
      </template>
    </v-navigation-drawer>

    <v-app-bar app clipped-left color="primary" dark>
      <v-app-bar-nav-icon @click.stop="drawer = !drawer"></v-app-bar-nav-icon>
      <v-toolbar-title class="font-weight-bold">
        <v-icon icon="mdi-lifebuoy" class="mr-2"></v-icon>
        Firma Helpdesk
      </v-toolbar-title>
      <v-spacer></v-spacer>
      <span class="mr-3">Hoş geldiniz, {{ userName }}</span>
    </v-app-bar>

    <v-main class="grey-lighten-5">
      <router-view />
    </v-main>
  </v-app>
</template>

<script>
import { ref, computed } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';

export default {
  name: 'MainLayout',
  setup() {
    const drawer = ref(true);
    const authStore = useAuthStore();
    const router = useRouter();

    const baseMenuItems = [
      { title: 'Ana Panel', icon: 'mdi-view-dashboard', route: '/' },
      { title: 'Biletlerim', icon: 'mdi-ticket', route: '/tickets' },
      { title: 'Yeni Bilet Oluştur', icon: 'mdi-plus-box', route: '/create-ticket' },
    ];

    const menuItems = computed(() => {
      const items = [...baseMenuItems];
      if (authStore.userRoles && authStore.userRoles.includes('general-admin')) {
        items.push({ title: 'Admin Paneli', icon: 'mdi-shield-crown', route: '/admin' });
        items.push({ title: 'Tenant Yönetimi', icon: 'mdi-domain', route: '/admin/tenants' });
        items.push({ title: 'Kullanıcı Yönetimi', icon: 'mdi-account-group', route: '/admin/users' });
      }
      return items;
    });

    // --- DÜZELTİLMİŞ KISIM ---
    const userName = computed(() => {
      const user = authStore.userProfile; // auth.js store'undaki userProfile'ı kullanıyoruz
      // userProfile içindeki 'name', 'preferred_username' veya 'email' gibi alanları kontrol edin
      // Keycloak'tan gelen profile göre bu alanlar değişebilir.
      // Örnek: user.name || user.preferred_username || user.email || 'Kullanıcı'
      // Sizin auth.js store'unuz userProfile.value = { username: tokenParsed.value?.preferred_username ...} şeklinde set ediyor.
      // Bu durumda user.username veya user.email kullanılabilir.
      if (user) {
        return user.name || user.preferred_username || user.email || 'Kullanıcı';
      }
      return 'Kullanıcı';
    });

    const handleLogout = () => {
      console.log('MainLayout: handleLogout called'); // Log eklendi
      authStore.logout(); // Bu, store'daki logout action'ını çağırır
      // store'daki logout action'ı zaten redirectUri ile Keycloak'a yönlendirme yapmalı
      // ve Keycloak da login sayfasına geri yönlendirmeli.
      // Eğer Keycloak yönlendirmesi sonrası login sayfasına gelinmiyorsa
      // veya state güncellenmiyorsa, authStore.logout() ve Keycloak init/check-sso akışını incelemek gerekir.
      // Şimdilik router.push('/login') çağrısını burada tutabiliriz,
      // ancak idealde Keycloak logout sonrası yönlendirme bunu halletmeli.
      // router.push('/login'); // Bu satır, authStore.logout içindeki Keycloak yönlendirmesiyle çakışabilir veya gereksiz olabilir.
                               // auth.js'deki logout'a redirectUri eklediğimiz için bu satıra genellikle gerek kalmaz.
                               // Keycloak logout sonrası /login'e yönlendirecektir.
                               // Eğer logout sonrası state güncellenmiyorsa, sorun başkadır.
    };
    // --- DÜZELTİLMİŞ KISIM SONU ---

    return {
      drawer,
      menuItems,
      userName,
      handleLogout,
    };
  }
};
</script>
  
  <style scoped>
  /* Özel stiller gerekirse buraya eklenebilir */
  .v-list-item--active {
    /* Aktif menü öğesi için özel stil (isteğe bağlı) */
    background-color: rgba(var(--v-theme-primary), 0.1);
  }
  .v-navigation-drawer {
    border-right: 1px solid #e0e0e0;
  }
  .v-app-bar {
    box-shadow: 0 2px 4px -1px rgba(0,0,0,.2), 0 4px 5px 0 rgba(0,0,0,.14), 0 1px 10px 0 rgba(0,0,0,.12) !important;
  }
  </style>
  