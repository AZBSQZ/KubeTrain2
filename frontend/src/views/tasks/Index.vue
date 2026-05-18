<template>
  <div class="page-container">
    <!-- 统计摘要卡片（对齐FTv1） -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ taskStats.total }}</div>
          <div class="stat-label">全部任务</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card stat-running">
          <div class="stat-value">{{ taskStats.running }}</div>
          <div class="stat-label">运行中</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card stat-pending">
          <div class="stat-value">{{ taskStats.pending + taskStats.queued }}</div>
          <div class="stat-label">待运行</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card stat-completed">
          <div class="stat-value">{{ taskStats.completed }}</div>
          <div class="stat-label">已完成</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card stat-failed">
          <div class="stat-value">{{ taskStats.failed }}</div>
          <div class="stat-label">失败</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card stat-cancelled">
          <div class="stat-value">{{ taskStats.cancelled }}</div>
          <div class="stat-label">已取消</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <div class="table-header">
        <span class="table-title">训练任务</span>
        <div class="table-actions">
          <el-input v-model="filters.search" placeholder="搜索任务名称" clearable @keyup.enter="loadTasks" prefix-icon="Search" style="width: 200px" />
          <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px" @change="loadTasks">
            <el-option label="等待中" value="pending" />
            <el-option label="运行中" value="running" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
          </el-select>
          <el-button type="primary" @click="loadTasks">搜索</el-button>
          <el-button type="primary" @click="showCreateDialog">
            <el-icon><plus /></el-icon>新建任务
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="tasks" stripe style="width:100%">
        <el-table-column type="selection" width="50" />
        <el-table-column label="任务名称" prop="name" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/tasks/${row.id}`)">{{ row.name }}</el-link>
            <el-tag v-if="row.is_pipeline" type="warning" size="small" style="margin-left: 6px;">流水线</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="训练模式" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.parallel_mode && row.parallel_mode !== 'single'" type="primary" size="small">{{ row.parallel_mode.toUpperCase() }}</el-tag>
            <span v-else style="color: #909399;">单机</span>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="160">
          <template #default="{ row }">
            <div v-if="row.total_epochs" class="epoch-progress">
              <el-progress :percentage="Math.round((row.current_epoch||0)/row.total_epochs*100)" :stroke-width="6" />
              <span class="ep-text">{{ row.current_epoch || 0 }}/{{ row.total_epochs }}</span>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="160">
          <template #default="{ row }">{{ formatTime(row.updated_at || row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/tasks/${row.id}`)">查看详情</el-button>
            <el-button v-if="!['running','starting','queued','assigned'].includes(row.status)"
              size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page" v-model:page-size="pageSize"
        :total="total" layout="total, sizes, prev, pager, next"
        :page-sizes="[10, 20, 50]" @change="loadTasks" class="pagination" />
    </el-card>

    <!-- 新建任务对话框（对齐FTv1实验创建） -->
    <el-dialog v-model="createDialogVisible" title="新建训练任务" width="720px" destroy-on-close top="3vh">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="120px">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="数据集">
          <el-select v-model="selectedDatasetId" placeholder="选择数据集" filterable clearable style="width: 100%; margin-bottom: 6px" @change="onDatasetChange">
            <el-option v-for="d in datasetList" :key="d.id" :label="d.name" :value="d.id">
              <div style="display:flex;flex-direction:column;padding:4px 0;line-height:1.4">
                <span style="font-weight:600;font-size:14px;color:#303133">{{ d.name }}</span>
                <span style="font-size:12px;color:#909399">{{ d.description || '暂无描述' }}</span>
              </div>
            </el-option>
          </el-select>
          <el-select v-if="selectedDatasetId && datasetVersions.length" v-model="createForm.dataset_version_id" placeholder="选择版本" filterable style="width: 100%">
            <el-option v-for="v in datasetVersions" :key="v.id" :label="`v${v.version_number}` + (v.version_tag ? ` (${v.version_tag})` : '')" :value="v.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="算法" prop="algorithm_version_id">
          <el-select v-model="selectedAlgorithmId" placeholder="选择算法" filterable style="width: 100%; margin-bottom: 6px" @change="onAlgorithmChange">
            <el-option v-for="a in algorithmList" :key="a.id" :label="a.name" :value="a.id">
              <div style="display:flex;flex-direction:column;padding:4px 0;line-height:1.4">
                <span style="font-weight:600;font-size:14px;color:#303133">{{ a.name }}</span>
                <span style="font-size:12px;color:#909399">{{ a.description || '暂无描述' }}</span>
              </div>
            </el-option>
          </el-select>
          <el-select v-if="selectedAlgorithmId && algorithmVersions.length" v-model="createForm.algorithm_version_id" placeholder="选择版本" filterable style="width: 100%" @change="onAlgorithmVersionChange">
            <el-option v-for="v in algorithmVersions" :key="v.id" :label="`v${v.version_number}`" :value="v.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="预训练模型">
          <el-select v-model="selectedModelId" placeholder="选择模型（可选）" filterable clearable style="width: 100%; margin-bottom: 6px" @change="onModelChange">
            <el-option v-for="m in modelList" :key="m.id" :label="m.name" :value="m.id">
              <div style="display:flex;flex-direction:column;padding:4px 0;line-height:1.4">
                <span style="font-weight:600;font-size:14px;color:#303133">{{ m.name }}</span>
                <span style="font-size:12px;color:#909399">{{ m.description || '暂无描述' }}</span>
              </div>
            </el-option>
          </el-select>
          <el-select v-if="selectedModelId && modelVersions.length" v-model="createForm.model_version_id" placeholder="选择版本" filterable clearable style="width: 100%">
            <el-option v-for="v in modelVersions" :key="v.id" :label="`v${v.version_number}`" :value="v.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="训练配置">
          <div class="config-inputs">
            <div v-if="!createForm.algorithm_version_id" class="config-tip">
              <el-icon><InfoFilled /></el-icon>
              请先选择算法版本，参数将自动加载
            </div>
            <template v-else>
              <div class="config-tip">
                <el-icon><InfoFilled /></el-icon>
                共 {{ algoParams.length }} 个参数，留空使用脚本默认值，填写则覆盖默认值
              </div>
              <div class="param-grid">
                <div class="param-row" v-for="param in algoParams" :key="param.name">
                  <div class="param-row-label">
                    <span class="param-display-name">{{ param.label || param.name }}</span>
                    <span class="param-code-name">{{ param.name }}</span>
                  </div>
                  <div class="param-row-input">
                    <el-input-number v-if="param.type === 'int'" v-model="createForm.configObj[param.name]" :min="0" size="small" :placeholder="String(param.default_value ?? '默认')" controls-position="right" style="width: 100%;" />
                    <el-input-number v-else-if="param.type === 'float'" v-model="createForm.configObj[param.name]" :step="0.0001" :precision="5" size="small" :placeholder="String(param.default_value ?? '默认')" controls-position="right" style="width: 100%;" />
                    <el-input v-else v-model="createForm.configObj[param.name]" size="small" :placeholder="String(param.default_value ?? '默认')" />
                  </div>
                </div>
              </div>
              <el-button size="small" text type="primary" @click="clearConfig" style="margin-top:6px">
                <el-icon><RefreshLeft /></el-icon>清空配置（使用脚本默认值）
              </el-button>
            </template>
          </div>
        </el-form-item>
        <el-form-item label="训练模式">
          <div class="train-mode-selector">
            <el-radio-group v-model="createForm.parallel_mode">
              <el-radio value="single">单机训练</el-radio>
              <el-radio value="local_ddp">单机多进程 (DDP)</el-radio>
              <el-radio value="distributed" :disabled="!canDistributed">多节点分布式 (DDP)</el-radio>
            </el-radio-group>
            <template v-if="createForm.parallel_mode === 'local_ddp'">
              <div style="display: flex; align-items: center; gap: 12px; margin-top: 8px;">
                <span style="font-size: 13px; color: #606266;">进程数:</span>
                <el-input-number v-model="createForm.nproc_per_node" :min="2" :max="16" size="small" />
                <el-tag size="small" type="info">单机内 torchrun --standalone 启动多 worker</el-tag>
              </div>
            </template>
            <template v-if="createForm.parallel_mode === 'distributed'">
              <div style="display: flex; align-items: center; gap: 12px; margin-top: 8px;">
                <span style="font-size: 13px; color: #606266;">节点数:</span>
                <el-input-number v-model="createForm.num_nodes" :min="2" :max="availableNodeCount || 8" size="small" />
                <span style="font-size: 13px; color: #606266;">每节点 GPU (0=纯CPU):</span>
                <el-input-number v-model="createForm.gpus_per_node" :min="0" :max="8" size="small" />
              </div>
            </template>
            <div style="font-size: 12px; margin-top: 4px;">
              <template v-if="loadingResources">
                <span style="color: #909399;">正在检测资源节点状态...</span>
              </template>
              <template v-else-if="availableNodeCount === 0">
                <span style="color: #F56C6C;">未检测到在线计算节点，请先在算力资源中注册节点</span>
              </template>
              <template v-else>
                <span style="color: #67C23A;">{{ availableNodeCount }} 个在线节点可用</span>
              </template>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="任务描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreateTask">创建任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled, RefreshLeft } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { tasksApi, algorithmsApi, modelsApi, datasetsApi, resourcesApi } from '@/api'

