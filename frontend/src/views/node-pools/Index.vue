<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-info">
        <h1>节点池管理</h1>
        <p>管理计算节点池与资源分配</p>
      </div>
      <el-button type="primary" @click="showCreate = true"><el-icon><plus /></el-icon> 新建节点池</el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="pools" v-loading="loading" stripe>
        <el-table-column label="名称" prop="name" min-width="140" />
        <el-table-column label="提供商" prop="provider" width="100" />
        <el-table-column label="GPU类型" width="120">
          <template #default="{ row }">{{ row.gpu_type || '-' }}</template>
        </el-table-column>
        <el-table-column label="节点数" width="100" align="center">
          <template #default="{ row }">{{ row.node_count || 0 }} / {{ row.max_nodes }}</template>
        </el-table-column>
        <el-table-column label="在线" prop="online_count" width="70" align="center" />
        <el-table-column label="总GPU" prop="total_gpus" width="80" align="center" />
        <el-table-column label="可用GPU" prop="available_gpus" width="80" align="center" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openNodes(row)">节点列表</el-button>
            <el-button size="small" @click="openAddNode(row)">添加节点</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建节点池 -->
    <el-dialog v-model="showCreate" title="新建节点池" width="540px">
      <el-form ref="createFormRef" :model="createForm" label-width="100px">
        <el-form-item label="名称"><el-input v-model="createForm.name" /></el-form-item>
        <el-form-item label="提供商">
          <el-select v-model="createForm.provider" style="width:100%">
            <el-option label="裸机" value="bare_metal" />
            <el-option label="Kubernetes" value="kubernetes" />
            <el-option label="云主机" value="cloud" />
          </el-select>
        </el-form-item>
        <el-form-item label="GPU类型"><el-input v-model="createForm.gpu_type" placeholder="如 A100, RTX3090" /></el-form-item>
        <el-form-item label="GPU/节点"><el-input-number v-model="createForm.gpu_per_node" :min="0" /></el-form-item>
        <el-form-item label="最大节点数"><el-input-number v-model="createForm.max_nodes" :min="1" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="createForm.description" type="textarea" rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 节点列表 -->
    <el-dialog v-model="showNodes" :title="`${selectedPool?.name} - 节点列表`" width="720px">
      <el-table :data="poolNodes" size="small">
        <el-table-column label="节点名" prop="name" min-width="140" />
        <el-table-column label="类型" prop="node_type" width="100" />
        <el-table-column label="IP" prop="ip_address" width="130" />
        <el-table-column label="端口" prop="port" width="70" align="center" />
        <el-table-column label="最大任务" prop="max_tasks" width="80" align="center" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'online' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link size="small" type="danger" @click="removeNode(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 添加节点 -->
    <el-dialog v-model="showAddNode" :title="`添加节点到 ${selectedPool?.name}`" width="480px">
      <el-form :model="nodeForm" label-width="90px">
        <el-form-item label="节点名称"><el-input v-model="nodeForm.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="nodeForm.node_type" style="width:100%">
            <el-option label="独立机器" value="standalone" />
            <el-option label="K8s节点" value="k8s_node" />
          </el-select>
        </el-form-item>
        <el-form-item label="IP地址"><el-input v-model="nodeForm.ip_address" /></el-form-item>
        <el-form-item label="端口"><el-input-number v-model="nodeForm.port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="最大任务数"><el-input-number v-model="nodeForm.max_tasks" :min="1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddNode = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleAddNode">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { nodePoolsApi } from '@/api'

const loading = ref(false)
const pools = ref([])
const showCreate = ref(false)
const showNodes = ref(false)
const showAddNode = ref(false)
const selectedPool = ref(null)
const poolNodes = ref([])
const saving = ref(false)
const createFormRef = ref()
const createForm = reactive({ name: '', provider: 'bare_metal', gpu_type: '', gpu_per_node: 1, max_nodes: 10, description: '' })
const nodeForm = reactive({ name: '', node_type: 'standalone', ip_address: '', port: 8005, max_tasks: 2 })

async function loadPools() {
  loading.value = true
  try {
    const res = await nodePoolsApi.list()
    pools.value = res.data.data || []
  } finally { loading.value = false }
}

async function handleCreate() {
  saving.value = true
  try {
    await nodePoolsApi.create(createForm)
    ElMessage.success('节点池创建成功')
    showCreate.value = false
    loadPools()
  } finally { saving.value = false }
}

async function openNodes(pool) {
  selectedPool.value = pool
  const res = await nodePoolsApi.get(pool.id)
  poolNodes.value = res.data.data.nodes || []
  showNodes.value = true
}

function openAddNode(pool) { selectedPool.value = pool; showAddNode.value = true }

async function handleAddNode() {
  saving.value = true
  try {
    await nodePoolsApi.addNode(selectedPool.value.id, nodeForm)
    ElMessage.success('节点已添加')
    showAddNode.value = false
    loadPools()
  } finally { saving.value = false }
}

async function removeNode(node) {
  await ElMessageBox.confirm(`确认移除节点 "${node.name}"？`, '确认', { type: 'warning' })
  await nodePoolsApi.removeNode(selectedPool.value.id, node.id)
  ElMessage.success('节点已移除')
  openNodes(selectedPool.value)
  loadPools()
}

async function handleDelete(pool) {
  await ElMessageBox.confirm(`确认删除节点池 "${pool.name}"？`, '删除确认', { type: 'warning' })
  await nodePoolsApi.delete(pool.id)
  ElMessage.success('删除成功')
  loadPools()
}

onMounted(loadPools)
</script>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
</style>
