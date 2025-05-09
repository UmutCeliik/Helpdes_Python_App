<script setup>
// Bu script bölümü şimdilik boş kalabilir veya
// ileride global watcher'lar (örn: auth durumu izleme) için kullanılabilir.
// import { RouterView } from 'vue-router' // RouterView otomatik import ediliyor olabilir
</script>

<template>
  <router-view />
</template>

<style>
/* App.vue'ya özel stiller kaldırıldı.
   Genel stilleriniz (main.css veya assets/base.css gibi)
   ve Vuetify stilleri geçerli olacaktır.
   Gerekirse buraya global, kapsayıcı olmayan stiller eklenebilir. */

/* Örneğin, Vuetify'ın tüm uygulamayı sarması için temel ayar */
html, body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
  /* Vuetify'ın düzgün çalışması için genellikle ek stile gerek kalmaz */
}
</style>
