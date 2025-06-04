import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores/auth'; // Auth store'u guard için import et

// Layout ve Sayfa Bileşenleri
import MainLayout from '@/layouts/MainLayout.vue'; // Yeni layout bileşeni (yolu kontrol edin)
import LoginView from '@/views/LoginView.vue';
import DashboardView from '@/views/DashboardView.vue'; // Sadeleştirilmiş dashboard
import TicketListView from '@/views/TicketListView.vue';
import CreateTicketView from '@/views/CreateTicketView.vue';

// Admin için placeholder (veya gerçek) view'ları import edin (bunları oluşturacağız)
const AdminDashboardView = () => import('@/views/admin/AdminDashboardView.vue'); // Örnek
const AdminTenantListView = () => import('@/views/admin/AdminTenantListView.vue');
const AdminTenantCreateView = () => import('@/views/admin/AdminTenantCreateView.vue');
const AdminTenantDetailView = () => import('@/views/admin/AdminTenantDetailView.vue'); // Bu dosyayı birazdan oluşturacağız


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
        },
        
        // --- YENİ ADMIN YOLLARI ---
        {
          path: 'admin', // Temel admin yolu /admin olacak
          name: 'AdminDashboard',
          component: AdminDashboardView, // Admin için bir ana panel sayfası
          meta: { requiresAuth: true, roles: ['general-admin'] } // Sadece general_admin erişebilir
        },
        {
          path: 'admin/tenants',
          name: 'AdminTenantList',
          component: AdminTenantListView, // Tenant listeleme sayfası
          meta: { requiresAuth: true, roles: ['general-admin'] }
        },
        {
          path: 'admin/tenants/new',
          name: 'AdminTenantCreate',
          component: AdminTenantCreateView, // Yeni tenant oluşturma sayfası
          meta: { requiresAuth: true, roles: ['general-admin'] }
        },
        {
          path: 'admin/tenants/:id', // Dinamik segment :id (tenant'ın DB ID'si olacak)
          name: 'AdminTenantDetail',
          component: AdminTenantDetailView,
          props: true, // Route parametrelerinin component'e props olarak geçmesini sağlar
          meta: { requiresAuth: true, roles: ['general-admin'] }
        }
        // Buraya diğer admin sayfaları (kullanıcı yönetimi vb.) eklenebilir
        // --- YENİ ADMIN YOLLARI SONU ---
      ]
    },
    // Yakalanamayan rotalar için 404 sayfası eklenebilir
    // { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFoundView }
  ],
});

// --- Global Navigation Guard ---
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore();
  const isAuthenticated = authStore.isAuthenticated;
  const userRoles = authStore.userRoles || []; // Roller yoksa boş dizi

  const requiresAuth = to.matched.some(record => record.meta.requiresAuth);
  const requiresGuest = to.matched.some(record => record.meta.requiresGuest);
  const requiredRoles = to.matched.flatMap(record => record.meta.roles || []); // Hedef yol için gerekli tüm rolleri topla

  console.log(`Navigating to: ${to.path}, isAuthenticated: ${isAuthenticated}, User Roles: ${userRoles}, Required Roles: ${requiredRoles}`);

  if (requiresAuth && !isAuthenticated) {
    console.log('Guard: Auth required, not authenticated. Redirecting to /login.');
    next({ name: 'login', query: { redirect: to.fullPath } }); // Login sonrası geri yönlendirme için
  } else if (requiresGuest && isAuthenticated) {
    console.log('Guard: Guest required, authenticated. Redirecting to /Dashboard.');
    next({ name: 'Dashboard' });
  } else if (requiredRoles.length > 0) { // Eğer yol belirli roller gerektiriyorsa
    const hasRequiredRole = requiredRoles.some(role => userRoles.includes(role));
    if (isAuthenticated && hasRequiredRole) {
      console.log('Guard: Role requirement met. Access granted.');
      next(); // Kullanıcı login olmuş ve gerekli role sahip
    } else if (isAuthenticated && !hasRequiredRole) {
      console.log('Guard: Role requirement NOT met. Redirecting to Dashboard (veya yetkisiz sayfasına).');
      // Kullanıcı login olmuş ama gerekli role sahip değil.
      // Onları yetkisiz bir sayfaya veya ana panele yönlendirebilirsiniz.
      next({ name: 'Dashboard' }); // VEYA next({ name: 'UnauthorizedPage' });
    } else {
      // Bu durum normalde ilk if'e takılmalı (login olmamış ve auth gerektiren yol)
      console.log('Guard: Auth required for role-protected route, not authenticated. Redirecting to /login.');
      next({ name: 'login', query: { redirect: to.fullPath } });
    }
  }
  else {
    console.log('Guard: No specific auth/guest/role requirement. Access granted.');
    next(); // Diğer tüm durumlar için izin ver
  }
});


export default router;
