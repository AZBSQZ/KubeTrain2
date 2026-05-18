<template>
  <el-container class="main-layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo" @click="$router.push('/')">
        <el-icon size="22"><cpu /></el-icon>
        <span v-if="!collapsed" class="logo-text">KubeTrain 2.0</span>
      </div>
      <el-scrollbar class="menu-scrollbar">
        <el-menu
          :default-active="activeMenu"
          :default-openeds="collapsed ? [] : ['train-resource', 'train-exec', 'resource', 'system']"
          :collapse="collapsed"
          router
          background-color="transparent"
          text-color="#ffffffcc"
          active-text-color="#ffffff"
          class="side-menu"
        >
          <el-menu-item index="/dashboard">
            <el-icon><odometer /></el-icon>
            <template #title>概览</template>
          </el-menu-item>

          <el-sub-menu index="train-resource">
            <template #title>
              <el-icon><folder /></el-icon>
              <span>训练资源</span>
            </template>
            <el-menu-item index="/datasets">
              <el-icon><files /></el-icon>
              <template #title>数据集</template>
            </el-menu-item>
            <el-menu-item index="/algorithms">
              <el-icon><cpu /></el-icon>
              <template #title>算法脚本</template>
            </el-menu-item>
            <el-menu-item index="/models">
              <el-icon><box /></el-icon>
              <template #title>模型仓库</template>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="train-exec">
            <template #title>
              <el-icon><video-play /></el-icon>
              <span>训练执行</span>
            </template>
            <el-menu-item index="/tasks">
              <el-icon><video-play /></el-icon>
              <template #title>训练任务</template>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="resource">
            <template #title>
              <el-icon><data-line /></el-icon>
              <span>算力资源</span>
            </template>
            <el-menu-item index="/resources">
              <el-icon><data-line /></el-icon>
              <template #title>资源概览</template>
            </el-menu-item>
            <el-menu-item index="/node-pools">
              <el-icon><histogram /></el-icon>
              <template #title>节点池</template>
            </el-menu-item>
            <el-menu-item index="/clusters">
              <el-icon><connection /></el-icon>
              <template #title>K8s 集群</template>
            </el-menu-item>
            <el-menu-item index="/workers">
              <el-icon><monitor /></el-icon>
              <template #title>Agent 节点</template>
            </el-menu-item>
            <el-menu-item index="/alerts">
              <el-icon><bell /></el-icon>
              <template #title>
                <span>告警</span>
                <el-badge v-if="alertCount > 0" :value="alertCount" class="alert-badge" type="danger" />
              </template>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu v-if="authStore.isAdmin" index="system">
            <template #title>
              <el-icon><setting /></el-icon>
              <span>系统管理</span>
            </template>
            <el-menu-item index="/users">
              <el-icon><user /></el-icon>
              <template #title>用户管理</template>
            </el-menu-item>
            <el-menu-item index="/logs">
              <el-icon><document /></el-icon>
              <template #title>操作日志</template>
            </el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-scrollbar>
      <div class="collapse-btn" @click="collapsed = !collapsed">
        <el-icon><fold v-if="!collapsed" /><expand v-else /></el-icon>
      </div>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-icon class="collapse-icon" @click="collapsed = !collapsed">
            <expand v-if="collapsed" /><fold v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="$route.meta.title && $route.path !== '/dashboard'">
              {{ $route.meta.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tag v-if="authStore.isAdmin" type="danger" size="small" effect="plain">管理员</el-tag>
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar size="small" :style="{ background: '#1890ff' }">
                {{ userInitial }}
              </el-avatar>
              <span class="username">{{ authStore.user?.username }}</span>
              <el-icon><arrow-down /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><user /></el-icon> 个人设置
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><switch-button /></el-icon> 退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <keep-alive :include="cachedViews">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { alertsApi } from '@/api'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const collapsed = ref(false)
const alertCount = ref(0)
const cachedViews = ref(['Tasks', 'Datasets', 'Algorithms', 'Models'])

const activeMenu = computed(() => {
  const path = route.path
  const segments = path.split('/')
  return '/' + (segments[1] || 'dashboard')
})

const userInitial = computed(() => {
  const u = authStore.user?.username || ''
  return u.charAt(0).toUpperCase()
})

async function handleCommand(cmd) {
  if (cmd === 'logout') {
    await authStore.logout()
    router.push('/login')
  } else if (cmd === 'profile') {
    router.push('/profile')
  }
}

async function fetchAlertCount() {
  try {
    const res = await alertsApi.activeCount()
    alertCount.value = res.data.data.count || 0
  } catch {}
}

onMounted(() => {
  fetchAlertCount()
  setInterval(fetchAlertCount, 30000)
})
</script>

<style scoped>
.main-layout { height: 100vh; }
.sidebar {
  background: linear-gradient(180deg, #1890ff 0%, #1890ff 100%);
  transition: width 0.3s;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 2px 0 8px rgba(0,0,0,0.08);
}
.logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 20px;
  height: 60px;
  min-height: 60px;
  color: #fff;
  cursor: pointer;
  font-weight: 700;
  font-size: 20px;
  white-space: nowrap;
  overflow: hidden;
  border-bottom: 1px solid rgba(255,255,255,0.2);
  background: rgba(0,0,0,0.1);
  flex-shrink: 0;
}
.logo-text { overflow: hidden; }
.menu-scrollbar { flex: 1; overflow: hidden; }
.side-menu {
  border-right: none;
  background: transparent;
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: rgba(255,255,255,0.15);
  --el-menu-active-color: #ffffff;
}
/* 一级菜单项 */
.side-menu :deep(> .el-menu-item) {
  color: #ffffff;
  font-size: 15px;
  height: 50px;
  line-height: 50px;
}
.side-menu :deep(> .el-menu-item:hover) {
  background: rgba(255,255,255,0.1) !important;
}
.side-menu :deep(> .el-menu-item.is-active) {
  background: rgba(255,255,255,0.25) !important;
  font-weight: 500;
}
/* 一级分组标题 */
.side-menu :deep(> .el-sub-menu > .el-sub-menu__title) {
  color: #ffffff;
  font-size: 15px;
  height: 50px;
  line-height: 50px;
}
.side-menu :deep(> .el-sub-menu > .el-sub-menu__title:hover) {
  background: rgba(255,255,255,0.1) !important;
}
.side-menu :deep(> .el-sub-menu.is-opened > .el-sub-menu__title) {
  background: rgba(255,255,255,0.1) !important;
}
/* 二级菜单项 */
.side-menu :deep(> .el-sub-menu > .el-menu > .el-menu-item) {
  color: #ffffff;
  font-size: 14px;
  height: 44px;
  line-height: 44px;
  padding-left: 56px !important;
}
.side-menu :deep(> .el-sub-menu > .el-menu > .el-menu-item:hover) {
  background: rgba(255,255,255,0.15) !important;
}
.side-menu :deep(> .el-sub-menu > .el-menu > .el-menu-item.is-active) {
  background: rgba(255,255,255,0.25) !important;
  font-weight: 500;
}
.side-menu :deep(.el-icon) { color: #ffffff; }
.side-menu :deep(.el-sub-menu__icon-arrow) { color: rgba(255,255,255,0.8); }
.alert-badge { margin-left: 6px; }
.collapse-btn {
  padding: 12px 20px;
  color: rgba(255,255,255,0.6);
  cursor: pointer;
  text-align: center;
  border-top: 1px solid rgba(255,255,255,0.15);
  flex-shrink: 0;
}
.collapse-btn:hover { color: #fff; background: rgba(255,255,255,0.1); }
.header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}
.header-left { display: flex; align-items: center; gap: 16px; }
.collapse-icon { font-size: 20px; cursor: pointer; color: #595959; }
.collapse-icon:hover { color: #1890ff; }
.header-right { display: flex; align-items: center; gap: 12px; }
.user-info { display: flex; align-items: center; gap: 8px; cursor: pointer; color: #333; }
.username { font-size: 14px; }
.main-content { background: #f5f7fa; padding: 20px; overflow-y: auto; }
</style>
