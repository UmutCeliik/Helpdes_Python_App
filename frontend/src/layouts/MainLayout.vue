<template>
  <v-app>
    <v-navigation-drawer
      v-model="drawer"
      app
      :clipped-left="true"
      color="grey-lighten-4"
      :rail="isDesktop && rail"
      :expand-on-hover="isDesktop && rail"
    >
      <v-list dense nav>
        <v-list-item v-if="drawer && !rail" class="pa-2 mb-2">
            <v-list-item-title class="text-h6 font-weight-bold ml-1">
                Serhat Baba
            </v-list-item-title>
        </v-list-item>

        <v-divider></v-divider>

        <v-list-subheader class="mt-2">MENÜ</v-list-subheader>
        <v-list-item
          v-for="(item, i) in menuItems"
          :key="i"
          :to="item.route"
          link
          color="primary"
          exact
          :title="item.title"
        >
          <template v-slot:prepend>
            <v-icon :icon="item.icon"></v-icon>
          </template>
          <v-list-item-title>{{ item.title }}</v-list-item-title>
        </v-list-item>
      </v-list>
    </v-navigation-drawer>

    <v-app-bar app :clipped-left="true" color="primary" dark>
      <v-app-bar-nav-icon
        @click.stop="isDesktop ? (rail = !rail) : (drawer = !drawer)"
        :title="isDesktop ? (rail ? 'Menüyü Genişlet' : 'Menüyü Daralt') : 'Menüyü Aç/Kapat'"
      >
        <v-icon v-if="isDesktop">{{ rail ? 'mdi-format-indent-decrease' : 'mdi-format-indent-increase' }}</v-icon>
        <v-icon v-else>mdi-menu</v-icon>
      </v-app-bar-nav-icon>

      <v-toolbar-title class="font-weight-bold" v-if="!drawer || rail">
        <v-icon icon="mdi-lifebuoy" class="mr-2"></v-icon>
        Firma Helpdesk
      </v-toolbar-title>
      
      <v-spacer></v-spacer>

      <v-tooltip location="bottom" text="Temayı Değiştir">
        <template v-slot:activator="{ props: tooltipProps }">
          <v-btn v-bind="tooltipProps" @click="toggleTheme" icon class="mr-1">
            <v-icon>mdi-theme-light-dark</v-icon>
          </v-btn>
        </template>
      </v-tooltip>

      <v-menu offset-y>
        <template v-slot:activator="{ props: menuProps }">
          <v-btn v-bind="menuProps" text class="mr-1 text-capitalize" style="letter-spacing: normal;">
            <v-icon left class="mr-2">mdi-account-circle-outline</v-icon>
            {{ userName }}
            <v-icon right class="ml-1">mdi-menu-down</v-icon>
          </v-btn>
        </template>
        <v-list density="compact" nav>
          <v-list-item :to="{ name: 'Profile' }" value="profile">
            <template v-slot:prepend>
              <v-icon>mdi-account-box-outline</v-icon>
            </template>
            <v-list-item-title>Profilim</v-list-item-title>
          </v-list-item>
          <v-list-item @click="() => { alert('Ayarlar sayfası henüz hazır değil.'); }" value="settings">
            <template v-slot:prepend>
              <v-icon>mdi-cog-outline</v-icon>
            </template>
            <v-list-item-title>Ayarlar</v-list-item-title>
          </v-list-item>
          <v-divider class="my-1"></v-divider>
          <v-list-item @click="handleLogout" value="logout" base-color="red">
             <template v-slot:prepend>
              <v-icon>mdi-logout</v-icon>
            </template>
            <v-list-item-title>Çıkış Yap</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-app-bar>

    <v-main :class="theme.global.current.value.dark ? 'bg-grey-darken-4' : 'bg-grey-lighten-4'" >
      <v-container fluid class="pa-4">
         <router-view />
      </v-container>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useTheme, useDisplay } from 'vuetify';

// Store ve Hook'lar
const authStore = useAuthStore();
const theme = useTheme();
const { mdAndUp: isDesktop } = useDisplay();

// State
const drawer = ref(true);
const rail = ref(true);

// Menü Öğeleri
const baseMenuItems = [
  { title: 'Ana Panel', icon: 'mdi-view-dashboard-outline', route: '/' },
  { title: 'Biletlerim', icon: 'mdi-ticket-outline', route: '/tickets' },
  { title: 'Yeni Bilet Oluştur', icon: 'mdi-plus-box-outline', route: '/create-ticket' },
];

const menuItems = computed(() => {
  const items = [...baseMenuItems];
  if (authStore.userRoles && authStore.userRoles.includes('general-admin')) {
    items.push({ title: 'Admin Paneli', icon: 'mdi-shield-crown-outline', route: '/admin' });
    items.push({ title: 'Tenant Yönetimi', icon: 'mdi-domain', route: '/admin/tenants' });
    items.push({ title: 'Kullanıcı Yönetimi', icon: 'mdi-account-group-outline', route: '/admin/users' });
  }
  return items;
});

// Kullanıcı Adı
const userName = computed(() => {
  const user = authStore.userProfile;
  if (user) {
    return user.name || user.preferred_username || user.email || 'Kullanıcı';
  }
  return 'Kullanıcı';
});

// Logout İşlevi
const handleLogout = () => {
  console.log('MainLayout: handleLogout called');
  authStore.logout();
};

// Tema Değiştirme İşlevi
const toggleTheme = () => {
  const newTheme = theme.global.current.value.dark ? 'myCustomLightTheme' : 'myCustomDarkTheme';
  theme.global.name.value = newTheme;
  localStorage.setItem('userTheme', newTheme);
};

// Lifecycle Hooks
onMounted(() => {
  const savedTheme = localStorage.getItem('userTheme');
  if (savedTheme && (savedTheme === 'myCustomLightTheme' || savedTheme === 'myCustomDarkTheme')) {
    theme.global.name.value = savedTheme;
  }

  if (isDesktop.value) {
    drawer.value = true;
    rail.value = true;
  } else {
    drawer.value = false;
    rail.value = false;
  }
});
</script>

<style scoped>
.v-list-item--active {
  border-left: 4px solid rgb(var(--v-theme-primary));
  background-color: rgba(var(--v-theme-primary), 0.08);
}
.v-navigation-drawer {
    border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.v-btn.text-capitalize {
  text-transform: none !important;
  letter-spacing: normal !important;
  font-weight: normal;
}
</style>