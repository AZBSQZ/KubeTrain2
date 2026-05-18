<template>
  <div class="dashboard">
    <!-- 标题栏 + 刷新按钮 -->
    <div class="dashboard-header">
      <span></span>
      <el-button :loading="loading" @click="loadData"><el-icon><refresh /></el-icon> 刷新</el-button>
    </div>

    <!-- 顶部渐变统计卡片（对齐FTv1） -->
    <div class="stats-row">
      <div class="stat-col" v-for="stat in mainStats" :key="stat.title">
        <div class="stat-card" :style="{ background: stat.gradient }">
          <div class="stat-icon-bg">
            <el-icon :size="40"><component :is="stat.icon" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stat.value }}</div>
            <div class="stat-title">{{ stat.title }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 今日数据 + 状态分布饼图 + 系统资源 -->
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="8">
        <el-card class="section-card equal-height-card">
          <template #header>
            <div class="card-header"><span><el-icon><sunny /></el-icon> 今日数据</span></div>
          </template>
          <div class="today-stats">
            <div class="today-item">
              <div class="today-label">新增<br>任务</div>
              <div class="today-value">{{ dashData.todayStats?.tasks ?? 0 }}</div>
            </div>
            <div class="today-item">
              <div class="today-label">已完成<br>任务</div>
              <div class="today-value">{{ dashData.todayStats?.completed ?? 0 }}</div>
            </div>
            <div class="today-item">
              <div class="today-label">本周<br>任务</div>
              <div class="today-value">{{ dashData.weekStats?.tasks ?? 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="section-card equal-height-card">
          <template #header>
            <div class="card-header"><span><el-icon><pie-chart /></el-icon> 任务状态分布</span></div>
          </template>
          <div ref="pieChartRef" style="height: 220px"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="section-card equal-height-card">
          <template #header>
            <div class="card-header"><span><el-icon><monitor /></el-icon> 系统资源</span></div>
          </template>
          <div class="resource-list">
            <div class="resource-item" v-for="r in sysResources" :key="r.label">
              <div class="resource-label">{{ r.label }}</div>
              <el-progress :percentage="r.pct" :color="getResourceColor(r.pct)" />
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 训练任务趋势（柱状图）+ 快捷操作 -->
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="16">
        <el-card class="section-card">
          <template #header>
            <div class="card-header"><span><el-icon><trend-charts /></el-icon> 训练任务趋势</span></div>
          </template>
          <div ref="barChartRef" style="height: 300px"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="section-card" style="height:100%">
          <template #header>
            <div class="card-header"><span><el-icon><operation /></el-icon> 快捷操作</span></div>
          </template>
          <div class="quick-actions">
            <el-button type="primary" size="large" @click="$router.push('/tasks/create')">
              <el-icon><plus /></el-icon> 新建训练任务
            </el-button>
            <el-button size="large" @click="$router.push('/datasets')">
              <el-icon><upload /></el-icon> 上传数据集
            </el-button>
            <el-button size="large" @click="$router.push('/algorithms')">
              <el-icon><cpu /></el-icon> 管理算法
            </el-button>
            <el-button size="large" @click="$router.push('/models')">
              <el-icon><box /></el-icon> 浏览模型
            </el-button>
            <el-button size="large" @click="$router.push('/workers')">
              <el-icon><connection /></el-icon> 查看节点
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近任务列表 -->
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <el-card class="section-card">
          <template #header>
            <div class="card-header"><span><el-icon><clock /></el-icon> 最近训练任务</span></div>
          </template>
          <div class="task-list">
            <div v-for="t in (dashData.recentTasks || [])" :key="t.id" class="task-item" @click="$router.push(`/tasks/${t.id}`)">
              <div class="task-info">
                <div class="task-name">{{ t.name }}</div>
                <div class="task-meta">
                  <span class="task-creator" v-if="t.creator">{{ t.creator }}</span>
                  <span class="task-time">{{ formatTime(t.created_at) }}</span>
                </div>
              </div>
              <el-tag :type="statusType(t.status)" size="small">{{ statusLabel(t.status) }}</el-tag>
            </div>
            <el-empty v-if="!(dashData.recentTasks || []).length" description="暂无任务" :image-size="80" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { dashboardApi } from '@/api'

const loading = ref(false)
const pieChartRef = ref()
const barChartRef = ref()
const dashData = ref({})

const STATUS_LABEL = { pending: '等待中', queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
const STATUS_TYPE = { running: 'primary', failed: 'danger', completed: 'success', pending: 'info', queued: 'warning', cancelled: 'info' }
const statusLabel = s => STATUS_LABEL[s] || s
const statusType = s => STATUS_TYPE[s] || 'info'
function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-' }

const mainStats = computed(() => {
  const s = dashData.value.stats || {}
  return [
    { title: '训练任务', value: s.tasks ?? 0, icon: 'DataAnalysis', gradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' },
    { title: '数据集', value: s.datasets ?? 0, icon: 'Files', gradient: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' },
    { title: '算法', value: s.algorithms ?? 0, icon: 'Cpu', gradient: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)' },
    { title: '模型', value: s.models ?? 0, icon: 'Box', gradient: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)' },
    { title: '用户', value: s.users ?? 0, icon: 'User', gradient: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)' },
  ]
})

const sysResources = computed(() => {
  const r = dashData.value.systemResources || {}
  return [
    { label: 'CPU', pct: Math.round(r.cpu_percent || 0) },
    { label: '内存', pct: Math.round(r.memory_percent || 0) },
    { label: '磁盘', pct: Math.round(r.disk_percent || 0) },
    { label: 'GPU', pct: Math.round(r.gpu_percent || 0) },
  ]
})

function getResourceColor(pct) {
  if (pct < 60) return '#67c23a'
  if (pct < 80) return '#e6a23c'
  return '#f56c6c'
}

async function loadData() {
  loading.value = true
  try {
    const res = await dashboardApi.get()
    dashData.value = res.data.data || {}
    await nextTick()
    drawPieChart()
    drawBarChart()
  } catch (e) {
    console.error('Dashboard load error:', e)
  } finally {
    loading.value = false
  }
}

function drawPieChart() {
  if (!pieChartRef.value) return
  const chart = echarts.getInstanceByDom(pieChartRef.value) || echarts.init(pieChartRef.value)
  const dist = dashData.value.statusDistribution || {}
  const data = [
    { value: dist.completed || 0, name: '已完成', itemStyle: { color: '#67c23a' } },
    { value: dist.running || 0, name: '运行中', itemStyle: { color: '#409eff' } },
    { value: dist.failed || 0, name: '失败', itemStyle: { color: '#f56c6c' } },
    { value: dist.pending || 0, name: '待运行', itemStyle: { color: '#e6a23c' } },
    { value: dist.queued || 0, name: '排队中', itemStyle: { color: '#909399' } },
    { value: dist.cancelled || 0, name: '已取消', itemStyle: { color: '#c0c4cc' } },
  ]
  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie', radius: ['45%', '75%'], center: ['38%', '50%'],
      avoidLabelOverlap: false, label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: data
    }]
  })
}

function drawBarChart() {
  if (!barChartRef.value) return
  const chart = echarts.getInstanceByDom(barChartRef.value) || echarts.init(barChartRef.value)
  const stats = dashData.value.trainingStats || []
  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['总任务', '已完成', '失败'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: stats.map(s => s.date) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '总任务', type: 'bar', data: stats.map(s => s.total), itemStyle: { color: '#409eff' } },
      { name: '已完成', type: 'bar', data: stats.map(s => s.completed), itemStyle: { color: '#67c23a' } },
      { name: '失败', type: 'bar', data: stats.map(s => s.failed), itemStyle: { color: '#f56c6c' } },
    ]
  })
}

