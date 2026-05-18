<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-info">
        <h1>K8s 集群管理</h1>
        <p>注册和管理 Kubernetes 集群连接</p>
      </div>
      <el-button type="primary" @click="showCreate = true"><el-icon><plus /></el-icon> 添加集群</el-button>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="clusters" stripe>
        <el-table-column label="集群名称" prop="name" min-width="140" />
        <el-table-column label="API Server" prop="api_server" min-width="200" show-overflow-tooltip />
        <el-table-column label="命名空间" prop="namespace" width="120" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'connected' ? 'success' : row.status === 'error' ? 'danger' : 'info'" size="small">
              {{ row.status || 'unknown' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="默认" width="70" align="center">
          <template #default="{ row }"><el-icon v-if="row.is_default" color="#409eff"><select /></el-icon></template>
        </el-table-column>
        <el-table-column label="描述" prop="description" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="testCluster(row)" :loading="testingId === row.id">连接测试</el-button>
            <el-button link size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑集群对话框 -->
    <el-dialog v-model="showCreate" :title="editMode ? '编辑集群' : '注册K8s集群'" width="580px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px" class="cluster-form">
        <el-form-item label="集群名称" prop="name">
          <el-input v-model="form.name" placeholder="如: production-cluster" />
        </el-form-item>
        <el-form-item label="API Server" prop="api_server">
          <el-input v-model="form.api_server" placeholder="如: https://192.168.1.100:6443" />
        </el-form-item>
        <el-form-item label="命名空间">
          <el-input v-model="form.namespace" placeholder="default" />
        </el-form-item>
        <el-form-item label="认证方式">
          <el-radio-group v-model="form.auth_type">
            <el-radio label="kubeconfig">Kubeconfig</el-radio>
            <el-radio label="token">Bearer Token</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.auth_type === 'kubeconfig'" label="Kubeconfig" prop="kubeconfig_content">
          <el-input v-model="form.kubeconfig_content" type="textarea" :rows="8"
            placeholder="粘贴 kubeconfig 内容（YAML格式）"
            style="font-family: 'Cascadia Code', monospace; font-size: 12px;" />
        </el-form-item>
        <el-form-item v-if="form.auth_type === 'token'" label="Token" prop="token">
          <el-input v-model="form.token" type="textarea" :rows="4"
            placeholder="粘贴 Bearer Token"
            style="font-family: 'Cascadia Code', monospace; font-size: 12px;" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">{{ editMode ? '保存' : '注册' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { clustersApi } from '@/api'

const loading = ref(false)
const clusters = ref([])
const showCreate = ref(false)
const editMode = ref(false)
const saving = ref(false)
const testingId = ref(null)
const editId = ref(null)
const formRef = ref()
const form = reactive({
  name: '', api_server: '', namespace: 'default', auth_type: 'kubeconfig',
  kubeconfig_content: '', token: '', description: ''
})
const formRules = {
  name: [{ required: true, message: '请输入集群名称', trigger: 'blur' }],
  api_server: [{ required: true, message: '请输入 API Server 地址', trigger: 'blur' }]
}

async function loadClusters() {
  loading.value = true
  try {
    const res = await clustersApi.list()
    clusters.value = res.data.data || []
  } finally { loading.value = false }
}

async function testCluster(row) {
  testingId.value = row.id
  try {
    const res = await clustersApi.test(row.id)
    const ok = res.data.data?.connected
    ElMessage[ok ? 'success' : 'error'](res.data.data?.message || (ok ? '连接成功' : '连接失败'))
    loadClusters()
  } finally { testingId.value = null }
}

function openEdit(row) {
  editMode.value = true
  editId.value = row.id
  Object.assign(form, {
    name: row.name,
    api_server: row.api_server,
    namespace: row.namespace || 'default',
    auth_type: row.token ? 'token' : 'kubeconfig',
    kubeconfig_content: row.kubeconfig_content || '',
    token: row.token || '',
    description: row.description || ''
  })
  showCreate.value = true
}

async function handleSave() {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = { ...form }
    if (form.auth_type === 'kubeconfig') {
      delete payload.token
    } else {
      delete payload.kubeconfig_content
    }
    if (editMode.value) {
      await clustersApi.update(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await clustersApi.create(payload)
      ElMessage.success('集群注册成功')
    }
    showCreate.value = false
    editMode.value = false
    loadClusters()
  } finally { saving.value = false }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除集群 "${row.name}"？`, '删除确认', { type: 'warning' })
  await clustersApi.delete(row.id)
  ElMessage.success('删除成功')
  loadClusters()
}

onMounted(loadClusters)
</script>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
.cluster-form :deep(.el-form-item__label) { font-weight: 500; }
</style>
