import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useNotificationStore = defineStore('notification', () => {
  // State
  const message = ref('');
  const color = ref('success');
  const show = ref(false);
  const timeout = ref(4000); // 4 saniye

  // Actions
  function showNotification(newMessage, newColor = 'success') {
    message.value = newMessage;
    color.value = newColor;
    show.value = true;
  }
  
  function hideNotification() {
      show.value = false;
      message.value = '';
      color.value = 'success';
  }

  return {
    message,
    color,
    show,
    timeout,
    showNotification,
    hideNotification
  };
});