onMounted(loadData)
</script>

<style scoped>
.dashboard { padding: 20px; background: #f5f7fa; min-height: calc(100vh - 60px); }
.dashboard-header { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 12px; }

/* 渐变统计卡片 */
.stats-row { display: flex; gap: 20px; }
.stat-col { flex: 1; min-width: 0; }
.stat-card { padding: 24px; border-radius: 16px; color: white; position: relative; overflow: hidden; cursor: pointer; transition: all 0.3s; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.stat-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.stat-icon-bg { opacity: 0.3; position: absolute; right: 20px; top: 50%; transform: translateY(-50%); }
.stat-info { position: relative; z-index: 1; }
.stat-value { font-size: 36px; font-weight: bold; margin-bottom: 8px; text-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.stat-title { font-size: 14px; opacity: 0.9; }

/* 通用区块卡片 */
.section-card { border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: all 0.3s; }
.section-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
.card-header { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 16px; }
.equal-height-card { height: 100%; display: flex; flex-direction: column; }
.equal-height-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; }

/* 今日数据 */
.today-stats { display: flex; justify-content: space-around; padding: 16px 10px; flex: 1; align-items: center; }
.today-item { text-align: center; padding: 16px 12px; border-radius: 12px; flex: 1; margin: 0 6px; background: rgba(64,158,255,0.04); transition: all 0.3s; }
.today-item:hover { background: rgba(64,158,255,0.1); transform: translateY(-4px); box-shadow: 0 4px 12px rgba(64,158,255,0.15); }
.today-label { font-size: 14px; color: #606266; margin-bottom: 10px; font-weight: 600; line-height: 1.4; }
.today-value { font-size: 32px; font-weight: bold; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }

/* 系统资源进度条 */
.resource-list { padding: 12px 0; flex: 1; display: flex; flex-direction: column; justify-content: center; }
.resource-item { margin-bottom: 20px; }
.resource-item:last-child { margin-bottom: 0; }
.resource-label { font-size: 14px; color: #606266; margin-bottom: 8px; font-weight: 500; }

/* 快捷操作 */
.quick-actions { display: flex; flex-direction: column; gap: 12px; }
.quick-actions .el-button { justify-content: flex-start; width: 100%; }

/* 最近任务列表 */
.task-list { max-height: 320px; overflow-y: auto; }
.task-item { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px; border-bottom: 1px solid #f0f0f0; cursor: pointer; transition: background 0.2s; }
.task-item:last-child { border-bottom: none; }
.task-item:hover { background: #fafafa; }
.task-info { flex: 1; }
.task-name { font-size: 15px; font-weight: 500; color: #303133; margin-bottom: 4px; }
.task-meta { font-size: 13px; color: #909399; }
.task-creator { margin-right: 16px; }
.task-creator::before { content: '👤 '; }
.task-time::before { content: '🕐 '; }

:deep(.el-card__header) { border-bottom: 1px solid #f0f0f0; background: #fafafa; }
:deep(.el-progress__text) { font-size: 14px !important; font-weight: 500; }
</style>
