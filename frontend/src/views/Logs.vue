<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-info">
        <h1>操作日志</h1>
        <p>查看系统操作审计记录</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="exportLogs" :loading="exporting">
          <el-icon><download /></el-icon> 导出报告
        </el-button>
        <el-button v-if="isAdmin" type="danger" @click="showBatchDelete = true">
          <el-icon><delete /></el-icon> 批量删除
        </el-button>
      </div>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-row :gutter="12">
        <el-col :span="4">
          <el-select v-model="filters.module" placeholder="模块" clearable @change="loadLogs">
            <el-option label="认证" value="auth" />
            <el-option label="用户" value="users" />
            <el-option label="数据集" value="datasets" />
            <el-option label="算法" value="algorithms" />
            <el-option label="模型" value="models" />
            <el-option label="任务" value="tasks" />
            <el-option label="节点" value="workers" />
            <el-option label="告警" value="alerts" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.operation_type" placeholder="操作类型" clearable @change="loadLogs">
            <el-option label="创建" value="create" />
            <el-option label="更新" value="update" />
            <el-option label="删除" value="delete" />
            <el-option label="登录" value="login" />
            <el-option label="退出" value="logout" />
            <el-option label="注册" value="register" />
            <el-option label="提交" value="submit" />
            <el-option label="取消" value="cancel" />
            <el-option label="上传" value="upload" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.result" placeholder="结果" clearable @change="loadLogs">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failure" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-input v-model="filters.username" placeholder="用户名" clearable @keyup.enter="loadLogs" />
        </el-col>
        <el-col :span="6">
          <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
            start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD"
            @change="onDateChange" style="width:100%" />
        </el-col>
        <el-col :span="2">
          <el-button type="primary" @click="loadLogs">查询</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="logs" stripe size="small">
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ row.created_at }}</template>
        </el-table-column>
        <el-table-column label="用户" prop="username" width="100" />
        <el-table-column label="模块" width="90">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ moduleLabel(row.module) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="operationType(row.operation_type)">{{ row.operation_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="描述" prop="action" min-width="200" show-overflow-tooltip />
        <el-table-column label="目标" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.target_name">{{ row.target_name }}</span>
            <span v-else-if="row.target_id" class="text-muted">ID: {{ row.target_id }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.result === 'success' ? 'success' : 'danger'">
              {{ row.result === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="IP" prop="ip_address" width="120" />
      </el-table>
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
        :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next" @change="loadLogs" class="pagination" />
    </el-card>

    <!-- 批量删除对话框 -->
    <el-dialog v-model="showBatchDelete" title="批量删除日志" width="420px">
      <el-form :model="deleteForm" label-width="80px">
        <el-form-item label="时间范围">
          <el-date-picker v-model="deleteForm.range" type="daterange" range-separator="至"
            start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-alert type="warning" :closable="false" style="margin-top:8px">
          此操作将永久删除所选时间范围内的所有日志，不可恢复！
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="showBatchDelete = false">取消</el-button>
        <el-button type="danger" :loading="deleting" @click="confirmBatchDelete">确认删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { operationLogsApi } from '@/api'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const loading = ref(false)
const exporting = ref(false)
const deleting = ref(false)
const logs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const dateRange = ref([])
const showBatchDelete = ref(false)
const filters = reactive({ module: '', operation_type: '', result: '', username: '', start_date: '', end_date: '' })
const deleteForm = reactive({ range: [] })

const moduleLabels = {
  auth: '认证', users: '用户', datasets: '数据集', algorithms: '算法',
  models: '模型', tasks: '任务', workers: '节点', alerts: '告警',
  clusters: '集群', node_pools: '节点池'
}
function moduleLabel(m) { return moduleLabels[m] || m }

function operationType(t) {
  const map = { create: 'success', delete: 'danger', update: 'warning', login: 'primary', logout: 'info', submit: 'success', cancel: 'warning', upload: 'primary' }
  return map[t] || 'info'
}

function onDateChange(val) {
  if (val && val.length === 2) {
    filters.start_date = val[0]
    filters.end_date = val[1]
  } else {
    filters.start_date = ''
    filters.end_date = ''
  }
  loadLogs()
}

async function loadLogs() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value }
    if (filters.module) params.module = filters.module
    if (filters.operation_type) params.operation_type = filters.operation_type
    if (filters.result) params.result = filters.result
    if (filters.username) params.username = filters.username
    if (filters.start_date) params.start_date = filters.start_date
    if (filters.end_date) params.end_date = filters.end_date
    const res = await operationLogsApi.list(params)
    logs.value = res.data.data.items || []
    total.value = res.data.data.total || 0
  } finally { loading.value = false }
}

async function exportLogs() {
  exporting.value = true
  try {
    const params = {}
    if (filters.module) params.module = filters.module
    if (filters.start_date) params.start_date = filters.start_date
    if (filters.end_date) params.end_date = filters.end_date
    const res = await operationLogsApi.export(params)
    const report = res.data.data
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `operation_logs_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch { ElMessage.error('导出失败') }
  finally { exporting.value = false }
}

async function confirmBatchDelete() {
  if (!deleteForm.range || deleteForm.range.length !== 2) {
    ElMessage.warning('请选择时间范围')
    return
  }
  await ElMessageBox.confirm('确认删除所选时间范围内的所有日志？此操作不可恢复！', '危险操作', { type: 'error' })
  deleting.value = true
  try {
    await operationLogsApi.batchDelete({ start_date: deleteForm.range[0], end_date: deleteForm.range[1] })
    ElMessage.success('删除成功')
    showBatchDelete.value = false
    loadLogs()
  } finally { deleting.value = false }
}

onMounted(loadLogs)
</script>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
.header-actions { display: flex; gap: 8px; }
.filter-card { border-radius: 10px; }
.filter-card :deep(.el-card__body) { padding: 12px 16px; }
.pagination { margin-top: 16px; justify-content: flex-end; display: flex; }
.text-muted { color: #999; }
</style>
