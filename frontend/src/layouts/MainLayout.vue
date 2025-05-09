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
      const drawer = ref(true); // Navigasyon menüsü durumu
      const authStore = useAuthStore();
      const router = useRouter();
  
      // Menü öğeleri (DashboardView'dan alındı)
      const menuItems = [
        { title: 'Ana Panel', icon: 'mdi-view-dashboard', route: '/' }, // Ana panel rotası
        { title: 'Biletlerim', icon: 'mdi-ticket', route: '/tickets' }, // Bilet listesi rotası
        { title: 'Yeni Bilet Oluştur', icon: 'mdi-plus-box', route: '/create-ticket' }, // Yeni bilet rotası
      ];
  
      // Kullanıcı adı (DashboardView'dan alındı)
      const userName = computed(() => {
         const user = authStore.user;
         return user ? (user.name || user.email || 'Kullanıcı') : 'Kullanıcı';
      });
  
      // Logout işlemi (DashboardView'dan alındı)
      const handleLogout = () => {
        authStore.logout();
        router.push('/login');
      };
  
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
  