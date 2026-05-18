<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-info">
        <h1>告警管理</h1>
        <p>监控系统告警与规则配置</p>
      </div>
      <el-radio-group v-model="activeTab" size="small">
        <el-radio-button label="alerts">告警列表</el-radio-button>
        <el-radio-button label="rules">告警规则</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 告警列表 -->
    <template v-if="activeTab === 'alerts'">
      <el-card shadow="never" class="filter-card">
        <el-row :gutter="12">
          <el-col :span="4">
            <el-select v-model="filters.status" placeholder="状态" clearable @change="loadAlerts">
              <el-option label="活跃" value="active" /><el-option label="已确认" value="acknowledged" />
              <el-option label="已解决" value="resolved" />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-select v-model="filters.level" placeholder="级别" clearable @change="loadAlerts">
              <el-option label="Critical" value="critical" />
              <el-option label="Warning" value="warning" />
              <el-option label="Info" value="info" />
            </el-select>
          </el-col>
        </el-row>
      </el-card>

      <el-card shadow="never">
        <el-table v-loading="loading" :data="alerts" stripe>
          <el-table-column label="级别" width="90">
            <template #default="{ row }">
              <el-tag :type="levelType(row.level)" size="small">{{ row.level }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="类型" prop="alert_type" width="120" />
          <el-table-column label="消息" prop="message" min-width="240" show-overflow-tooltip />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="触发时间" width="150">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button v-if="row.status === 'active'" link size="small" @click="acknowledge(row)">确认</el-button>
              <el-button v-if="row.status !== 'resolved'" link size="small" type="success" @click="resolve(row)">解决</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
          layout="total, prev, pager, next" @change="loadAlerts" class="pagination" />
      </el-card>
    </template>

    <!-- 告警规则 -->
    <template v-if="activeTab === 'rules'">
      <el-card shadow="never">
        <template #header>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>告警规则</span>
            <el-button size="small" type="primary" @click="showAddRule = true">+ 新增规则</el-button>
          </div>
        </template>
        <el-table v-loading="rulesLoading" :data="rules" stripe>
          <el-table-column label="规则名称" prop="name" min-width="160" />
          <el-table-column label="类型" prop="alert_type" width="120" />
          <el-table-column label="级别" width="90">
            <template #default="{ row }">
              <el-tag :type="levelType(row.level)" size="small">{{ row.level }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">{{ row.is_enabled ? '启用' : '禁用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="描述" prop="description" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link size="small" @click="toggleRule(row)">{{ row.is_enabled ? '禁用' : '启用' }}</el-button>
              <el-button link size="small" type="danger" @click="deleteRule(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- 解决告警 -->
    <el-dialog v-model="showResolve" title="解决告警" width="420px">
      <el-form :model="resolveForm" label-width="80px">
        <el-form-item label="解决说明"><el-input v-model="resolveForm.note" type="textarea" rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showResolve = false">取消</el-button>
        <el-button type="primary" @click="confirmResolve">确认解决</el-button>
      </template>
    </el-dialog>

    <!-- 新增规则 -->
    <el-dialog v-model="showAddRule" title="新增告警规则" width="540px">
      <el-form :model="ruleForm" label-width="100px">
        <el-form-item label="规则名称"><el-input v-model="ruleForm.name" /></el-form-item>
        <el-form-item label="告警类型"><el-input v-model="ruleForm.alert_type" placeholder="如 task_failed" /></el-form-item>
        <el-form-item label="级别">
          <el-select v-model="ruleForm.level" style="width:100%">
            <el-option label="Critical" value="critical" />
            <el-option label="Warning" value="warning" />
            <el-option label="Info" value="info" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="ruleForm.description" type="textarea" rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddRule = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleAddRule">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { alertsApi } from '@/api'

const activeTab = ref('alerts')
const loading = ref(false)
const rulesLoading = ref(false)
const alerts = ref([])
const rules = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ status: 'active', level: '' })
const showResolve = ref(false)
const showAddRule = ref(false)
const resolveForm = reactive({ note: '' })
const ruleForm = reactive({ name: '', alert_type: '', level: 'warning', description: '' })
const resolveTarget = ref(null)
const saving = ref(false)

function levelType(l) { return { critical: 'danger', warning: 'warning', info: 'info' }[l] || 'info' }
function statusType(s) { return { active: 'danger', acknowledged: 'warning', resolved: 'success' }[s] || 'info' }
function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-' }

async function loadAlerts() {
  loading.value = true
  try {
    const res = await alertsApi.list({ page: page.value, per_page: pageSize.value, status: filters.status || undefined, level: filters.level || undefined })
    alerts.value = res.data.data.items || []
    total.value = res.data.data.total || 0
  } finally { loading.value = false }
}

async function loadRules() {
  rulesLoading.value = true
  try {
    const res = await alertsApi.rules()
    rules.value = res.data.data || []
  } finally { rulesLoading.value = false }
}

async function acknowledge(row) {
  await alertsApi.acknowledge(row.id)
  ElMessage.success('已确认')
  loadAlerts()
}

function resolve(row) { resolveTarget.value = row; resolveForm.note = ''; showResolve.value = true }
async function confirmResolve() {
  await alertsApi.resolve(resolveTarget.value.id, { note: resolveForm.note })
  ElMessage.success('告警已解决')
  showResolve.value = false
  loadAlerts()
}

async function toggleRule(row) {
  await alertsApi.updateRule(row.id, { is_enabled: !row.is_enabled })
  ElMessage.success('已更新')
  loadRules()
}
async function deleteRule(row) {
  await ElMessageBox.confirm(`确认删除规则 "${row.name}"？`, '确认', { type: 'warning' })
  await alertsApi.deleteRule(row.id)
  ElMessage.success('删除成功')
  loadRules()
}
async function handleAddRule() {
  saving.value = true
  try {
    await alertsApi.createRule(ruleForm)
    ElMessage.success('规则创建成功')
    showAddRule.value = false
    loadRules()
  } finally { saving.value = false }
}

watch(activeTab, tab => { if (tab === 'rules') loadRules() })
onMounted(loadAlerts)
</script>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
.filter-card { border-radius: 10px; }
.filter-card :deep(.el-card__body) { padding: 12px 16px; }
.pagination { margin-top: 16px; justify-content: flex-end; display: flex; }
</style>
