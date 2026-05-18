<template>
  <div class="version-detail-page">
    <!-- 页面标题栏（对齐FTv1 VersionDetail） -->
    <div class="page-header">
      <div class="header-left">
        <el-button text @click="$router.push('/tasks')">
          <el-icon><arrow-left /></el-icon>返回
        </el-button>
        <h2 class="page-title">任务详情</h2>
        <span v-if="task.name" class="experiment-label">{{ task.name }}</span>
        <el-tag :type="statusType(task.status)" size="large">{{ statusLabel(task.status) }}</el-tag>
      </div>
      <div class="header-actions">
        <el-tooltip :content="autoRefresh ? '自动刷新已开启' : '自动刷新已关闭'" placement="bottom">
          <el-switch v-model="autoRefresh" active-text="自动" inactive-text="" style="margin-right: 8px;" />
        </el-tooltip>
        <el-button @click="handleRefreshAll" :loading="refreshing">
          <el-icon><refresh /></el-icon>刷新
        </el-button>
        <el-button v-if="task.status === 'pending'" type="success" @click="handleSubmit">
          <el-icon><video-play /></el-icon>提交训练
        </el-button>
        <el-button v-if="task.status === 'failed'" type="success" @click="handleRetry">
          <el-icon><refresh-right /></el-icon>重试
        </el-button>
        <el-button v-if="['running','queued','starting','assigned'].includes(task.status)"
          type="danger" @click="handleCancel">
          <el-icon><close /></el-icon>终止
        </el-button>
      </div>
    </div>

    <el-row :gutter="20">
      <!-- 左侧：基本信息 + 训练参数 + 进度 + 结果 + 产出 + 图表 -->
      <el-col :span="16">
        <!-- 基本信息 -->
        <el-card style="margin-bottom: 16px;" v-loading="initialLoading">
          <template #header><span class="card-title">基本信息</span></template>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="状态">
              <el-tag :type="statusType(task.status)" size="small">{{ statusLabel(task.status) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="执行模式">{{ task.execution_mode || '-' }}</el-descriptions-item>
            <el-descriptions-item label="并行模式">
              <el-tag v-if="task.parallel_mode && task.parallel_mode !== 'single'" type="primary" size="small">{{ task.parallel_mode.toUpperCase() }}</el-tag>
              <span v-else>单机</span>
            </el-descriptions-item>
            <el-descriptions-item label="数据集">
              <span v-if="task.dataset_name">{{ task.dataset_name }}</span>
              <el-text v-else-if="task.dataset_path" truncated style="max-width: 200px">{{ task.dataset_path }}</el-text>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item label="算法脚本">
              <span v-if="task.algorithm_name">{{ task.algorithm_name }}</span>
              <el-text v-else-if="task.training_script" truncated style="max-width: 200px">{{ task.training_script }}</el-text>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item label="预训练模型">
              <span v-if="task.base_model_path">{{ task.base_model_path }}</span>
              <span v-else>无</span>
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatTime(task.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="训练耗时">{{ formatDuration(task.duration || runningTime) }}</el-descriptions-item>
            <el-descriptions-item label="节点/GPU">
              {{ task.num_nodes || 1 }} 节点 | {{ task.gpus_per_node || 0 }} GPU/节点
            </el-descriptions-item>
            <el-descriptions-item label="描述" :span="3" v-if="task.description">
              {{ task.description }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- 训练参数 -->
        <el-card style="margin-bottom: 16px;">
          <template #header><span class="card-title">训练参数</span></template>
          <pre class="config-content">{{ fullTrainingConfig }}</pre>
        </el-card>

        <!-- 训练进度 -->
        <el-card style="margin-bottom: 16px;" v-if="['pending','running','completed','failed','starting','queued','assigned'].includes(task.status)">
          <template #header>
            <div class="card-header-flex">
              <span class="card-title">训练进度</span>
              <span class="progress-text">Epoch {{ task.current_epoch || 0 }} / {{ task.total_epochs || '?' }}</span>
            </div>
          </template>
          <el-progress :percentage="progressPercent" :stroke-width="16"
            :format="() => `${progressPercent.toFixed(1)}%`"
            :status="task.status === 'completed' ? 'success' : task.status === 'failed' ? 'exception' : ''" />
          <div v-if="task.parallel_mode && task.parallel_mode !== 'single'" style="margin-top: 12px; padding-top: 10px; border-top: 1px solid #ebeef5; display: flex; align-items: center;">
            <el-tag size="small" type="primary" style="margin-right: 8px">{{ task.parallel_mode.toUpperCase() }}</el-tag>
            <span style="font-size: 13px; color: #606266;">节点: {{ task.num_nodes || 1 }} | GPU/节点: {{ task.gpus_per_node || 0 }}</span>
          </div>
        </el-card>

        <!-- 流水线阶段 (Pipeline Only) -->
        <el-card style="margin-bottom: 16px;" v-if="task.is_pipeline && pipelineStages.length > 0">
          <template #header>
            <div class="card-header-flex">
              <span class="card-title">流水线阶段</span>
              <span class="progress-text" v-if="task.pipeline_progress">
                阶段 {{ (task.pipeline_progress.current_stage ?? -1) + 1 }} / {{ pipelineStages.length }}
              </span>
            </div>
          </template>
          <el-steps :active="currentPipelineStageIdx" finish-status="success" align-center style="margin-bottom: 16px;">
            <el-step v-for="(st, idx) in pipelineStages" :key="st.id"
              :title="st.name || `阶段${idx+1}`"
              :status="stageStepStatus(st, idx)"
              @click="selectStage(idx)" style="cursor: pointer;">
              <template #description>
                <div style="font-size: 12px;">
                  <span>{{ statusLabel(st.status) }}</span>
                  <span v-if="st.current_epoch"> · Epoch {{ st.current_epoch }}/{{ st.total_epochs || '?' }}</span>
                </div>
              </template>
            </el-step>
          </el-steps>
          <!-- Selected stage detail -->
          <div v-if="selectedStage" class="stage-detail-panel">
            <div class="stage-detail-header">
              <el-tag :type="statusType(selectedStage.status)" size="small">{{ statusLabel(selectedStage.status) }}</el-tag>
              <span style="font-weight: 600; margin-left: 8px;">{{ selectedStage.name }}</span>
              <span v-if="selectedStage.current_epoch" style="margin-left: 12px; color: #606266; font-size: 13px;">
                Epoch {{ selectedStage.current_epoch }}/{{ selectedStage.total_epochs || '?' }}
                ({{ selectedStage.progress_percent ? selectedStage.progress_percent.toFixed(1) : 0 }}%)
              </span>
              <el-button v-if="selectedStage.id" size="small" text type="primary" style="margin-left: auto;"
                @click="$router.push(`/tasks/${selectedStage.id}`)">
                查看完整详情 →
              </el-button>
            </div>
            <el-progress v-if="selectedStage.total_epochs"
              :percentage="Math.min(((selectedStage.current_epoch||0) / selectedStage.total_epochs) * 100, 100)"
              :stroke-width="10" style="margin-top: 8px;"
              :status="selectedStage.status === 'completed' ? 'success' : selectedStage.status === 'failed' ? 'exception' : ''" />
            <div v-if="selectedStage.status === 'completed' && selectedStage.final_loss != null" style="margin-top: 8px; font-size: 13px; color: #606266;">
              Loss: <strong>{{ selectedStage.final_loss?.toFixed(6) }}</strong>
              <span v-if="selectedStage.final_accuracy != null" style="margin-left: 16px;">
                Accuracy: <strong>{{ (selectedStage.final_accuracy * 100).toFixed(2) }}%</strong>
              </span>
              <span v-if="selectedStage.model_path" style="margin-left: 16px;">
                模型: <el-text type="primary" truncated style="max-width: 200px">{{ selectedStage.model_path }}</el-text>
              </span>
            </div>
            <el-alert v-if="selectedStage.status === 'failed' && selectedStage.error_message"
              :title="selectedStage.error_message" type="error" show-icon :closable="false" style="margin-top: 8px;" />
          </div>
        </el-card>

        <!-- 训练结果摘要 -->
        <el-card style="margin-bottom: 16px;" v-if="['completed','failed'].includes(task.status)">
          <template #header>
            <div class="card-header-flex">
              <span class="card-title">训练结果</span>
              <el-tag :type="task.status === 'completed' ? 'success' : 'danger'" size="small">
                {{ task.status === 'completed' ? '成功' : '失败' }}
              </el-tag>
            </div>
          </template>
          <el-descriptions v-if="task.status === 'completed'" :column="3" border size="small">
            <el-descriptions-item label="最终模型">
              <el-text v-if="task.model_path" type="primary" truncated style="max-width: 280px">{{ task.model_path }}</el-text>
              <span v-else style="color:#909399">未生成模型</span>
            </el-descriptions-item>
            <el-descriptions-item label="最终Loss">
              <el-text type="warning">{{ task.final_loss != null ? task.final_loss.toFixed(6) : '-' }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="最终Accuracy">
              <el-text type="success">{{ task.final_accuracy != null ? (task.final_accuracy * 100).toFixed(2) + '%' : '-' }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="输出目录">
              <el-text v-if="task.output_path" truncated style="max-width: 280px">{{ task.output_path }}</el-text>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item label="总Epochs">
              {{ task.total_epochs || task.current_epoch || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="训练耗时">
              {{ formatDuration(task.duration) }}
            </el-descriptions-item>
          </el-descriptions>
          <el-alert v-if="task.status === 'failed'"
            :title="task.error_message || '训练失败'" type="error" show-icon :closable="false" />
        </el-card>

        <!-- 训练产出（结果文件） -->
        <el-card style="margin-bottom: 16px;">
          <template #header>
            <div class="card-header-flex">
              <span class="card-title">训练产出</span>
            </div>
          </template>
          <!-- 训练进行中提示 -->
          <div v-if="!isTerminal && resultFiles.length === 0" class="results-running-hint">
            <el-icon size="40" style="margin-bottom: 12px; color: #409EFF;"><loading /></el-icon>
            <p>训练进行中，完成后可查看结果文件</p>
          </div>
          <div v-else>
            <!-- 工具栏 -->
            <div class="results-toolbar">
              <el-button size="small" @click="loadResultFiles" :loading="resultsLoading">
                <el-icon><refresh /></el-icon>刷新文件列表
              </el-button>
              <el-button size="small" type="success" @click="downloadAllResults" :loading="downloadingAll">
                <el-icon><download /></el-icon>一键打包下载
              </el-button>
              <el-button size="small" type="primary" @click="downloadLogs" :loading="downloadingLogs">
                <el-icon><download /></el-icon>导出日志
              </el-button>
              <el-button size="small" type="info" @click="downloadMetricsCSV" :loading="downloadingMetrics" :disabled="!hasMetrics">
                <el-icon><download /></el-icon>导出指标CSV
              </el-button>
              <el-checkbox v-model="modelOnly" @change="loadResultFiles" size="small" style="margin-left: 12px;">仅显示模型文件</el-checkbox>
            </div>
            <!-- 文件表格 -->
            <el-table :data="resultFiles" stripe style="width: 100%; margin-top: 10px;" v-loading="resultsLoading" size="small">
              <el-table-column label="类型" width="90">
                <template #default="{ row }">
                  <el-tag :type="fileTypeTag(row.type)" size="small">{{ fileTypeLabel(row.type) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="name" label="文件名" min-width="220">
                <template #default="{ row }">
                  <span :style="{ fontWeight: row.type === 'model' ? 'bold' : 'normal' }">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column label="大小" width="110" prop="size_human" />
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button type="primary" size="small" link @click="downloadSingleFile(row.name)">下载</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!resultsLoading && resultFiles.length === 0" description="暂无训练结果文件" :image-size="60" />
          </div>
        </el-card>

        <!-- 训练曲线 -->
        <el-row :gutter="16" style="margin-bottom: 16px;">
          <el-col :span="12">
            <el-card>
              <template #header><span class="card-title">Loss 曲线</span></template>
              <div ref="lossChartRef" style="height: 280px"></div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card>
              <template #header><span class="card-title">Accuracy 曲线</span></template>
              <div ref="accChartRef" style="height: 280px"></div>
            </el-card>
          </el-col>
        </el-row>
      </el-col>

      <!-- 右侧：日志 -->
      <el-col :span="8">
        <el-card class="log-card">
          <template #header>
            <div class="card-header-flex">
              <span class="card-title">训练日志</span>
              <div style="display: flex; align-items: center; gap: 8px;">
                <el-button size="small" text @click="loadLogs"><el-icon><refresh /></el-icon></el-button>
                <el-button size="small" text @click="exportLogs" :loading="exportingLogs">
                  <el-icon><download /></el-icon>
                </el-button>
                <el-tag :type="autoRefresh ? 'success' : 'info'" size="small">
                  {{ autoRefresh ? '实时' : '静态' }}
                </el-tag>
              </div>
            </div>
          </template>
          <div class="log-container" ref="logContainer">
            <div v-if="logs.length === 0" class="log-empty">暂无日志</div>
            <div v-for="log in logs" :key="log.id" :class="['log-item', `log-${(log.level || 'info').toLowerCase()}`]">
              <span class="log-time">{{ formatLogTime(log.timestamp) }}</span>
              <span class="log-level">[{{ (log.level || 'INFO').toUpperCase() }}]</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Refresh, VideoPlay, RefreshRight, Close, Download, Loading } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { io } from 'socket.io-client'
import { tasksApi } from '@/api'

const route = useRoute()
const taskId = route.params.id
const task = ref({})
const logs = ref([])
const autoScroll = ref(true)
const autoRefresh = ref(true)
const wsConnected = ref(false)
const refreshing = ref(false)
const initialLoading = ref(true)
const logContainer = ref()
const lossChartRef = ref()
const accChartRef = ref()
const exportingLogs = ref(false)
const runningTime = ref(0)
const resultFiles = ref([])
const resultsLoading = ref(false)
const modelOnly = ref(false)
const downloadingLogs = ref(false)
const downloadingMetrics = ref(false)
const downloadingAll = ref(false)
const metricsDataCache = ref([])
const pipelineStages = ref([])      // Child stage task objects
const selectedStageIdx = ref(0)     // Currently selected stage in UI
let socket = null
let lossChart = null
let accChart = null
let autoRefreshTimer = null
let runningTimer = null
let lastWsEpoch = 0          // Track latest epoch from WebSocket to prevent polling regression
let lastWsTotalEpochs = null // Track latest total_epochs from WebSocket

const STATUS_LABEL = { pending: '等待中', queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消', starting: '启动中', assigned: '已分配' }
const STATUS_TYPE = { running: 'primary', failed: 'danger', completed: 'success', pending: 'info', queued: 'warning', cancelled: 'info', starting: 'primary', assigned: 'warning' }
function statusLabel(s) { return STATUS_LABEL[s] || s }
function statusType(s) { return STATUS_TYPE[s] || 'info' }
function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-' }
function formatLogTime(t) { return t ? dayjs(t).format('HH:mm:ss') : '' }

const isTerminal = computed(() => ['completed', 'failed', 'cancelled'].includes(task.value.status))
const hasMetrics = computed(() => metricsDataCache.value.length > 0)
const currentPipelineStageIdx = computed(() => {
  if (!task.value.pipeline_progress) return 0
  const cur = task.value.pipeline_progress.current_stage ?? -1
  return Math.max(cur, 0)
})
const selectedStage = computed(() => pipelineStages.value[selectedStageIdx.value] || null)

function stageStepStatus(stage, idx) {
  if (stage.status === 'completed') return 'success'
  if (stage.status === 'failed') return 'error'
  if (['running', 'starting', 'assigned'].includes(stage.status)) return 'process'
  if (stage.status === 'queued') return 'process'
  return 'wait'
}
function selectStage(idx) { selectedStageIdx.value = idx }

function formatDuration(seconds) {
  if (!seconds) return '0s'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return h > 0 ? `${h}h ${m}m ${s}s` : m > 0 ? `${m}m ${s}s` : `${s}s`
}

function formatConfig(args) {
  if (!args || Object.keys(args).length === 0) return '{}'
  return JSON.stringify(args, null, 2)
}

const fullTrainingConfig = computed(() => {
  const t = task.value
  if (!t || !t.id) return '{}'
  const config = {}
  // 用户指定的训练参数
  if (t.training_args && Object.keys(t.training_args).length > 0) {
    Object.assign(config, t.training_args)
  }
  // 补充核心训练配置
  if (t.total_epochs) config['total_epochs'] = t.total_epochs
  if (t.parallel_mode) config['parallel_mode'] = t.parallel_mode
  if (t.num_nodes && t.num_nodes > 1) config['num_nodes'] = t.num_nodes
  if (t.gpus_per_node != null) config['gpus_per_node'] = t.gpus_per_node
  if (t.nproc_per_node && t.nproc_per_node > 1) config['nproc_per_node'] = t.nproc_per_node
  if (t.execution_mode) config['execution_mode'] = t.execution_mode
  if (t.cpu_request) config['cpu_request'] = t.cpu_request
  if (t.memory_request) config['memory_request'] = t.memory_request
  if (t.gpu_limit) config['gpu_limit'] = t.gpu_limit
  if (t.dataset_path) config['dataset_path'] = t.dataset_path
  if (t.training_script) config['training_script'] = t.training_script
  if (t.pip_packages) config['pip_packages'] = t.pip_packages
  if (t.environment && Object.keys(t.environment).length > 0) config['environment'] = t.environment
  if (Object.keys(config).length === 0) return '{}'
  return JSON.stringify(config, null, 2)
})

const progressPercent = computed(() => {
  if (!task.value.total_epochs || task.value.total_epochs <= 0) return 0
  return Math.min(((task.value.current_epoch || 0) / task.value.total_epochs) * 100, 100)
})

async function loadPipelineStages() {
  if (!task.value.is_pipeline) return
  try {
    const res = await tasksApi.stages(taskId)
    pipelineStages.value = res.data.data || []
  } catch {}
}

async function loadTask() {
  try {
    const res = await tasksApi.get(taskId)
    const newData = res.data.data
    // Prevent polling from overwriting WS-pushed progress with stale DB values
    if (wsConnected.value && ['running', 'starting', 'assigned'].includes(newData.status)
        && lastWsEpoch > 0 && (newData.current_epoch || 0) < lastWsEpoch) {
      const preservedEpoch = lastWsEpoch
      const preservedTotal = lastWsTotalEpochs
      const preservedPercent = task.value.progress_percent
      task.value = newData
      task.value.current_epoch = preservedEpoch
      if (preservedTotal != null) task.value.total_epochs = preservedTotal
      if (preservedPercent != null) task.value.progress_percent = preservedPercent
    } else {
      task.value = newData
    }
    if (task.value.status === 'running' && task.value.started_at && !task.value.duration) {
      const elapsed = Math.floor((Date.now() - new Date(task.value.started_at).getTime()) / 1000)
      if (elapsed > 0) runningTime.value = elapsed
    }
    // Reset WS tracker when task reaches terminal state
    if (['completed', 'failed', 'cancelled'].includes(task.value.status)) {
      lastWsEpoch = 0
      lastWsTotalEpochs = null
    }
    // Load pipeline stages if this is a pipeline task
    if (task.value.is_pipeline) loadPipelineStages()
  } finally {
    initialLoading.value = false
  }
}

async function loadLogs() {
  try {
    const res = await tasksApi.logs(taskId, { per_page: 500 })
    logs.value = res.data.data.items || []
    scrollLogs()
  } catch {}
}

async function loadMetrics() {
  try {
    const res = await tasksApi.metricsSummary(taskId)
    const data = res.data.data || []
    metricsDataCache.value = data
    drawLossChart(data)
    drawAccChart(data)
  } catch {}
}

function drawLossChart(data) {
  nextTick(() => {
    if (!lossChartRef.value) return
    if (!lossChart) lossChart = echarts.init(lossChartRef.value)
    lossChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['训练Loss', '验证Loss'] },
      xAxis: { type: 'category', data: data.map(d => d.epoch), name: 'Epoch' },
      yAxis: { type: 'value', name: 'Loss' },
      series: [
        { name: '训练Loss', type: 'line', data: data.map(d => d.loss), smooth: true, itemStyle: { color: '#409EFF' } },
        { name: '验证Loss', type: 'line', data: data.map(d => d.val_loss), smooth: true, itemStyle: { color: '#E6A23C' }, lineStyle: { type: 'dashed' } },
      ]
    })
  })
}

function drawAccChart(data) {
  nextTick(() => {
    if (!accChartRef.value) return
    if (!accChart) accChart = echarts.init(accChartRef.value)
    accChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['训练准确率', '测试准确率'] },
      xAxis: { type: 'category', data: data.map(d => d.epoch), name: 'Epoch' },
      yAxis: { type: 'value', name: '准确率', max: 1 },
      series: [
        { name: '训练准确率', type: 'line', data: data.map(d => d.accuracy), smooth: true, itemStyle: { color: '#409EFF' } },
        { name: '测试准确率', type: 'line', data: data.map(d => d.val_accuracy), smooth: true, itemStyle: { color: '#67C23A' } },
      ]
    })
  })
}

async function exportLogs() {
  exportingLogs.value = true
  try {
    const res = await tasksApi.logs(taskId, { per_page: 10000 })
    const allLogs = res.data.data.items || []
    const content = allLogs.map(l => `[${l.timestamp}] [${(l.level||'info').toUpperCase()}] ${l.source}: ${l.message}`).join('\n')
    triggerDownload(new Blob([content], { type: 'text/plain' }), `task_${taskId}_logs_${dayjs().format('YYYYMMDD_HHmmss')}.txt`)
    ElMessage.success('日志导出成功')
  } catch { ElMessage.error('导出失败') }
  finally { exportingLogs.value = false }
}

function scrollLogs() {
  if (!autoScroll.value) return
  nextTick(() => {
    if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight
  })
}

// ======== 结果文件 & 下载 ========
async function loadResultFiles() {
  resultsLoading.value = true
  try {
    const res = await tasksApi.resultFiles(taskId, modelOnly.value ? { model_only: 'true' } : {})
    resultFiles.value = res.data.data?.files || []
  } catch { resultFiles.value = [] }
  finally { resultsLoading.value = false }
}

function fileTypeTag(type) {
  return { model: 'success', checkpoint: 'warning', metric: '', log: 'info', other: 'info' }[type] || 'info'
}
function fileTypeLabel(type) {
  return { model: '模型', checkpoint: '检查点', metric: '指标', log: '日志', other: '其他' }[type] || type
}

function triggerDownload(data, filename) {
  const blob = data instanceof Blob ? data : new Blob([data])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadSingleFile(filename) {
  try {
    const res = await tasksApi.downloadFile(taskId, filename)
    const fn = filename.split('/').pop() || filename
    triggerDownload(res.data, fn)
  } catch (e) {
    ElMessage.error('文件下载失败: ' + (e.message || '未知错误'))
  }
}

async function downloadAllResults() {
  downloadingAll.value = true
  try {
    const res = await tasksApi.downloadAll(taskId)
    triggerDownload(res.data, `task_${taskId.substring(0, 8)}_results.zip`)
  } catch (e) {
    ElMessage.error('打包下载失败: ' + (e.message || '未知错误'))
  } finally { downloadingAll.value = false }
}

async function downloadLogs() {
  downloadingLogs.value = true
  try {
    const res = await tasksApi.logs(taskId, { per_page: 10000 })
    const allLogs = res.data.data.items || []
    const content = allLogs.map(l => `[${l.timestamp}] [${(l.level||'info').toUpperCase()}] ${l.source}: ${l.message}`).join('\n')
    triggerDownload(new Blob([content], { type: 'text/plain' }), `task_${taskId.substring(0, 8)}_logs.txt`)
  } catch { ElMessage.error('日志下载失败') }
  finally { downloadingLogs.value = false }
}

async function downloadMetricsCSV() {
  downloadingMetrics.value = true
  try {
    const res = await tasksApi.metricsSummary(taskId)
    const data = res.data.data || []
    let csv = 'epoch,loss,val_loss,accuracy,val_accuracy\n'
    data.forEach(d => {
      csv += `${d.epoch ?? ''},${d.loss ?? ''},${d.val_loss ?? ''},${d.accuracy ?? ''},${d.val_accuracy ?? ''}\n`
    })
    triggerDownload(new Blob([csv], { type: 'text/csv' }), `task_${taskId.substring(0, 8)}_metrics.csv`)
  } catch { ElMessage.error('指标导出失败') }
  finally { downloadingMetrics.value = false }
}

function connectWs() {
  if (socket) return
  socket = io('/training', { transports: ['websocket', 'polling'] })
  socket.on('connect', () => {
    wsConnected.value = true
    socket.emit('subscribe', { task_id: taskId })
  })
  socket.on('disconnect', () => { wsConnected.value = false })
  socket.on('log', data => {
    if (data.task_id !== taskId) return
    logs.value.push(data)
    if (logs.value.length > 1000) logs.value.splice(0, 200)
    scrollLogs()
  })
  socket.on('status', data => {
    if (data.task_id !== taskId) return
    const oldStatus = task.value.status
    task.value.status = data.status
    if (['completed', 'failed'].includes(data.status) && oldStatus !== data.status) {
      loadTask()
      loadMetrics()
      loadResultFiles()
      autoRefresh.value = false
    }
    // Pipeline stage transition: refresh stages when parent status message indicates stage change
    if (task.value.is_pipeline && data.status === 'running') {
      loadPipelineStages()
    }
  })
  socket.on('metric', data => {
    if (data.task_id !== taskId) return
    loadMetrics()
  })
  socket.on('progress', data => {
    if (data.task_id !== taskId) return
    // Only accept monotonically increasing epoch to prevent jumps
    const newEpoch = data.current_epoch || 0
    if (newEpoch >= lastWsEpoch) {
      lastWsEpoch = newEpoch
      task.value.current_epoch = newEpoch
    }
    if (data.total_epochs != null) {
      lastWsTotalEpochs = data.total_epochs
      task.value.total_epochs = data.total_epochs
    }
    if (data.progress != null) task.value.progress_percent = data.progress
  })
}

// BUG-B fix: handleRefreshAll 在终态时也加载结果文件
async function handleRefreshAll() {
  refreshing.value = true
  try {
    await loadTask()
    await Promise.all([loadLogs(), loadMetrics()])
    if (isTerminal.value) await loadResultFiles()
    ElMessage.success('刷新成功')
  } finally { refreshing.value = false }
}

async function handleSubmit() {
  await tasksApi.submit(taskId); ElMessage.success('已提交'); loadTask()
}
async function handleCancel() {
  await tasksApi.cancel(taskId); ElMessage.success('已取消'); loadTask()
}
async function handleRetry() {
  await tasksApi.retry(taskId); ElMessage.success('已重新提交'); loadTask()
}

// BUG-C fix: 轮询检测状态变化，自动加载结果文件
function startAutoRefresh() {
  stopAutoRefresh()
  if (autoRefresh.value) {
    const interval = (task.value.status === 'running') ? 5000 : 15000
    autoRefreshTimer = setInterval(async () => {
      if (['running', 'starting', 'assigned', 'queued'].includes(task.value.status)) {
        const oldStatus = task.value.status
        await loadTask()
        loadLogs()
        loadMetrics()
        // BUG-C: 检测状态变为终态时自动加载结果文件
        if (['completed', 'failed'].includes(task.value.status) && oldStatus !== task.value.status) {
          loadResultFiles()
          autoRefresh.value = false
        }
      } else {
        autoRefresh.value = false
      }
    }, interval)
  }
}

function stopAutoRefresh() {
  if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null }
}

watch(autoRefresh, (val) => { val ? startAutoRefresh() : stopAutoRefresh() })

onMounted(async () => {
  await loadTask()
  loadLogs()
  loadMetrics()
  if (task.value.is_pipeline) loadPipelineStages()
  if (isTerminal.value) loadResultFiles()
  connectWs()
  startAutoRefresh()
  runningTimer = setInterval(() => {
    if (task.value.status === 'running') runningTime.value++
  }, 1000)
})

onUnmounted(() => {
  if (socket) { socket.disconnect(); socket = null }
  if (lossChart) { lossChart.dispose(); lossChart = null }
  if (accChart) { accChart.dispose(); accChart = null }
  stopAutoRefresh()
  if (runningTimer) clearInterval(runningTimer)
})
</script>

<style scoped>
.version-detail-page { padding: 20px; }

/* 页面标题栏 */
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #ebeef5;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; color: #303133; }
.experiment-label { font-size: 15px; color: #606266; padding: 2px 10px; background: #f4f4f5; border-radius: 4px; }
.header-actions { display: flex; align-items: center; gap: 8px; }

/* 卡片标题 */
.card-title { font-size: 15px; font-weight: 600; color: #303133; }
.card-header-flex { display: flex; justify-content: space-between; align-items: center; width: 100%; }

/* 训练参数代码块 */
.config-content {
  background: #1e1e1e; color: #d4d4d4; border-radius: 6px;
  padding: 14px 16px; font-size: 13px; line-height: 1.6;
  font-family: 'Cascadia Code', 'Consolas', 'Monaco', monospace;
  overflow: auto; max-height: 200px; white-space: pre-wrap; word-break: break-all;
  margin: 0;
}

/* 训练进度 */
.progress-text { font-size: 14px; color: #606266; font-weight: 500; }

/* 训练产出 */
.results-toolbar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding-bottom: 8px; border-bottom: 1px solid #f0f0f0;
}
.results-running-hint {
  display: flex; flex-direction: column; align-items: center;
  padding: 40px 0; color: #909399;
}
.results-running-hint p { margin: 0; font-size: 14px; }

/* 日志卡片 */
.log-card { position: sticky; top: 20px; }
.log-container {
  height: calc(100vh - 200px); min-height: 700px; overflow-y: auto;
  font-family: 'Cascadia Code', 'Consolas', 'Monaco', monospace;
  font-size: 12px; line-height: 1.7;
  background: #1e1e1e; padding: 12px; border-radius: 6px;
}
.log-empty { text-align: center; color: #666; padding: 60px 0; }
.log-item { padding: 1px 0; color: #d4d4d4; white-space: pre-wrap; word-break: break-all; }
.log-time { color: #808080; margin-right: 8px; }
.log-level { margin-right: 8px; color: #9cdcfe; }
.log-item.log-error { color: #f56c6c; }
.log-item.log-error .log-level { color: #f56c6c; }
.log-item.log-warning { color: #e6a23c; }
.log-item.log-warning .log-level { color: #e6a23c; }
.log-item.log-info .log-level { color: #409eff; }
.log-message { white-space: pre-wrap; }

/* Pipeline stages */
.stage-detail-panel {
  background: #f8f9fa; border-radius: 8px; padding: 14px 16px;
  border: 1px solid #ebeef5;
}
.stage-detail-header {
  display: flex; align-items: center; flex-wrap: wrap;
}
</style>
