<template>
  <v-container fluid>
    <v-row justify="space-between" align="center" class="mb-4">
      <v-col>
        <h1 class="text-h5 font-weight-medium">Kullanıcı Yönetimi</h1>
      </v-col>
      <v-col class="text-right">
        <v-btn
          color="primary"
          @click="navigateToCreateUser"
          prepend-icon="mdi-account-plus-outline"
        >
          Yeni Kullanıcı Oluştur
        </v-btn>
      </v-col>
    </v-row>

    <v-alert
      v-if="usersError"
      type="error"
      density="compact"
      closable
      class="mb-4"
      @update:modelValue="clearListError" 
    >
      Kullanıcı listesi yüklenirken hata: {{ usersError }}
    </v-alert>

    <v-alert
      v-if="deleteUserError"
      type="error"
      density="compact"
      closable
      class="mb-4"
      @update:modelValue="clearDeleteError"
    >
      Kullanıcı silinirken hata: {{ deleteUserError }}
    </v-alert>

    <v-card elevation="2">
      <v-card-title class="d-flex align-center pe-2">
        Kayıtlı Kullanıcılar (Toplam: {{ totalUsers }})
        <v-spacer></v-spacer>
        </v-card-title>
      <v-divider></v-divider>

      <v-data-table
        :headers="headers"
        :items="users"
        :loading="isLoadingUsers"
        :items-per-page="itemsPerPage"
        :page="currentPage" 
        density="compact"
        item-value="id"
        class="elevation-0"
        hover
        loading-text="Kullanıcılar yükleniyor..."
        no-data-text="Gösterilecek kullanıcı bulunamadı."
        @update:page="handlePageUpdate"
        @update:items-per-page="handleItemsPerPageUpdate"
      >
        <template v-slot:item.id="{ item }">
          <span class="text-caption" style="font-family: monospace;">{{ item.id }}</span>
        </template>

        <template v-slot:item.roles="{ item }">
          <div v-if="item.roles && item.roles.length">
            <v-chip
              v-for="role in item.roles"
              :key="role"
              size="small"
              class="mr-1 mb-1"
              label
              color="teal-lighten-5"
              variant="outlined"
            >
              {{ role }}
            </v-chip>
          </div>
          <span v-else class="text-caption">Rol Yok</span>
        </template>

        <template v-slot:item.is_active="{ item }">
          <v-chip :color="item.is_active ? 'green-lighten-1' : 'red-lighten-1'" size="small" label dark>
            {{ item.is_active ? 'Aktif' : 'Pasif' }}
          </v-chip>
        </template>

        <template v-slot:item.created_at="{ item }">
          <span class="text-caption">{{ formatDateTime(item.created_at) }}</span>
        </template>

        <template v-slot:item.actions="{ item }">
          <v-tooltip location="top" text="Kullanıcıyı Düzenle">
            <template v-slot:activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-pencil"
                variant="text"
                color="info"
                size="small"
                class="me-1"
                @click="editUser(item.id)"
              >
                <v-icon>mdi-pencil</v-icon>
              </v-btn>
            </template>
          </v-tooltip>
          <v-tooltip location="top" text="Kullanıcıyı Sil">
            <template v-slot:activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-delete"
                variant="text"
                color="error"
                size="small"
                @click="confirmDeleteUser(item.id, item.full_name || item.email)"
                :disabled="isDeletingUser && userToDelete.id === item.id" 
              >
                <v-icon>mdi-delete</v-icon>
              </v-btn>
            </template>
          </v-tooltip>
        </template>

        <template v-slot:loading>
          <v-skeleton-loader type="table-row@5"></v-skeleton-loader>
        </template>
        
        <template v-slot:bottom>
          <v-divider></v-divider>
          <div class="text-center d-flex align-center justify-space-between pa-2">
            <div class="text-caption">
              Sayfa başına:
              <v-select
                v-model="itemsPerPage"
                :items="[5, 10, 20, 50]"
                density="compact"
                variant="outlined"
                hide-details
                style="display: inline-block; width: 80px;"
                class="ml-2"
              ></v-select>
            </div>
            <v-pagination
              v-model="currentPage"
              :length="totalPages"
              :total-visible="5"
              density="compact"
            ></v-pagination>
             <div class="text-caption" style="width: 80px;"> </div>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-model="deleteDialog" max-width="500px" persistent>
      <v-card>
        <v-card-title class="text-h5 grey lighten-2" primary-title>
          Kullanıcıyı Silme Onayı
        </v-card-title>
        <v-card-text class="py-4">
          <strong>{{ userToDelete.name }}</strong> adlı kullanıcıyı kalıcı olarak silmek istediğinizden emin misiniz? 
          <br><br>
          Bu işlem geri alınamaz.
        </v-card-text>
        <v-divider></v-divider>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn 
            color="blue darken-1" 
            variant="text" 
            @click="closeDeleteDialog" 
            :disabled="isDeletingUser"
          >
            İptal
          </v-btn>
          <v-btn 
            color="red darken-1" 
            variant="flat" 
            @click="deleteUserConfirmed" 
            :loading="isDeletingUser"
          >
            Sil
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="snackbar.timeout"
      location="top right"
    >
      {{ snackbar.text }}
      <template v-slot:actions>
        <v-btn color="white" variant="text" @click="snackbar.show = false">
          Kapat
        </v-btn>
      </template>
    </v-snackbar>

  </v-container>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue';
import { useUserManagementStore } from '@/stores/userManagementStore';
import { storeToRefs } from 'pinia';
import { useRouter } from 'vue-router';

