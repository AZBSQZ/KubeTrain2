<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-info">
        <h1>Worker 管理</h1>
        <p>管理计算节点与 GPU 资源</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="registerDialogVisible = true" v-if="authStore.isAdmin">
          注册计算节点
        </el-button>
        <el-button @click="probeWorkers" :loading="probing" type="warning">
          探活检测
        </el-button>
        <el-button @click="loadWorkers" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 - 6列布局 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ stats.total || 0 }}</div>
          <div class="stat-label">总节点</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #67c23a">{{ stats.online || 0 }}</div>
          <div class="stat-label">在线</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #409eff">{{ stats.idle || 0 }}</div>
          <div class="stat-label">空闲</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #e6a23c">{{ stats.busy || 0 }}</div>
          <div class="stat-label">忙碌</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #f56c6c">{{ stats.offline || 0 }}</div>
          <div class="stat-label">离线</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ stats.total_gpu || 0 }} / {{ stats.available_gpu || 0 }}</div>
          <div class="stat-label">GPU 总/可用</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 节点列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Worker 节点列表</span>
          <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 120px" @change="loadWorkers">
            <el-option label="空闲" value="idle" />
            <el-option label="忙碌" value="busy" />
            <el-option label="离线" value="offline" />
          </el-select>
        </div>
      </template>
      <el-table v-loading="loading" :data="workers" stripe style="width: 100%">
        <el-table-column prop="name" label="节点名称" min-width="120" />
        <el-table-column prop="ip_address" label="IP" width="130" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="workerStatusType(row.status)" size="small">
              <span :class="['status-dot', { online: row.is_online }]"></span>
              {{ STATUS_LABEL[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="GPU" width="160">
          <template #default="{ row }">
            <span v-if="row.gpu_total > 0">{{ row.gpu_model || 'GPU' }} × {{ row.gpu_total }}</span>
            <span v-else style="color: #909399">无</span>
          </template>
        </el-table-column>
        <el-table-column label="CPU" width="80">
          <template #default="{ row }">{{ row.cpu_total || 0 }} 核</template>
        </el-table-column>
        <el-table-column label="内存" width="80">
          <template #default="{ row }">{{ formatMem(row.memory_total) }}</template>
        </el-table-column>
        <el-table-column label="任务槽位" width="110">
          <template #default="{ row }">
            <el-progress :percentage="row.max_tasks > 0 ? Math.round((row.tasks_running || 0) / row.max_tasks * 100) : 0" :stroke-width="10" />
            <span class="slot-text">{{ row.tasks_running || 0 }}/{{ row.max_tasks || 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="GPU利用率" width="100">
          <template #default="{ row }">
            <el-progress :percentage="row.gpu_utilization || 0" :stroke-width="8" />
          </template>
        </el-table-column>
        <el-table-column label="能力" width="140">
          <template #default="{ row }">
            <el-tag v-for="cap in (row.capabilities || []).slice(0, 3)" :key="cap" size="small" type="info" style="margin: 1px">{{ cap }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后心跳" width="140">
          <template #default="{ row }">{{ formatTime(row.last_heartbeat) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="showDetail(row)">详情</el-button>
            <el-button v-if="authStore.isAdmin" link size="small" @click="openEditDialog(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 注册计算节点对话框 -->
    <RegisterDialog v-model="registerDialogVisible" @refresh="loadWorkers" />

    <!-- Worker 详情对话框 -->
    <el-dialog v-model="detailVisible" title="Worker 详情" width="600px">
      <el-descriptions :column="2" border size="small" v-if="selectedWorker">
        <el-descriptions-item label="名称">{{ selectedWorker.name }}</el-descriptions-item>
        <el-descriptions-item label="IP">{{ selectedWorker.ip_address }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="workerStatusType(selectedWorker.status)" size="small">{{ selectedWorker.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Worker ID">{{ selectedWorker.worker_id || selectedWorker.id }}</el-descriptions-item>
        <el-descriptions-item label="Agent 版本">{{ selectedWorker.agent_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Python">{{ selectedWorker.python_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="CUDA">{{ selectedWorker.cuda_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="NCCL">{{ selectedWorker.nccl_available ? '✓' : '✗' }}</el-descriptions-item>
        <el-descriptions-item label="容器运行时" :span="2">{{ selectedWorker.container_runtime || '-' }}</el-descriptions-item>
        <el-descriptions-item label="GPU 详情" :span="2">
          <div v-if="selectedWorker.gpu_details && selectedWorker.gpu_details.length > 0">
            <div v-for="(g, i) in selectedWorker.gpu_details" :key="i">GPU{{ g.index }}: {{ g.name }} ({{ g.memory_mb }}MB)</div>
          </div>
          <span v-else>{{ selectedWorker.gpu_total > 0 ? `${selectedWorker.gpu_model} × ${selectedWorker.gpu_total}` : '无 GPU' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="能力标签" :span="2">
          <el-tag v-for="cap in (selectedWorker.capabilities || [])" :key="cap" size="small" style="margin: 2px">{{ cap }}</el-tag>
          <span v-if="!selectedWorker.capabilities?.length">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="注册时间">{{ formatTime(selectedWorker.registered_at) }}</el-descriptions-item>
        <el-descriptions-item label="心跳间隔">{{ selectedWorker.heartbeat_interval || 30 }}s</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button v-if="authStore.isAdmin" type="primary" @click="detailVisible = false; openEditDialog(selectedWorker)">编辑</el-button>
        <el-button v-if="authStore.isAdmin" type="danger" @click="handleDeregister(selectedWorker); detailVisible = false">注销</el-button>
      </template>
    </el-dialog>

    <!-- 编辑节点对话框 -->
    <el-dialog v-model="dialogVisible" title="编辑节点" width="520px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="节点名称" prop="name">
          <el-input v-model="form.name" placeholder="如: gpu-node-01" />
        </el-form-item>
        <el-form-item label="IP 地址" prop="ip_address">
          <el-input v-model="form.ip_address" placeholder="192.168.1.100" />
        </el-form-item>
        <el-form-item label="CPU 核数">
          <el-input-number v-model="form.cpu_total" :min="1" :max="128" />
        </el-form-item>
        <el-form-item label="内存 (MB)">
          <el-input-number v-model="form.memory_total" :min="1024" :step="1024" />
        </el-form-item>
        <el-form-item label="GPU 数量">
          <el-input-number v-model="form.gpu_total" :min="0" :max="16" />
        </el-form-item>
        <el-form-item label="GPU 型号">
          <el-input v-model="form.gpu_model" placeholder="如: NVIDIA RTX 3090" />
        </el-form-item>
        <el-form-item label="最大任务数">
          <el-input-number v-model="form.max_tasks" :min="1" :max="16" />
        </el-form-item>
        <el-form-item label="能力标签">
          <el-select v-model="form.capabilities" multiple allow-create filterable placeholder="选择或输入能力" style="width: 100%">
            <el-option label="gpu" value="gpu" />
            <el-option label="docker" value="docker" />
            <el-option label="cuda" value="cuda" />
            <el-option label="nccl" value="nccl" />
            <el-option label="ddp" value="ddp" />
            <el-option label="fsdp" value="fsdp" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { workersApi, nodePoolsApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import RegisterDialog from './RegisterDialog.vue'

const loading = ref(false)
const saving = ref(false)
const probing = ref(false)
const registerDialogVisible = ref(false)
const workers = ref([])
const pools = ref([])
const stats = ref({ total: 0, online: 0, idle: 0, busy: 0, offline: 0, total_gpu: 0, available_gpu: 0 })
const authStore = useAuthStore()
const dialogVisible = ref(false)
const detailVisible = ref(false)
const selectedWorker = ref(null)
const statusFilter = ref('')
const editingId = ref(null)
const formRef = ref()
let timer = null

const STATUS_LABEL = { online: '在线', busy: '忙碌', idle: '空闲', offline: '离线', error: '异常' }

const defaultForm = () => ({
  name: '', ip_address: '', cpu_total: 8, memory_total: 16384,
  gpu_total: 0, gpu_model: '', max_tasks: 2, capabilities: []
})
const form = reactive(defaultForm())

const formRules = {
  ip_address: [{ required: true, message: 'IP 地址不能为空', trigger: 'blur' }],
}

function workerStatusType(s) {
  return { online: 'success', busy: 'warning', idle: 'success', offline: 'danger', error: 'danger' }[s] || 'info'
}
function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-' }
function formatMem(mb) {
  if (!mb) return '0'
  if (mb >= 1024) return (mb / 1024).toFixed(1) + 'G'
  return mb + 'M'
}
function showDetail(worker) {
  selectedWorker.value = worker
  detailVisible.value = true
}

async function loadWorkers() {
  loading.value = true
  try {
    const params = { probe: 'false' }
    if (statusFilter.value) params.status = statusFilter.value
    const res = await workersApi.status(params)
    workers.value = res.data.data || []
    await loadStats()
  } finally { loading.value = false }
}

async function loadStats() {
  try {
    const res = await workersApi.stats()
    const s = res.data.data || {}
    stats.value = {
      total: s.total_workers || workers.value.length,
      online: s.online_workers || 0,
      idle: s.idle_workers || 0,
      busy: s.busy_workers || 0,
      offline: s.offline_workers || 0,
      total_gpu: s.total_gpu || 0,
      available_gpu: s.available_gpu || 0,
    }
  } catch {
    // fallback to local calculation
    stats.value = {
      total: workers.value.length,
      online: workers.value.filter(w => ['online', 'idle'].includes(w.status)).length,
      idle: workers.value.filter(w => w.status === 'idle').length,
      busy: workers.value.filter(w => w.status === 'busy').length,
      offline: workers.value.filter(w => ['offline', 'error'].includes(w.status)).length,
      total_gpu: workers.value.reduce((sum, w) => sum + (w.gpu_total || 0), 0),
      available_gpu: workers.value.reduce((sum, w) => sum + (w.gpu_available || 0), 0),
    }
  }
}

async function loadPools() {
  try {
    const res = await nodePoolsApi.list()
    pools.value = res.data.data || res.data?.data?.items || []
  } catch {}
}

function openEditDialog(row) {
  editingId.value = row.id
  Object.assign(form, {
    name: row.name || '',
    ip_address: row.ip_address || '',
    cpu_total: row.cpu_total || 8,
    memory_total: row.memory_total || 16384,
    gpu_total: row.gpu_total || 0,
    gpu_model: row.gpu_model || '',
    max_tasks: row.max_tasks || 2,
    capabilities: row.capabilities || [],
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = {
      name: form.name || form.ip_address,
      ip_address: form.ip_address,
      cpu_total: form.cpu_total,
      memory_total: form.memory_total,
      gpu_total: form.gpu_total,
      gpu_model: form.gpu_model,
      max_tasks: form.max_tasks,
      capabilities: form.capabilities,
    }
    await workersApi.update(editingId.value, payload)
    ElMessage.success('节点信息已更新')
    dialogVisible.value = false
    loadWorkers()
  } finally { saving.value = false }
}

async function handleDeregister(row) {
  await ElMessageBox.confirm(
    `确认注销 Worker "${row.name || row.id}"？节点数据将被删除。`,
    '注销 Worker', { type: 'warning' }
  )
  await workersApi.deregister(row.id)
  ElMessage.success('已注销')
  loadWorkers()
}

async function probeWorkers() {
  probing.value = true
  try {
    const res = await workersApi.status({ probe: true })
    workers.value = res.data.data || []
    updateStats()
    ElMessage.success('探活检测完成')
  } catch (e) {
    ElMessage.error('探活失败: ' + (e.response?.data?.message || e.message))
  } finally {
    probing.value = false
  }
}

function updateStats() {
  stats.value = {
    total: workers.value.length,
    online: workers.value.filter(w => ['online', 'idle'].includes(w.status)).length,
    idle: workers.value.filter(w => w.status === 'idle').length,
    busy: workers.value.filter(w => w.status === 'busy').length,
    offline: workers.value.filter(w => ['offline', 'error'].includes(w.status)).length,
    total_gpu: workers.value.reduce((sum, w) => sum + (w.gpu_total || 0), 0),
    available_gpu: workers.value.reduce((sum, w) => sum + (w.gpu_available || 0), 0),
  }
}

onMounted(() => { loadWorkers(); loadPools(); timer = setInterval(loadWorkers, 15000) })
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.page-container { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
.header-actions { display: flex; gap: 8px; }
.stat-row { margin-bottom: 16px !important; }
.stat-card { text-align: center; }
.stat-value { font-size: 24px; font-weight: bold; }
.stat-label { font-size: 12px; color: #909399; margin-top: 4px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.slot-text { font-size: 12px; color: #909399; }
.status-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 4px; background: #909399; }
.status-dot.online { background: #67c23a; }
</style>
