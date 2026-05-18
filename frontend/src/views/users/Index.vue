<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-info">
        <h1>用户管理</h1>
        <p>管理系统用户、角色与资源配额</p>
      </div>
    </div>

    <!-- 顶部统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-inner">
            <div class="stat-icon" style="background:#e6f4ff"><el-icon size="24" color="#1890ff"><user /></el-icon></div>
            <div class="stat-info"><div class="stat-num">{{ stats.total }}</div><div class="stat-label">总用户</div></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-inner">
            <div class="stat-icon" style="background:#fff0f6"><el-icon size="24" color="#eb2f96"><user-filled /></el-icon></div>
            <div class="stat-info"><div class="stat-num">{{ stats.admins }}</div><div class="stat-label">管理员</div></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-inner">
            <div class="stat-icon" style="background:#f6ffed"><el-icon size="24" color="#52c41a"><circle-check /></el-icon></div>
            <div class="stat-info"><div class="stat-num">{{ stats.active }}</div><div class="stat-label">启用中</div></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-inner">
            <div class="stat-icon" style="background:#fff7e6"><el-icon size="24" color="#fa8c16"><warning /></el-icon></div>
            <div class="stat-info"><div class="stat-num">{{ stats.disabled }}</div><div class="stat-label">已禁用</div></div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">用户列表</span>
          <div class="header-actions">
            <el-input v-model="search" placeholder="搜索用户名 / 邮箱" clearable style="width:220px"
              prefix-icon="Search" @keyup.enter="loadList" />
            <el-select v-model="filterRole" placeholder="角色筛选" clearable style="width:120px" @change="loadList">
              <el-option label="管理员" value="admin" />
              <el-option label="普通用户" value="user" />
              <el-option label="访客" value="guest" />
            </el-select>
            <el-select v-model="filterStatus" placeholder="状态筛选" clearable style="width:110px" @change="loadList">
              <el-option label="启用" :value="1" />
              <el-option label="禁用" :value="0" />
            </el-select>
            <el-button @click="loadList"><el-icon><refresh /></el-icon></el-button>
            <el-button type="primary" @click="openCreate">
              <el-icon><plus /></el-icon> 新建用户
            </el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="users" stripe border>
        <el-table-column label="用户名" min-width="120">
          <template #default="{ row }">
            <div class="user-cell">
              <el-avatar size="small" :style="{ background: avatarColor(row.username) }">
                {{ row.username.charAt(0).toUpperCase() }}
              </el-avatar>
              <span>{{ row.username }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="邮箱" prop="email" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)" size="small" effect="light">
              {{ roleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" size="small" :loading="row._toggling"
              @change="toggleActive(row)" />
          </template>
        </el-table-column>
        <el-table-column label="配额" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="row.quota_name" type="info" size="small">{{ row.quota_name }}</el-tag>
            <span v-else class="text-muted">未分配</span>
          </template>
        </el-table-column>
        <el-table-column label="最后登录" width="150">
          <template #default="{ row }">
            <span class="text-muted">{{ formatTime(row.last_login) || '从未登录' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="140">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="openEdit(row)">
              <el-icon><edit /></el-icon> 编辑
            </el-button>
            <el-button link size="small" @click="openResetPwd(row)">重置密码</el-button>
            <el-button link size="small" @click="openSetQuota(row)">配额</el-button>
            <el-button link size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
        :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next"
        @size-change="loadList" @current-change="loadList" class="pagination" />
    </el-card>

    <!-- 创建/编辑用户对话框 -->
    <el-dialog v-model="showCreate" :title="editMode ? '编辑用户' : '新建用户'" width="500px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="editMode" placeholder="3-50 个字符" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="可选" />
        </el-form-item>
        <el-form-item label="密码" :prop="editMode ? '' : 'password'">
          <el-input v-model="form.password" type="password" show-password
            :placeholder="editMode ? '留空则不修改' : '至少 6 位'" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="form.role">
            <el-radio-button value="admin">
              <el-icon><user-filled /></el-icon> 管理员
            </el-radio-button>
            <el-radio-button value="user">
              <el-icon><user /></el-icon> 普通用户
            </el-radio-button>
            <el-radio-button value="guest">
              <el-icon><view /></el-icon> 访客
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="editMode" label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
        <el-form-item label="权限说明">
          <div class="perm-tip">
            <div v-if="form.role === 'admin'" class="perm-item admin">
              <el-icon><circle-check /></el-icon> 完整系统权限，可管理用户、资源、任务
            </div>
            <div v-else-if="form.role === 'user'" class="perm-item user">
              <el-icon><circle-check /></el-icon> 可创建任务、上传数据集、管理自己的模型
            </div>
            <div v-else class="perm-item guest">
              <el-icon><view /></el-icon> 只读访问，可查看任务和资源，不可创建
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          {{ editMode ? '保存修改' : '创建用户' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="showResetPwd" :title="`重置密码 — ${pwdUser?.username}`" width="420px" destroy-on-close>
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="100px">
        <el-form-item label="新密码" prop="password">
          <el-input v-model="pwdForm.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="pwdForm.confirm" type="password" show-password placeholder="再次输入新密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showResetPwd = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleResetPwd">确认重置</el-button>
      </template>
    </el-dialog>

    <!-- 设置配额对话框 -->
    <el-dialog v-model="showQuota" :title="`资源配额 — ${quotaUser?.username}`" width="440px" destroy-on-close>
      <el-form :model="quotaForm" label-width="100px">
        <el-form-item label="资源配额">
          <el-select v-model="quotaForm.quota_id" placeholder="选择配额方案" clearable style="width:100%">
            <el-option v-for="q in quotaOptions" :key="q.id" :label="q.name" :value="q.id">
              <span>{{ q.name }}</span>
              <span class="quota-desc">{{ q.description || '' }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-alert v-if="!quotaOptions.length" type="info" title="暂无可用配额方案，请先在资源管理中创建" :closable="false" style="margin-top:8px" />
      </el-form>
      <template #footer>
        <el-button @click="showQuota = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSetQuota">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { usersApi, resourcesApi } from '@/api'

const loading = ref(false)
const saving = ref(false)
const users = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')
const filterRole = ref('')
const filterStatus = ref(null)
const showCreate = ref(false)
const showResetPwd = ref(false)
const showQuota = ref(false)
const editMode = ref(false)
const editId = ref(null)
const formRef = ref()
const pwdFormRef = ref()
const pwdUser = ref(null)
const quotaUser = ref(null)
const quotaOptions = ref([])

const form = reactive({ username: '', email: '', password: '', role: 'user', is_active: true })
const pwdForm = reactive({ password: '', confirm: '' })
const quotaForm = reactive({ quota_id: null })

const stats = computed(() => ({
  total: total.value,
  admins: users.value.filter(u => u.role === 'admin').length,
  active: users.value.filter(u => u.is_active).length,
  disabled: users.value.filter(u => !u.is_active).length,
}))

const formRules = {
  username: [
    { required: true, message: '用户名不能为空', trigger: 'blur' },
    { min: 3, max: 50, message: '3-50 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '密码不能为空', trigger: 'blur' },
    { min: 6, message: '至少 6 位', trigger: 'blur' }
  ],
}

const pwdRules = {
  password: [{ required: true, min: 6, message: '至少 6 位', trigger: 'blur' }],
  confirm: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (r, v, cb) => v !== pwdForm.password ? cb(new Error('两次密码不一致')) : cb(),
      trigger: 'blur'
    }
  ]
}

const COLORS = ['#1890ff', '#52c41a', '#fa8c16', '#eb2f96', '#722ed1', '#13c2c2']
const avatarColor = (name) => COLORS[name.charCodeAt(0) % COLORS.length]

const roleLabel = (role) => ({ admin: '管理员', user: '普通用户', guest: '访客' }[role] || role)
const roleTagType = (role) => ({ admin: 'danger', user: 'primary', guest: 'info' }[role] || '')

function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '' }

async function loadList() {
  loading.value = true
  try {
    const res = await usersApi.list({
      page: page.value, per_page: pageSize.value,
      search: search.value, role: filterRole.value,
      ...(filterStatus.value !== null && filterStatus.value !== undefined ? { is_active: filterStatus.value } : {})
    })
    users.value = (res.data.data.items || []).map(u => ({ ...u, _toggling: false }))
    total.value = res.data.data.total
  } finally { loading.value = false }
}

function openCreate() {
  editMode.value = false
  editId.value = null
  Object.assign(form, { username: '', email: '', password: '', role: 'user', is_active: true })
  showCreate.value = true
}

function openEdit(row) {
  editMode.value = true
  editId.value = row.id
  Object.assign(form, { username: row.username, email: row.email || '', password: '', role: row.role, is_active: row.is_active })
  showCreate.value = true
}

async function handleSave() {
  try { await formRef.value.validate() } catch { return }
  saving.value = true
  try {
    const payload = { ...form }
    if (!payload.password) delete payload.password
    if (editMode.value) {
      await usersApi.update(editId.value, payload)
    } else {
      await usersApi.create(payload)
    }
    ElMessage.success(editMode.value ? '更新成功' : '用户创建成功')
    showCreate.value = false
    loadList()
  } finally { saving.value = false }
}

async function toggleActive(row) {
  row._toggling = true
  try {
    await usersApi.update(row.id, { is_active: row.is_active })
    ElMessage.success(row.is_active ? '已启用' : '已禁用')
    loadList()
  } catch {
    row.is_active = !row.is_active
  } finally { row._toggling = false }
}

function openResetPwd(row) {
  pwdUser.value = row
  Object.assign(pwdForm, { password: '', confirm: '' })
  showResetPwd.value = true
}

async function handleResetPwd() {
  try { await pwdFormRef.value.validate() } catch { return }
  saving.value = true
  try {
    await usersApi.update(pwdUser.value.id, { password: pwdForm.password })
    ElMessage.success('密码重置成功')
    showResetPwd.value = false
  } finally { saving.value = false }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除用户 "${row.username}"？此操作不可撤销。`,
      '删除确认', { type: 'warning', confirmButtonText: '确认删除', confirmButtonClass: 'el-button--danger' }
    )
    await usersApi.delete(row.id)
    ElMessage.success('删除成功')
    loadList()
  } catch {}
}

async function openSetQuota(row) {
  quotaUser.value = row
  quotaForm.quota_id = row.quota_id || null
  try {
    const res = await resourcesApi.quotas()
    quotaOptions.value = res.data.data || []
  } catch { quotaOptions.value = [] }
  showQuota.value = true
}

async function handleSetQuota() {
  saving.value = true
  try {
    await usersApi.setQuota(quotaUser.value.id, { quota_id: quotaForm.quota_id })
    ElMessage.success('配额已更新')
    showQuota.value = false
    loadList()
  } finally { saving.value = false }
}

onMounted(loadList)
</script>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
.stats-row { margin-bottom: 4px; }
.stat-card :deep(.el-card__body) { padding: 16px 20px; }
.stat-inner { display: flex; align-items: center; gap: 16px; }
.stat-icon { width: 48px; height: 48px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.stat-num { font-size: 26px; font-weight: 700; color: #262626; line-height: 1.2; }
.stat-label { font-size: 13px; color: #8c8c8c; margin-top: 2px; }
.card-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.card-title { font-size: 16px; font-weight: 600; color: #262626; }
.header-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.user-cell { display: flex; align-items: center; gap: 8px; }
.text-muted { color: #bfbfbf; font-size: 13px; }
.pagination { margin-top: 16px; justify-content: flex-end; display: flex; }
.quota-desc { font-size: 12px; color: #8c8c8c; margin-left: 8px; }
.perm-tip { font-size: 13px; line-height: 1.6; }
.perm-item { display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 6px; }
.perm-item.admin { background: #fff0f6; color: #eb2f96; }
.perm-item.user { background: #e6f4ff; color: #1890ff; }
.perm-item.guest { background: #fafafa; color: #8c8c8c; }
</style>