const router = useRouter();
const userStore = useUserManagementStore();

const { 
  users, 
  totalUsers, 
  isLoadingUsers, 
  usersError, 
  isDeletingUser, // Store'dan gelen silme yüklenme durumu
  deleteUserError   // Store'dan gelen silme hatası
} = storeToRefs(userStore);

// Store action'larını alırken, component içinde aynı isimde bir fonksiyonla çakışmaması için
// farklı bir isimle alabiliriz veya doğrudan store.actionName() şeklinde çağırabiliriz.
// Şimdilik doğrudan store.deleteUser() kullanacağız.
const { fetchUsers } = userStore; 

const headers = [
  { title: 'ID', key: 'id', sortable: false, width: '280px', cellProps: { class: 'text-caption' } },
  { title: 'Tam Adı', key: 'full_name', sortable: true },
  { title: 'E-posta', key: 'email', sortable: true },
  { title: 'Roller', key: 'roles', sortable: false, align: 'center', width: '150px' },
  { title: 'Durum', key: 'is_active', sortable: true, align: 'center', width: '100px'},
  { title: 'Oluşturulma Tarihi', key: 'created_at', sortable: true, width: '170px'},
  { title: 'Aksiyonlar', key: 'actions', sortable: false, align: 'center', width: '130px' },
];

const currentPage = ref(1);
const itemsPerPage = ref(10); 

const totalPages = computed(() => {
  if (totalUsers.value === 0 || itemsPerPage.value === 0) return 1; // En az 1 sayfa
  return Math.ceil(totalUsers.value / itemsPerPage.value);
});

const loadUsers = async () => {
  await fetchUsers(currentPage.value, itemsPerPage.value);
};

onMounted(loadUsers);

watch(currentPage, (newPage, oldPage) => {
  if (newPage !== oldPage) { // Sadece gerçekten değiştiyse yükle
    loadUsers();
  }
});

watch(itemsPerPage, (newItemsPerPage, oldItemsPerPage) => {
 if (newItemsPerPage !== oldItemsPerPage) {
    currentPage.value = 1; 
    loadUsers();
  }
});

const formatDateTime = (dateTimeString) => {
  if (!dateTimeString) return 'N/A';
  try {
    return new Date(dateTimeString).toLocaleString('tr-TR', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit'
    });
  } catch (e) {
    return dateTimeString;
  }
};

const navigateToCreateUser = () => {
  router.push({ name: 'AdminUserCreate' }); // <--- GÜNCELLENDİ
  // alert('Yeni kullanıcı oluşturma sayfası henüz hazır değil.'); // Eski satırı silin
  // console.log('Navigate to create user page'); // Eski satırı silin
};

const editUser = (userId) => {
  router.push({ name: 'AdminUserEdit', params: { userId: userId } });
};

const deleteDialog = ref(false);
const userToDelete = ref({ id: null, name: '' });

const snackbar = ref({
  show: false,
  text: '',
  color: 'success',
  timeout: 3000,
});

const showSnackbar = (text, color = 'success', timeout = 3000) => {
  snackbar.value.text = text;
  snackbar.value.color = color;
  snackbar.value.timeout = timeout;
  snackbar.value.show = true;
};

const confirmDeleteUser = (userId, userName) => {
  userToDelete.value = { id: userId, name: userName };
  userStore.deleteUserError = null; 
  userStore.usersError = null; 
  deleteDialog.value = true;
};

const closeDeleteDialog = () => {
  deleteDialog.value = false;
};

const deleteUserConfirmed = async () => {
  if (!userToDelete.value.id) return;
  
  const success = await userStore.deleteUser(userToDelete.value.id); // Doğrudan store.actionName()
  
  if (success) {
    showSnackbar(`'${userToDelete.value.name}' adlı kullanıcı başarıyla silindi.`, 'success');
    if (users.value.length === 1 && currentPage.value > 1 && totalUsers.value > 1) {
        currentPage.value -= 1; // Eğer sayfadaki son eleman silindiyse ve ilk sayfa değilse, bir önceki sayfaya git
    } else {
      // Mevcut sayfada kalıp listeyi yenile veya eğer son eleman silindiyse ve sayfa 1'e düştüyse
      // current page zaten 1 ise watch tetiklenmeyebilir, bu yüzden manuel çağrı gerekebilir.
      await loadUsers(); 
    }
  } else {
    // Hata mesajı store'daki deleteUserError state'ine yazıldı.
    // Snackbar ile de gösterilebilir veya sadece v-alert'e güvenilebilir.
    showSnackbar(`Hata: ${deleteUserError.value || 'Kullanıcı silinemedi.'}`, 'error');
  }
  
  closeDeleteDialog(); 
  userToDelete.value = { id: null, name: '' };
};

const clearListError = () => {
  userStore.usersError = null; 
};
const clearDeleteError = () => {
  userStore.deleteUserError = null;
};

// v-data-table'dan gelen event'ler için (eğer gerekirse diye duruyor, watch ile yönetiyoruz)
const handlePageUpdate = (newPage) => {
  if(currentPage.value !== newPage) currentPage.value = newPage;
};
const handleItemsPerPageUpdate = (newItemsPerPage) => {
  if (itemsPerPage.value !== newItemsPerPage) {
    itemsPerPage.value = newItemsPerPage;
  }
};

</script>

<style scoped>
.v-chip {
  margin-top: 4px;
  margin-bottom: 4px;
}
.v-data-table .v-btn { /* Butonların etrafındaki padding'i azaltmak için */
  margin: 0 2px;
}
</style>