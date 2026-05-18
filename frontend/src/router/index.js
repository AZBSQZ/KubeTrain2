import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
    meta: { title: '注册', public: true }
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '概览', icon: 'Odometer' }
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('@/views/tasks/Index.vue'),
        meta: { title: '训练任务', icon: 'VideoPlay' }
      },
      {
        path: 'tasks/create',
        name: 'TaskCreate',
        component: () => import('@/views/tasks/Create.vue'),
        meta: { title: '创建任务', hidden: true }
      },
      {
        path: 'tasks/:id',
        name: 'TaskDetail',
        component: () => import('@/views/tasks/Detail.vue'),
        meta: { title: '任务详情', hidden: true }
      },
      {
        path: 'datasets',
        name: 'Datasets',
        component: () => import('@/views/datasets/Index.vue'),
        meta: { title: '数据集', icon: 'Files' }
      },
      {
        path: 'datasets/:id',
        name: 'DatasetDetail',
        component: () => import('@/views/datasets/Detail.vue'),
        meta: { title: '数据集详情', hidden: true }
      },
      {
        path: 'algorithms',
        name: 'Algorithms',
        component: () => import('@/views/algorithms/Index.vue'),
        meta: { title: '算法', icon: 'Cpu' }
      },
      {
        path: 'algorithms/:id',
        name: 'AlgorithmDetail',
        component: () => import('@/views/algorithms/Detail.vue'),
        meta: { title: '算法详情', hidden: true }
      },
      {
        path: 'models',
        name: 'Models',
        component: () => import('@/views/models/Index.vue'),
        meta: { title: '模型仓库', icon: 'Box' }
      },
      {
        path: 'models/:id',
        name: 'ModelDetail',
        component: () => import('@/views/models/Detail.vue'),
        meta: { title: '模型详情', hidden: true }
      },
      {
        path: 'resources',
        name: 'Resources',
        component: () => import('@/views/resources/Index.vue'),
        meta: { title: '资源概览', icon: 'DataLine' }
      },
      {
        path: 'node-pools',
        name: 'NodePools',
        component: () => import('@/views/node-pools/Index.vue'),
        meta: { title: '节点池', icon: 'Histogram' }
      },
      {
        path: 'clusters',
        name: 'Clusters',
        component: () => import('@/views/clusters/Index.vue'),
        meta: { title: 'K8s 集群', icon: 'Connection' }
      },
      {
        path: 'alerts',
        name: 'Alerts',
        component: () => import('@/views/alerts/Index.vue'),
        meta: { title: '告警', icon: 'Bell' }
      },
      {
        path: 'workers',
        name: 'Workers',
        component: () => import('@/views/workers/Index.vue'),
        meta: { title: 'Agent 节点', icon: 'Monitor' }
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/users/Index.vue'),
        meta: { title: '用户管理', icon: 'User', adminOnly: true }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/Logs.vue'),
        meta: { title: '操作日志', icon: 'Document' }
      },
      {
        path: 'workers/guide',
        name: 'WorkerGuide',
        component: () => import('@/views/workers/Guide.vue'),
        meta: { title: '节点注册引导', hidden: true }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/Profile.vue'),
        meta: { title: '个人设置', hidden: true }
      }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  document.title = `${to.meta.title || 'KubeTrain'} - KubeTrain 2.0`
  if (to.meta.public) return next()
  const token = localStorage.getItem('kt_token')
  if (!token) return next('/login')
  next()
})

export default router
