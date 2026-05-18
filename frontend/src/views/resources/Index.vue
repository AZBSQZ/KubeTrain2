<template>
  <div class="resources-page">
    <div class="page-header">
      <div class="header-info">
        <h1>资源概览</h1>
        <p>监控集群资源利用率与配额管理</p>
      </div>
      <div class="header-actions">
        <el-switch v-model="autoRefresh" active-text="自动刷新" size="small" @change="toggleAutoRefresh" />
        <el-button size="small" @click="refreshAll" :loading="refreshing">刷新</el-button>
      </div>
    </div>

    <!-- 摘要统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background:#e6f7ff;color:#1890ff"><el-icon :size="28"><Monitor /></el-icon></div>
          <div>
            <div class="stat-value">{{ overview.total_nodes || 0 }}</div>
            <div class="stat-title">总节点</div>
            <div class="stat-sub">在线 {{ overview.ready_nodes || 0 }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card success">
          <div class="stat-icon"><el-icon :size="28"><Cpu /></el-icon></div>
          <div>
            <div class="stat-value">{{ overview.total_gpus || 0 }}</div>
            <div class="stat-title">GPU 总量</div>
            <div class="stat-sub">可用 {{ (overview.total_gpus || 0) - (overview.used_gpus || 0) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card warning">
          <div class="stat-icon"><el-icon :size="28"><Cpu /></el-icon></div>
          <div>
            <div class="stat-value">{{ overview.total_cpus || 0 }}</div>
            <div class="stat-title">CPU 核心</div>
            <div class="stat-sub">可用 {{ (overview.total_cpus || 0) - (overview.used_cpus || 0) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card info">
          <div class="stat-icon"><el-icon :size="28"><Coin /></el-icon></div>
          <div>
            <div class="stat-value">{{ formatMemory(overview.total_memory) }}</div>
            <div class="stat-title">总内存</div>
            <div class="stat-sub">可用 {{ formatMemory((overview.total_memory || 0) - (overview.used_memory || 0)) }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 利用率仪表盘 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="8">
        <el-card shadow="hover">
          <div class="gauge-wrap">
            <el-progress type="dashboard" :percentage="cpuUtilization" :width="100" :stroke-width="10" :color="gaugeColor">
              <template #default="{ percentage }"><span class="gauge-text">{{ percentage }}%</span></template>
            </el-progress>
            <div class="gauge-label">CPU 平均利用率</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <div class="gauge-wrap">
            <el-progress type="dashboard" :percentage="memoryUtilization" :width="100" :stroke-width="10" :color="gaugeColor">
              <template #default="{ percentage }"><span class="gauge-text">{{ percentage }}%</span></template>
            </el-progress>
            <div class="gauge-label">内存平均利用率</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <div class="gauge-wrap">
            <el-progress type="dashboard" :percentage="gpuUtilization" :width="100" :stroke-width="10" :color="gaugeColor">
              <template #default="{ percentage }"><span class="gauge-text">{{ percentage }}%</span></template>
            </el-progress>
            <div class="gauge-label">GPU 平均利用率</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 标签页 -->
    <el-tabs v-model="activeTab" class="page-tabs">
      <!-- 资源分配 -->
      <el-tab-pane label="资源分配" name="allocations">
        <div class="tab-toolbar">
          <el-switch v-model="allocationsActiveOnly" active-text="仅活跃" @change="loadAllocations" />
          <el-button @click="loadAllocations" :loading="allocLoading" size="small">刷新</el-button>
        </div>
        <el-table :data="allocations" v-loading="allocLoading" stripe size="small">
          <el-table-column label="任务" min-width="180">
            <template #default="{ row }">
              <div class="meta-cell">
                <span>{{ row.task_name || row.task_id }}</span>
                <span class="meta-sub">ID: {{ shortId(row.task_id) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="node_name" label="分配节点" width="140" />
          <el-table-column prop="gpu_allocated" label="GPU" width="80" />
          <el-table-column prop="cpu_allocated" label="CPU" width="80" />
          <el-table-column label="内存" width="100">
            <template #default="{ row }">{{ formatMemory(row.memory_allocated) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '活跃' : '已释放' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="分配时间" width="140">
            <template #default="{ row }">{{ formatTime(row.allocated_at) }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="allocations.length === 0 && !allocLoading" :description="allocationsActiveOnly ? '暂无活跃资源分配' : '暂无资源分配记录'" />
      </el-tab-pane>

      <!-- 资源配额 -->
      <el-tab-pane label="资源配额" name="quotas">
        <div class="tab-toolbar">
          <el-button type="primary" size="small" @click="showAddQuota = true">创建配额</el-button>
          <el-button @click="loadQuotas" :loading="quotaLoading" size="small">刷新</el-button>
        </div>
        <el-table :data="quotas" stripe size="small" v-loading="quotaLoading">
          <el-table-column prop="name" label="配额名称" min-width="140" />
          <el-table-column label="GPU 配额" width="120">
            <template #default="{ row }">
              <span v-if="row.max_gpus > 0">{{ row.used_gpus || 0 }}/{{ row.max_gpus }}</span>
              <span v-else class="text-muted">未限制</span>
            </template>
          </el-table-column>
          <el-table-column label="CPU 配额" width="120">
            <template #default="{ row }">
              <span v-if="row.max_cpus > 0">{{ row.used_cpus || 0 }}/{{ row.max_cpus }}</span>
              <span v-else class="text-muted">未限制</span>
            </template>
          </el-table-column>
          <el-table-column label="任务配额" width="100">
            <template #default="{ row }">{{ row.used_tasks || 0 }}/{{ row.max_tasks }}</template>
          </el-table-column>
          <el-table-column label="启用" width="80" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.is_enabled" @change="toggleQuotaEnabled(row)" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link @click="openEditQuota(row)">编辑</el-button>
              <el-button size="small" link type="danger" @click="deleteQuota(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="quotas.length === 0 && !quotaLoading" description="暂无资源配额" />
      </el-tab-pane>

      <!-- 节点列表 -->
      <el-tab-pane label="节点列表" name="nodes">
        <div class="tab-toolbar">
          <el-select v-model="nodeStatus" placeholder="全部状态" clearable size="small" style="width:120px" @change="loadNodes">
            <el-option label="就绪" value="Ready" />
            <el-option label="离线" value="NotReady" />
          </el-select>
          <el-button @click="loadNodes" :loading="nodesLoading" size="small">刷新</el-button>
        </div>
        <el-table :data="nodes" size="small" v-loading="nodesLoading" stripe>
          <el-table-column label="节点名" prop="name" min-width="140" show-overflow-tooltip />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'Ready' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="GPU" width="100" align="center">
            <template #default="{ row }">{{ row.gpu_used || 0 }}/{{ row.gpu_total || 0 }}</template>
          </el-table-column>
          <el-table-column label="CPU" width="100" align="center">
            <template #default="{ row }">{{ row.cpu_used || '-' }}/{{ row.cpu_total || '-' }}</template>
          </el-table-column>
          <el-table-column label="内存" width="120" align="center">
            <template #default="{ row }">{{ row.memory_used || '-' }}/{{ row.memory_total || '-' }}</template>
          </el-table-column>
          <el-table-column label="IP" prop="ip_address" width="130" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 配额对话框 -->
    <el-dialog v-model="showAddQuota" :title="editingQuota ? '编辑资源配额' : '创建资源配额'" width="500px">
      <el-form :model="quotaForm" label-width="100px">
        <el-form-item label="配额名称" required>
          <el-input v-model="quotaForm.name" placeholder="如：默认配额" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="quotaForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="最大 GPU">
          <el-input-number v-model="quotaForm.max_gpus" :min="0" :max="100" />
          <span class="form-hint">0 表示不限制</span>
        </el-form-item>
        <el-form-item label="最大 CPU">
          <el-input-number v-model="quotaForm.max_cpus" :min="0" :max="1000" />
          <span class="form-hint">核心数</span>
        </el-form-item>
        <el-form-item label="最大内存">
          <el-input-number v-model="quotaForm.max_memory" :min="0" :step="1024" />
          <span class="form-hint">MB (0=不限制)</span>
        </el-form-item>
        <el-form-item label="最大任务数">
          <el-input-number v-model="quotaForm.max_tasks" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="quotaForm.is_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddQuota = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveQuota">{{ editingQuota ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Monitor, Cpu, Coin } from '@element-plus/icons-vue'
import { resourcesApi } from '@/api'

const overview = ref({})
const nodes = ref([])
const quotas = ref([])
const allocations = ref([])
const nodesLoading = ref(false)
const quotaLoading = ref(false)
const allocLoading = ref(false)
const nodeStatus = ref('')
const showAddQuota = ref(false)
const editingQuota = ref(null)
const saving = ref(false)
const autoRefresh = ref(true)
const refreshing = ref(false)
const activeTab = ref('allocations')
const allocationsActiveOnly = ref(true)
let refreshInterval = null

const quotaForm = reactive({
  name: '', description: '', max_gpus: 0, max_cpus: 0, max_memory: 0, max_tasks: 10, is_enabled: true
})

const gaugeColor = [
  { color: '#67c23a', percentage: 50 },
  { color: '#e6a23c', percentage: 80 },
  { color: '#f56c6c', percentage: 100 },
]

const cpuUtilization = computed(() => {
  const d = overview.value
  return d.total_cpus ? Math.round((d.used_cpus || 0) / d.total_cpus * 100) : 0
})
const memoryUtilization = computed(() => {
  const d = overview.value
  return d.total_memory ? Math.round((d.used_memory || 0) / d.total_memory * 100) : 0
})
const gpuUtilization = computed(() => {
  const d = overview.value
  return d.total_gpus ? Math.round((d.used_gpus || 0) / d.total_gpus * 100) : 0
})

const formatTime = (t) => t ? new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'
const formatMemory = (mb) => {
  if (!mb) return '0'
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)}G`
  return `${mb}M`
}
const shortId = (v) => v ? String(v).slice(0, 8) : '-'

async function loadOverview() {
  try {
    const res = await resourcesApi.overview()
    overview.value = res.data.data || {}
  } catch {}
}

async function loadNodes() {
  nodesLoading.value = true
  try {
    const res = await resourcesApi.nodes({ status: nodeStatus.value || undefined, per_page: 100 })
    nodes.value = res.data.data.items || []
  } finally { nodesLoading.value = false }
}

async function loadQuotas() {
  quotaLoading.value = true
  try {
    const res = await resourcesApi.quotas()
    quotas.value = res.data.data || []
  } finally { quotaLoading.value = false }
}

async function loadAllocations() {
  allocLoading.value = true
  try {
    const res = await resourcesApi.allocations({ active: allocationsActiveOnly.value })
    allocations.value = res.data.data || []
  } finally { allocLoading.value = false }
}

function resetQuotaForm() {
  Object.assign(quotaForm, { name: '', description: '', max_gpus: 0, max_cpus: 0, max_memory: 0, max_tasks: 10, is_enabled: true })
  editingQuota.value = null
}

function openEditQuota(row) {
  editingQuota.value = row.id
  Object.assign(quotaForm, {
    name: row.name || '', description: row.description || '',
    max_gpus: row.max_gpus || 0, max_cpus: row.max_cpus || 0,
    max_memory: row.max_memory || 0, max_tasks: row.max_tasks || 10,
    is_enabled: row.is_enabled !== false
  })
  showAddQuota.value = true
}

async function handleSaveQuota() {
  if (!quotaForm.name.trim()) { ElMessage.warning('请输入配额名称'); return }
  saving.value = true
  try {
    const payload = { ...quotaForm }
    if (editingQuota.value) {
      await resourcesApi.updateQuota(editingQuota.value, payload)
      ElMessage.success('配额更新成功')
    } else {
      await resourcesApi.createQuota(payload)
      ElMessage.success('配额创建成功')
    }
    showAddQuota.value = false
    resetQuotaForm()
    loadQuotas()
  } finally { saving.value = false }
}

async function toggleQuotaEnabled(row) {
  try {
    await resourcesApi.updateQuota(row.id, { is_enabled: row.is_enabled })
    ElMessage.success(`配额已${row.is_enabled ? '启用' : '停用'}`)
  } catch { row.is_enabled = !row.is_enabled }
}

async function deleteQuota(row) {
  await ElMessageBox.confirm(`确认删除配额 "${row.name}"？`, '删除确认', { type: 'warning' })
  await resourcesApi.deleteQuota(row.id)
  ElMessage.success('删除成功')
  loadQuotas()
}

async function refreshAll() {
  refreshing.value = true
  try {
    await Promise.all([loadOverview(), loadNodes(), loadQuotas(), loadAllocations()])
  } finally { refreshing.value = false }
}

function toggleAutoRefresh(val) {
  if (val) {
    refreshInterval = setInterval(refreshAll, 10000)
  } else {
    if (refreshInterval) clearInterval(refreshInterval)
  }
}

onMounted(() => {
  loadOverview()
  loadNodes()
  loadQuotas()
  loadAllocations()
  if (autoRefresh.value) {
    refreshInterval = setInterval(refreshAll, 10000)
  }
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
})
</script>

<style scoped>
.resources-page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
.header-actions { display: flex; align-items: center; gap: 12px; }
.stat-row { margin-bottom: 16px; }
.stat-card {
  display: flex; align-items: center;
}
.stat-card :deep(.el-card__body) { display: flex; align-items: center; gap: 16px; padding: 20px; width: 100%; }
.stat-icon { width: 60px; height: 60px; border-radius: 12px; display: flex; align-items: center; justify-content: center; background: #e6f7ff; color: #1890ff; }
.stat-card.success .stat-icon { background: #f6ffed; color: #52c41a; }
.stat-card.warning .stat-icon { background: #fffbe6; color: #faad14; }
.stat-card.info .stat-icon { background: #e6f7ff; color: #1890ff; }
.stat-value { font-size: 28px; font-weight: 600; color: #303133; }
.stat-title { color: #909399; font-size: 14px; margin-top: 4px; }
.stat-sub { font-size: 14px; color: #909399; }
.gauge-wrap { display: flex; flex-direction: column; align-items: center; padding: 8px 0; }
.gauge-text { font-size: 18px; font-weight: 600; color: #303133; }
.gauge-label { margin-top: 6px; font-size: 13px; color: #606266; }
.page-tabs { margin-top: 4px; }
.tab-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.text-muted { color: #c0c4cc; }
.form-hint { margin-left: 8px; color: #909399; font-size: 12px; }
.meta-cell { display: flex; flex-direction: column; gap: 2px; }
.meta-sub { font-size: 12px; color: #909399; }
</style>
