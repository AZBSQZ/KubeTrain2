<template>
  <div class="dataset-list-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-info">
        <h1>数据集</h1>
        <p>管理训练数据集，支持版本控制</p>
      </div>
      <el-button type="primary" @click="openCreate"><el-icon><plus /></el-icon> 添加数据集</el-button>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="search-form">
            <el-input v-model="search" placeholder="搜索数据集名称" clearable style="width:220px"
              prefix-icon="Search" @keyup.enter="loadList" @clear="loadList" />
            <el-select v-model="sortBy" style="width:140px" @change="loadList">
              <el-option label="最新创建" value="newest" />
              <el-option label="最早创建" value="oldest" />
              <el-option label="名称 A-Z" value="name_asc" />
            </el-select>
            <el-button type="primary" @click="loadList">搜索</el-button>
          </div>
        </div>
      </template>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column label="数据集名称" prop="name" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/datasets/${row.id}`)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="格式" width="100">
          <template #default="{ row }"><el-tag size="small" type="info">{{ row.format || 'general' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.total_size) }}</template>
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
            <el-button size="small" @click="$router.push(`/datasets/${row.id}`)">查看详情</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" @click="openUpload(row)">上传</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
        :page-sizes="[12, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadList" style="margin-top: 16px" />
    </el-card>

    <!-- 创建对话框 -->
    <el-dialog v-model="showCreate" title="添加数据集" width="560px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="90px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="输入数据集名称" />
        </el-form-item>
        <el-form-item label="格式">
          <el-select v-model="createForm.format" style="width:100%">
            <el-option-group label="常用格式">
              <el-option label="通用" value="general" />
              <el-option label="CSV" value="csv" />
              <el-option label="JSON" value="json" />
            </el-option-group>
            <el-option-group label="图像格式">
              <el-option label="ImageFolder" value="imagefolder" />
            </el-option-group>
            <el-option-group label="其他">
              <el-option label="HuggingFace" value="huggingface" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" rows="3" placeholder="数据集描述信息" />
        </el-form-item>
        <el-form-item label="公开">
          <el-switch v-model="createForm.is_public" />
          <span style="margin-left:8px;font-size:12px;color:#909399">公开后其他用户可查看</span>
        </el-form-item>
        <el-form-item label="上传文件">
          <el-upload drag :before-upload="() => false" :on-change="onCreateFileChange"
            :file-list="createFileList" :limit="1" accept=".zip,.tar.gz,.csv,.json,.jsonl,.txt,.tsv">
            <el-icon size="32" color="#c0c4cc"><upload-filled /></el-icon>
            <div style="margin-top:6px;font-size:13px">拖拽文件到此处，或 <em>点击上传</em></div>
            <template #tip><div style="color:#909399;font-size:12px">支持 .zip / .tar.gz / .csv / .json 等格式（可选）</div></template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="showEdit" title="编辑数据集" width="520px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="90px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="格式">
          <el-select v-model="editForm.format" style="width:100%">
            <el-option label="通用" value="general" /><el-option label="ImageFolder" value="imagefolder" />
            <el-option label="CSV" value="csv" /><el-option label="JSON" value="json" />
            <el-option label="HuggingFace" value="huggingface" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" rows="3" />
        </el-form-item>
        <el-form-item label="公开">
          <el-switch v-model="editForm.is_public" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 上传对话框 -->
    <el-dialog v-model="showUpload" :title="`上传到：${uploadTarget?.name}`" width="500px" destroy-on-close>
      <el-upload drag :before-upload="() => false" :http-request="doUpload" :show-file-list="false">
        <el-icon size="40" color="#c0c4cc"><upload-filled /></el-icon>
        <div style="margin-top:8px">拖拽文件到此处，或 <em>点击上传</em></div>
        <template #tip><div style="color:#909399;font-size:12px">支持 .zip / .tar.gz / .csv 等格式</div></template>
      </el-upload>
      <el-progress v-if="uploadPct > 0" :percentage="uploadPct" style="margin-top:12px" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { datasetsApi } from '@/api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(12)
const search = ref('')
const sortBy = ref('newest')
const showCreate = ref(false)
const showEdit = ref(false)
const showUpload = ref(false)
const uploadTarget = ref(null)
const uploadPct = ref(0)
const saving = ref(false)
const createFormRef = ref()
const editFormRef = ref()
const createForm = reactive({ name: '', format: 'general', description: '', is_public: false })
const editForm = reactive({ id: null, name: '', format: 'general', description: '', is_public: false })
const createRules = { name: [{ required: true, message: '名称不能为空', trigger: 'blur' }] }
const editRules = { name: [{ required: true, message: '名称不能为空', trigger: 'blur' }] }
const createFileList = ref([])
let createFile = null

function formatSize(b) {
  if (!b) return '-'
  if (b < 1024) return b + 'B'
  if (b < 1048576) return (b / 1024).toFixed(1) + 'KB'
  if (b < 1073741824) return (b / 1048576).toFixed(1) + 'MB'
  return (b / 1073741824).toFixed(2) + 'GB'
}
function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-' }

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value, search: search.value }
    if (sortBy.value === 'oldest') params.sort = 'created_at'
    else if (sortBy.value === 'name_asc') params.sort = 'name'
    else params.sort = '-created_at'
    const res = await datasetsApi.list(params)
    list.value = res.data.data.items
    total.value = res.data.data.total
  } finally { loading.value = false }
}

function openCreate() {
  Object.assign(createForm, { name: '', format: 'general', description: '', is_public: false })
  createFileList.value = []
  createFile = null
  showCreate.value = true
}

function onCreateFileChange(file) { createFile = file.raw; createFileList.value = [file] }

async function handleCreate() {
  await createFormRef.value.validate()
  saving.value = true
  try {
    const res = await datasetsApi.create(createForm)
    const dsId = res.data.data.id
    if (createFile) {
      const fd = new FormData()
      fd.append('file', createFile)
      await datasetsApi.upload(dsId, fd, () => {})
    }
    ElMessage.success('创建成功')
    showCreate.value = false
    loadList()
  } finally { saving.value = false }
}

function openEdit(row) {
  Object.assign(editForm, { id: row.id, name: row.name, format: row.format || 'general', description: row.description || '', is_public: !!row.is_public })
  showEdit.value = true
}

async function handleEdit() {
  await editFormRef.value.validate()
  saving.value = true
  try {
    await datasetsApi.update(editForm.id, { name: editForm.name, format: editForm.format, description: editForm.description, is_public: editForm.is_public })
    ElMessage.success('更新成功')
    showEdit.value = false
    loadList()
  } finally { saving.value = false }
}

function openUpload(row) { uploadTarget.value = row; uploadPct.value = 0; showUpload.value = true }

async function doUpload({ file }) {
  const fd = new FormData()
  fd.append('file', file)
  uploadPct.value = 0
  try {
    await datasetsApi.upload(uploadTarget.value.id, fd, e => {
      uploadPct.value = Math.round(e.loaded / e.total * 100)
    })
    ElMessage.success('上传成功')
    showUpload.value = false
    loadList()
  } catch { ElMessage.error('上传失败') }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除 "${row.name}"？`, '删除确认', { type: 'warning' })
  await datasetsApi.delete(row.id)
  ElMessage.success('删除成功')
  loadList()
}


onMounted(loadList)
</script>

<style scoped>
.dataset-list-page { padding: 20px; }

.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }

.card-header { display: flex; justify-content: space-between; align-items: center; }
.search-form { display: flex; gap: 12px; align-items: center; }
:deep(.el-dialog__body) { padding: 20px 30px; }
:deep(.el-form-item) { margin-bottom: 18px; }
</style>
