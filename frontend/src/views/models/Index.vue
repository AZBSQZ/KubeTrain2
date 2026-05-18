<template>
  <div class="model-list-page">
    <div class="page-header">
      <div class="header-info">
        <h1>模型仓库</h1>
        <p>管理预训练模型和训练产出模型</p>
      </div>
      <el-button type="primary" @click="openCreate"><el-icon><plus /></el-icon> 注册模型</el-button>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="search-form">
            <el-input v-model="search" placeholder="搜索模型名称" clearable style="width:220px"
              prefix-icon="Search" @keyup.enter="loadList" @clear="loadList" />
            <el-select v-model="filterFramework" placeholder="框架" clearable style="width:130px" @change="loadList">
              <el-option label="PyTorch" value="PyTorch" />
              <el-option label="TensorFlow" value="TensorFlow" />
              <el-option label="ONNX" value="ONNX" />
            </el-select>
            <el-button type="primary" @click="loadList">搜索</el-button>
          </div>
        </div>
      </template>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column label="模型名称" prop="name" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/models/${row.id}`)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="框架" width="100">
          <template #default="{ row }"><el-tag size="small" type="info">{{ row.framework }}</el-tag></template>
        </el-table-column>
        <el-table-column label="来源" width="80">
          <template #default="{ row }">
            <el-tag :type="row.source === 'upload' ? 'info' : 'success'" size="small">
              {{ row.source === 'upload' ? '上传' : row.source || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本数" prop="version_count" width="80" align="center" />
        <el-table-column label="公开" width="80" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.is_public" size="small" disabled />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/models/${row.id}`)">查看详情</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
        :page-sizes="[12, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadList" style="margin-top: 16px" />
    </el-card>

    <!-- 创建对话框（对齐FTv1） -->
    <el-dialog v-model="showCreate" title="上传模型" width="560px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
        <el-form-item label="模型名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入模型名称" />
        </el-form-item>
        <el-form-item label="模型类型">
          <el-select v-model="createForm.model_type" placeholder="请选择模型类型" style="width: 100%">
            <el-option label="CNN" value="CNN" />
            <el-option label="RNN" value="RNN" />
            <el-option label="Transformer" value="Transformer" />
          </el-select>
        </el-form-item>
        <el-form-item label="是否公开">
          <el-switch v-model="createForm.is_public" active-text="公开" inactive-text="私有" />
          <span style="margin-left: 12px; font-size: 12px; color: #909399;">公开后其他用户可查看和使用此模型</span>
        </el-form-item>
        <el-form-item label="模型文件">
          <el-upload ref="modelUploadRef" :auto-upload="false" :limit="1" :on-change="handleModelFileChange" :on-remove="handleModelFileRemove" accept=".pkl,.pth,.pt">
            <el-button type="primary">选择文件</el-button>
            <template #tip><div class="el-upload__tip">支持 pkl, pth, pt 格式</div></template>
          </el-upload>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" rows="3" placeholder="请输入模型描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="showEdit" title="编辑模型" width="520px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="90px">
        <el-form-item label="名称" prop="name"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="框架">
          <el-select v-model="editForm.framework" style="width:100%">
            <el-option label="PyTorch" value="PyTorch" /><el-option label="TensorFlow" value="TensorFlow" />
            <el-option label="ONNX" value="ONNX" /><el-option label="其他" value="Other" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务类型">
          <el-select v-model="editForm.task_type" style="width:100%">
            <el-option label="图像分类" value="image_classification" />
            <el-option label="目标检测" value="object_detection" />
            <el-option label="语言模型" value="language_model" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="editForm.description" type="textarea" rows="3" /></el-form-item>
        <el-form-item label="公开"><el-switch v-model="editForm.is_public" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { modelsApi } from '@/api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(12)
const search = ref('')
const filterFramework = ref('')
const showCreate = ref(false)
const showEdit = ref(false)
const saving = ref(false)
const createFormRef = ref()
const editFormRef = ref()
const modelUploadRef = ref()
const modelUploadedFile = ref(null)
const createForm = reactive({ name: '', model_type: '', description: '', is_public: false })
const editForm = reactive({ id: null, name: '', framework: 'PyTorch', task_type: 'other', description: '', is_public: false })
const createRules = { name: [{ required: true, message: '模型名称不能为空', trigger: 'blur' }] }
const editRules = { name: [{ required: true, message: '名称不能为空', trigger: 'blur' }] }

function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-' }

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value, search: search.value }
    if (filterFramework.value) params.framework = filterFramework.value
    const res = await modelsApi.list(params)
    list.value = res.data.data.items
    total.value = res.data.data.total
  } finally { loading.value = false }
}

function handleModelFileChange(file) {
  modelUploadedFile.value = file.raw
  if (!createForm.name && file.name) {
    createForm.name = file.name.replace(/\.(pkl|pth|pt)$/, '')
  }
}
function handleModelFileRemove() {
  modelUploadedFile.value = null
}

function openCreate() {
  Object.assign(createForm, { name: '', model_type: '', description: '', is_public: false })
  modelUploadedFile.value = null
  showCreate.value = true
}

async function handleCreate() {
  await createFormRef.value.validate()
  saving.value = true
  try {
    const formData = new FormData()
    formData.append('name', createForm.name)
    formData.append('model_type', createForm.model_type)
    formData.append('description', createForm.description)
    formData.append('is_public', createForm.is_public)
    if (modelUploadedFile.value) {
      formData.append('model_file', modelUploadedFile.value)
    }
    const res = await modelsApi.createWithFile(formData)
    if (res.data.code === 200) {
      ElMessage.success('上传成功')
      showCreate.value = false
      loadList()
    } else {
      ElMessage.error(res.data.message || '创建失败')
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.message || '创建失败')
  } finally { saving.value = false }
}

function openEdit(row) {
  Object.assign(editForm, { id: row.id, name: row.name, framework: row.framework || 'PyTorch', task_type: row.task_type || 'other', description: row.description || '', is_public: !!row.is_public })
  showEdit.value = true
}

async function handleEdit() {
  await editFormRef.value.validate()
  saving.value = true
  try {
    await modelsApi.update(editForm.id, { name: editForm.name, framework: editForm.framework, task_type: editForm.task_type, description: editForm.description, is_public: editForm.is_public })
    ElMessage.success('更新成功')
    showEdit.value = false
    loadList()
  } finally { saving.value = false }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除模型 "${row.name}"？`, '删除确认', { type: 'warning' })
  await modelsApi.delete(row.id)
  ElMessage.success('删除成功')
  loadList()
}


onMounted(loadList)
</script>

<style scoped>
.model-list-page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.search-form { display: flex; gap: 12px; align-items: center; }
:deep(.el-dialog__body) { padding: 20px 30px; }
:deep(.el-form-item) { margin-bottom: 18px; }
</style>