const router = useRouter()

const loading = ref(false)
const tasks = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ search: '', status: '' })

// 统计
const taskStats = reactive({ total: 0, running: 0, pending: 0, completed: 0, failed: 0, cancelled: 0, queued: 0 })

// 创建对话框
const createDialogVisible = ref(false)
const creating = ref(false)
const createFormRef = ref()
const createForm = reactive({
  name: '', description: '',
  algorithm_version_id: null, model_version_id: null, dataset_version_id: null,
  parallel_mode: 'single', num_nodes: 2, gpus_per_node: 1, nproc_per_node: 2,
  configObj: {},
})
const createRules = {
  name: [{ required: true, message: '任务名称不能为空', trigger: 'blur' }],
}

// 资源选择器数据
const datasetList = ref([])
const algorithmList = ref([])
const modelList = ref([])
const selectedDatasetId = ref(null)
const selectedAlgorithmId = ref(null)
const selectedModelId = ref(null)
const datasetVersions = ref([])
const algorithmVersions = ref([])
const modelVersions = ref([])
const algoParams = ref([])
const loadingResources = ref(false)
const availableNodeCount = ref(0)
const canDistributed = computed(() => availableNodeCount.value >= 2)

const STATUS_LABEL = { pending: '等待中', queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消', starting: '启动中', assigned: '已分配' }
function statusLabel(s) { return STATUS_LABEL[s] || s }
function statusType(s) {
  return { running: 'success', failed: 'danger', completed: '', pending: 'info', queued: 'warning', cancelled: 'info' }[s] || 'info'
}
function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-' }
function resetFilters() { Object.assign(filters, { search: '', status: '' }); loadTasks() }

async function loadStats() {
  try {
    const res = await tasksApi.stats()
    if (res.data.code === 200) Object.assign(taskStats, res.data.data)
  } catch (_) {}
}

async function loadTasks() {
  loading.value = true
  try {
    const res = await tasksApi.list({ page: page.value, per_page: pageSize.value, ...filters })
    tasks.value = res.data.data.items
    total.value = res.data.data.total
  } finally { loading.value = false }
  loadStats()
}

// ---- 创建对话框逻辑 ----
async function loadResourceLists() {
  try {
    const [dsRes, algoRes, modelRes] = await Promise.all([
      datasetsApi.list({ per_page: 200 }),
      algorithmsApi.list({ per_page: 200 }),
      modelsApi.list({ per_page: 200 }),
    ])
    datasetList.value = dsRes.data.data?.items || []
    algorithmList.value = algoRes.data.data?.items || []
    modelList.value = modelRes.data.data?.items || []
  } catch (_) {}
}

async function loadComputeResources() {
  loadingResources.value = true
  try {
    const res = await resourcesApi.computeResources()
    if (res.data.code === 200) {
      availableNodeCount.value = res.data.data.summary?.online_nodes || 0
    }
  } catch (_) {
    availableNodeCount.value = 0
  } finally { loadingResources.value = false }
}

async function onDatasetChange(dsId) {
  datasetVersions.value = []
  createForm.dataset_version_id = null
  if (!dsId) return
  try {
    const res = await datasetsApi.versions(dsId)
    datasetVersions.value = res.data.data || []
    if (datasetVersions.value.length === 1) createForm.dataset_version_id = datasetVersions.value[0].id
  } catch (_) {}
}

async function onAlgorithmChange(algoId) {
  algorithmVersions.value = []
  createForm.algorithm_version_id = null
  algoParams.value = []
  createForm.configObj = {}
  if (!algoId) return
  try {
    const res = await algorithmsApi.versions(algoId)
    algorithmVersions.value = res.data.data || []
    if (algorithmVersions.value.length === 1) {
      createForm.algorithm_version_id = algorithmVersions.value[0].id
      onAlgorithmVersionChange(algorithmVersions.value[0].id)
    }
  } catch (_) {}
}

async function onAlgorithmVersionChange(versionId) {
  algoParams.value = []
  createForm.configObj = {}
  if (!versionId) return
  try {
    const res = await algorithmsApi.getVersion(versionId)
    const params = res.data.data?.parameters || []
    algoParams.value = params
    const obj = {}
    params.forEach(p => {
      if (p.default_value !== undefined && p.default_value !== '') {
        if (p.type === 'int') obj[p.name] = parseInt(p.default_value)
        else if (p.type === 'float') obj[p.name] = parseFloat(p.default_value)
        else obj[p.name] = p.default_value
      }
    })
    createForm.configObj = obj
  } catch (_) {}
}

async function onModelChange(modelId) {
  modelVersions.value = []
  createForm.model_version_id = null
  if (!modelId) return
  try {
    const res = await modelsApi.versions(modelId)
    modelVersions.value = res.data.data || []
    if (modelVersions.value.length === 1) createForm.model_version_id = modelVersions.value[0].id
  } catch (_) {}
}

function clearConfig() {
  createForm.configObj = {}
}

function showCreateDialog() {
  Object.assign(createForm, {
    name: '', description: '',
    algorithm_version_id: null, model_version_id: null, dataset_version_id: null,
    parallel_mode: 'single', num_nodes: 2, gpus_per_node: 1, nproc_per_node: 2,
    configObj: {},
  })
  selectedDatasetId.value = null
  selectedAlgorithmId.value = null
  selectedModelId.value = null
  datasetVersions.value = []
  algorithmVersions.value = []
  modelVersions.value = []
  algoParams.value = []
  createDialogVisible.value = true
  loadResourceLists()
  loadComputeResources()
}

async function handleCreateTask() {
  await createFormRef.value.validate()

  if (!createForm.algorithm_version_id) {
    ElMessage.warning('请选择算法版本')
    return
  }

  creating.value = true
  try {
    // 构建训练参数（只提交非空值）
    const training_args = {}
    for (const [k, v] of Object.entries(createForm.configObj)) {
      if (v !== undefined && v !== null && v !== '') training_args[k] = v
    }

    const payload = {
      name: createForm.name,
      description: createForm.description,
      algorithm_version_id: createForm.algorithm_version_id,
      model_version_id: createForm.model_version_id,
      dataset_id: selectedDatasetId.value,
      dataset_version_id: createForm.dataset_version_id,
      parallel_mode: createForm.parallel_mode,
      training_args: Object.keys(training_args).length > 0 ? training_args : undefined,
    }

    if (createForm.parallel_mode === 'local_ddp') {
      payload.nproc_per_node = createForm.nproc_per_node
    } else if (createForm.parallel_mode === 'distributed') {
      payload.num_nodes = createForm.num_nodes
      payload.gpus_per_node = createForm.gpus_per_node
    }

    const res = await tasksApi.create(payload)
    if (res.data.code === 200) {
      const taskId = res.data.data?.id
      createDialogVisible.value = false
      // 对齐FTv1：创建后自动提交并跳转监控页
      if (taskId) {
        try {
          await tasksApi.submit(taskId)
          ElMessage.success('任务已创建并提交')
        } catch {
          ElMessage.success('任务创建成功（自动提交失败，请手动提交）')
        }
        router.push(`/tasks/${taskId}`)
      } else {
        ElMessage.success('任务创建成功')
        loadTasks()
      }
    } else {
      ElMessage.error(res.data.message || '创建失败')
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.message || '创建失败')
  } finally { creating.value = false }
}

// ---- 列表操作 ----
async function handleSubmit(row) {
  await tasksApi.submit(row.id)
  ElMessage.success('任务已提交')
  loadTasks()
}
async function handleCancel(row) {
  await ElMessageBox.confirm(`确认取消任务 "${row.name}"？`, '取消任务', { type: 'warning' })
  await tasksApi.cancel(row.id)
  ElMessage.success('任务已取消')
  loadTasks()
}
async function handleRetry(row) {
  await tasksApi.retry(row.id)
  ElMessage.success('任务已重新提交')
  loadTasks()
}
async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除任务 "${row.name}"？`, '删除任务', { type: 'warning' })
  await tasksApi.delete(row.id)
  ElMessage.success('删除成功')
  loadTasks()
}

async function handleClone(row) {
  try {
    await tasksApi.clone(row.id)
    ElMessage.success('任务克隆成功')
    loadTasks()
  } catch (e) {
    ElMessage.error('克隆失败: ' + (e.response?.data?.message || e.message))
  }
}

onMounted(loadTasks)
</script>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; padding: 20px; }
.table-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.table-title { font-size: 18px; font-weight: 600; color: #303133; }
.table-actions { display: flex; align-items: center; gap: 10px; }
.epoch-progress { display: flex; align-items: center; gap: 8px; }
.ep-text { font-size: 12px; color: #888; white-space: nowrap; }
.text-muted { color: #ccc; font-size: 13px; }
.pagination { margin-top: 16px; justify-content: flex-end; display: flex; }

.stats-row { margin-bottom: 16px; }
.stat-card { text-align: center; border-radius: 8px; }
.stat-card :deep(.el-card__body) { padding: 16px 12px; }
.stat-value { font-size: 28px; font-weight: 700; color: #303133; line-height: 1.2; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.stat-running .stat-value { color: #67C23A; }
.stat-pending .stat-value { color: #E6A23C; }
.stat-completed .stat-value { color: #409EFF; }
.stat-failed .stat-value { color: #F56C6C; }
.stat-cancelled .stat-value { color: #909399; }

.config-inputs { width: 100%; }
.config-tip { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #909399; margin-bottom: 8px; }
.param-grid { display: flex; flex-direction: column; gap: 8px; }
.param-row { display: flex; align-items: center; gap: 12px; }
.param-row-label { min-width: 140px; display: flex; flex-direction: column; }
.param-display-name { font-size: 13px; font-weight: 600; color: #303133; }
.param-code-name { font-size: 11px; color: #909399; font-family: 'Consolas', monospace; }
.param-row-input { flex: 1; }

.train-mode-selector { width: 100%; }
:deep(.el-dialog__body) { padding: 16px 24px; max-height: 70vh; overflow-y: auto; }
</style>
