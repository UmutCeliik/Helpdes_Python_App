import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores/auth'; // Auth store'u guard için import et

// Layout ve Sayfa Bileşenleri
import MainLayout from '@/layouts/MainLayout.vue'; // Yeni layout bileşeni (yolu kontrol edin)
import LoginView from '@/views/LoginView.vue';
import DashboardView from '@/views/DashboardView.vue'; // Sadeleştirilmiş dashboard
import TicketListView from '@/views/TicketListView.vue';
import CreateTicketView from '@/views/CreateTicketView.vue';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // Login Sayfası (Layout kullanmıyor)
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { requiresGuest: true } // Sadece giriş yapmamış kullanıcılar erişsin
    },
    // Ana Layout'u kullanan sayfalar
    {
      path: '/', // Ana layout'un temel yolu
      component: MainLayout,
      meta: { requiresAuth: true }, // Bu layout ve altındaki tüm rotalar için login gerekli
      children: [
        // Dashboard (Ana Sayfa)
        {
          path: '', // '/' yoluna denk gelir (MainLayout'un path'i ile birleşir)
          name: 'Dashboard',
          component: DashboardView,
          // meta: { requiresAuth: true } // Üst rotada zaten var, isteğe bağlı
        },
        // Bilet Listesi
        {
          path: 'tickets', // '/tickets' yoluna denk gelir
          name: 'tickets',
          component: TicketListView,
          // meta: { requiresAuth: true }
        },
        // Yeni Bilet Oluşturma
        {
          path: 'create-ticket', // '/create-ticket' yoluna denk gelir
          name: 'create-ticket',
          component: CreateTicketView,
          // meta: { requiresAuth: true }
        }
        // Diğer layout içi sayfalar buraya eklenebilir
      ]
    },
    // Yakalanamayan rotalar için 404 sayfası eklenebilir
    // { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFoundView }
  ],
});

// --- Global Navigation Guard ---
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore();
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth);
  const requiresGuest = to.matched.some(record => record.meta.requiresGuest);
  const isAuthenticated = authStore.isAuthenticated; // Store'dan kontrol et

  console.log(`Navigating to: ${to.path}, requiresAuth: ${requiresAuth}, requiresGuest: ${requiresGuest}, isAuthenticated: ${isAuthenticated}`);

  if (requiresAuth && !isAuthenticated) {
    // Login gerektiren sayfaya yetkisiz erişim -> Login'e yönlendir
    console.log('Guard: Auth required, not authenticated. Redirecting to /login.');
    next({ name: 'login' });
  } else if (requiresGuest && isAuthenticated) {
    // Sadece misafirlerin girebileceği sayfaya (örn: login) login olmuş kullanıcı erişimi -> Ana sayfaya yönlendir
    console.log('Guard: Guest required, authenticated. Redirecting to /.');
    next({ name: 'Dashboard' }); // Veya '/'
  } else {
    // Diğer tüm durumlar için izin ver
    console.log('Guard: Access granted.');
    next();
  }
});


export default router;
