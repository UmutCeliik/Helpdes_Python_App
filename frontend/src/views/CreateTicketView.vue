<template>
  <v-container fluid>
    <v-row justify="center">
      <v-col cols="12" md="8" lg="6">
         <h1 class="text-h5 font-weight-medium mb-6 text-center">Yeni Destek Bileti Oluştur</h1>
         <v-card elevation="2">
           <v-card-text>
             <v-form @submit.prevent="handleCreateTicket" ref="createForm">
               <v-text-field
                 v-model="title"
                 label="Başlık / Konu"
                 variant="outlined"
                 :rules="titleRules"
                 required
                 class="mb-4"
                 :disabled="isCreating" 
                 prepend-inner-icon="mdi-format-title"
               ></v-text-field>

               <v-textarea
                 v-model="description"
                 label="Sorunun Açıklaması"
                 variant="outlined"
                 :rules="descriptionRules"
                 required
                 rows="5"
                 auto-grow
                 class="mb-4"
                 :disabled="isCreating" 
                 prepend-inner-icon="mdi-text-long"
               ></v-textarea>

               <v-alert
                   v-if="createError"
                   type="error"
                   density="compact"
                   variant="tonal"
                   closable
                   class="mb-4"
                   @update:modelValue="clearCreateError" 
               >
                   {{ createError }}
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
                 :loading="isCreating" 
                 :disabled="isCreating" 
                 type="submit"
                 color="primary"
                 block
                 size="large"
               >
                 Bileti Oluştur
               </v-btn>
             </v-form>
           </v-card-text>
         </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
// mapState kaldırıldı, storeToRefs eklendi
import { ref, computed } from 'vue';
import { mapActions, storeToRefs } from 'pinia'; // mapActions hala kullanılabilir veya doğrudan alınabilir
import { useTicketStore } from '@/stores/ticketStore';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';

export default {
  name: 'CreateTicketView',
  setup() {
    const router = useRouter();
    const ticketStore = useTicketStore();
    const authStore = useAuthStore();

    const title = ref('');
    const description = ref('');
    const successMessage = ref('');
    const createForm = ref(null);

    // --- Doğrudan Store Erişimi ---
    // isCreating ve createError state'lerini reaktif tutmak için storeToRefs kullanın
    const { isCreating, createError } = storeToRefs(ticketStore);
    // createTicket action'ını doğrudan store'dan alın
    const { createTicket } = ticketStore;

    // Hata mesajını temizlemek için fonksiyon
    const clearCreateError = () => {
        ticketStore.createError = null; // Doğrudan store state'ini güncelle
    };
    // --- Store Erişimi Sonu ---

    const titleRules = [
      v => !!v || 'Başlık gerekli.',
      v => (v && v.length >= 3) || 'Başlık en az 3 karakter olmalı.',
      v => (v && v.length <= 100) || 'Başlık en fazla 100 karakter olabilir.',
    ];
    const descriptionRules = [
      v => !!v || 'Açıklama gerekli.',
      v => (v && v.length >= 10) || 'Açıklama en az 10 karakter olmalı.',
    ];

    const handleCreateTicket = async () => {
      if (!authStore.isAuthenticated) {
         ticketStore.createError = 'Bilet oluşturmak için giriş yapmalısınız.';
         router.push('/login');
         return;
      }

      const { valid } = await createForm.value.validate();
      if (!valid) {
        console.log("Form geçerli değil.");
        return;
      }

      successMessage.value = '';
      clearCreateError(); // Önceki hatayı temizle

      const ticketData = {
        title: title.value,
        description: description.value,
      };

      // Store'daki createTicket action'ını çağır
      const success = await createTicket(ticketData);

      if (success) {
        successMessage.value = 'Destek bileti başarıyla oluşturuldu!';
        createForm.value.reset();
        title.value = '';
        description.value = '';
        setTimeout(() => {
            if(successMessage.value){
               router.push('/tickets');
            }
        }, 2000);
      }
      // Hata mesajı zaten store'daki createError state'i üzerinden gösterilecek
    };

    // Template'de kullanılacak her şeyi return et
    return {
      title,
      description,
      isCreating, // storeToRefs sayesinde reaktif
      createError, // storeToRefs sayesinde reaktif
      successMessage,
      createForm,
      titleRules,
      descriptionRules,
      handleCreateTicket,
      clearCreateError, // Hata temizleme metodunu da return et
    };
  }
};
</script>

<style scoped>
.v-card {
    overflow: visible;
}
</style>
