<template>
  <v-snackbar
    v-model="notificationStore.show"
    :color="notificationStore.color"
    :timeout="notificationStore.timeout"
    location="top right"
    variant="elevated"
    multi-line
  >
    {{ notificationStore.message }}
    <template v-slot:actions>
      <v-btn
        icon="mdi-close"
        variant="text"
        @click="notificationStore.hideNotification"
      ></v-btn>
    </template>
  </v-snackbar>
</template>

<script setup>
import { useNotificationStore } from '@/stores/notificationStore';

const notificationStore = useNotificationStore();
</script>