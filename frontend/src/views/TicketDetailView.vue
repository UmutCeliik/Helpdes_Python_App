<template>
  <v-container fluid>
    <v-btn variant="text" prepend-icon="mdi-arrow-left" to="/tickets" class="mb-4">
      Bilet Listesine Dön
    </v-btn>

    <v-progress-linear indeterminate color="primary" v-if="isLoadingDetails" class="mb-4"></v-progress-linear>

    <v-alert v-if="detailsError" type="error" density="compact" closable class="mb-4">
      {{ detailsError }}
    </v-alert>

    <v-row v-if="ticket">
      <v-col cols="12" md="7">
        <v-card elevation="2">
          <v-card-title class="d-flex justify-space-between align-center text-h5">
            <span>Bilet Detayı</span>
            <v-chip :color="getStatusColor(ticket.status)" label>{{ ticket.status }}</v-chip>
          </v-card-title>
          <v-card-subtitle>ID: {{ ticket.id }}</v-card-subtitle>
          <v-divider class="mt-2"></v-divider>

          <v-card-text>
            <v-list-item class="px-0">
              <v-list-item-title class="font-weight-bold">Konu:</v-list-item-title>
              <p class="text-body-1">{{ ticket.title }}</p>
            </v-list-item>
            <v-list-item class="px-0 mt-4">
              <v-list-item-title class="font-weight-bold">Açıklama:</v-list-item-title>
              <p class="text-body-1" style="white-space: pre-wrap;">{{ ticket.description }}</p>
            </v-list-item>
            
            <v-list-item class="px-0 mt-4">
                <v-list-item-title class="font-weight-bold mb-2">Ekler ({{ ticket.attachments.length }})</v-list-item-title>
                
                <v-file-input
                  v-model="filesToUpload"
                  label="Dosya ekle"
                  multiple
                  chips
                  variant="outlined"
                  density="compact"
                  prepend-icon="mdi-paperclip"
                ></v-file-input>
                <v-btn 
                  v-if="filesToUpload.length > 0" 
                  @click="submitAttachments"
                  :loading="isUploading"
                  color="primary" 
                  class="mt-2"
                  block
                >
                  Yükle
                </v-btn>

                <v-list dense class="mt-4 bg-transparent">
                  <div v-if="ticket.attachments.length === 0" class="text-medium-emphasis">Ek dosya bulunmamaktadır.</div>
                  <v-list-item
                    v-for="attachment in ticket.attachments"
                    :key="attachment.id"
                    class="pa-0"
                    :href="`http://localhost:8000/attachments/${attachment.id}`"
                    target="_blank"
                    :title="`'${attachment.file_name}' dosyasını indir`"
                  >
                    <template v-slot:prepend>
                      <v-icon color="primary">mdi-download-box-outline</v-icon>
                    </template>

                    <v-list-item-title class="text-primary">{{ attachment.file_name }}</v-list-item-title>
                    <v-list-item-subtitle>{{ attachment.file_type }}</v-list-item-subtitle>
                  </v-list-item>
                </v-list>
            </v-list-item>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="5">
        <h3 class="text-h6 mb-2">Yorumlar ({{ ticket.comments.length }})</h3>
        <v-card variant="outlined" class="mb-4">
          <v-card-text>
            <v-textarea
              v-model="newCommentText"
              label="Yorumunuzu ekleyin..."
              rows="3"
              variant="underlined"
              hide-details
              auto-grow
            ></v-textarea>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn color="primary" variant="tonal" @click="submitComment" :loading="isSubmittingComment">Yorum Ekle</v-btn>
          </v-card-actions>
        </v-card>
        
        <div v-if="ticket.comments.length === 0" class="text-center text-medium-emphasis pa-4">Henüz yorum yapılmamış.</div>
        <v-card v-for="comment in sortedComments" :key="comment.id" class="mb-3" variant="tonal">
          <v-card-text>
            <p style="white-space: pre-wrap;">{{ comment.content }}</p>
            <div class="d-flex justify-space-between align-center mt-2 text-caption text-medium-emphasis">
              <span>Yazar ID: {{ comment.author_id.substring(0,8) }}...</span>
              <span>{{ formatDateTime(comment.created_at) }}</span>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { onMounted, computed, ref } from 'vue';
import { useTicketStore } from '@/stores/ticketStore';
import { storeToRefs } from 'pinia';

const props = defineProps({
  ticketId: {
    type: String,
    required: true,
  },
});

const ticketStore = useTicketStore();
const {
  currentTicketDetails: ticket,
  isLoadingDetails,
  detailsError,
} = storeToRefs(ticketStore);

const newCommentText = ref('');
const isSubmittingComment = ref(false);
const filesToUpload = ref([]);
const isUploading = ref(false);

onMounted(() => {
  ticketStore.fetchTicketDetails(props.ticketId);
});

const sortedComments = computed(() => {
  if (ticket.value && ticket.value.comments) {
    return [...ticket.value.comments].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }
  return [];
});

const submitComment = async () => {
  if (!newCommentText.value.trim()) return;
  isSubmittingComment.value = true;
  const success = await ticketStore.addComment(props.ticketId, { content: newCommentText.value });
  if (success) {
    newCommentText.value = '';
  }
  isSubmittingComment.value = false;
};

const submitAttachments = async () => {
  if (filesToUpload.value.length === 0) return;
  isUploading.value = true;
  const success = await ticketStore.uploadAttachments(props.ticketId, filesToUpload.value);
  if(success) {
    filesToUpload.value = [];
  }
  isUploading.value = false;
};

const formatDateTime = (dateTimeString) => {
  if (!dateTimeString) return '';
  const options = { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' };
  return new Date(dateTimeString).toLocaleString('tr-TR', options);
};

const getStatusColor = (status) => {
  if (status === 'Açık') return 'info';
  if (status === 'İşlemde') return 'warning';
  if (status === 'Çözüldü') return 'success';
  return 'grey';
};
</script>

<style scoped>
.v-list.bg-transparent .v-list-item {
  background-color: transparent !important;
}
</style>