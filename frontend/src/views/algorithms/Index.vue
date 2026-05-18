<template>
  <div class="algo-list-page">
    <div class="page-header">
      <div class="header-info">
        <h1>算法管理</h1>
        <p>管理训练算法脚本，支持多版本</p>
      </div>
      <el-button type="primary" @click="openCreate"><el-icon><plus /></el-icon> 上传算法</el-button>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="search-form">
            <el-input v-model="search" placeholder="搜索算法名称" clearable style="width:220px"
              prefix-icon="Search" @keyup.enter="loadList" @clear="loadList" />
            <el-select v-model="filterFramework" placeholder="框架" clearable style="width:130px" @change="loadList">
              <el-option label="PyTorch" value="PyTorch" />
              <el-option label="TensorFlow" value="TensorFlow" />
              <el-option label="JAX" value="JAX" />
            </el-select>
            <el-button type="primary" @click="loadList">搜索</el-button>
          </div>
        </div>
      </template>

      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column label="算法名称" prop="name" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/algorithms/${row.id}`)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="框架" width="100">
          <template #default="{ row }"><el-tag size="small" type="info">{{ row.framework }}</el-tag></template>
        </el-table-column>
        <el-table-column label="任务类型" width="120">
          <template #default="{ row }">{{ taskTypeLabel(row.task_type) }}</template>
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
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/algorithms/${row.id}`)">查看详情</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
        :page-sizes="[12, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadList" style="margin-top: 16px" />
    </el-card>

    <!-- 创建对话框（对齐FTv1） -->
    <el-dialog v-model="showCreate" title="上传算法脚本" width="700px" destroy-on-close>
      <!-- 温馨提示 -->
      <div class="tip-banner">
        <div class="tip-row">
          <el-icon class="tip-icon"><WarningFilled /></el-icon>
          <span class="tip-text">请在训练循环中按以下格式输出指标，否则平台无法展示实时进度和指标曲线。</span>
          <el-button size="small" text type="primary" @click="showTemplate = true">查看规范模板</el-button>
          <el-divider direction="vertical" />
          <el-button size="small" text type="success" @click="downloadTemplate">下载模板</el-button>
        </div>
        <div class="tip-code">
          <span class="tip-code-label">推荐格式：</span>
          <code>print("[METRIC] epoch=1, loss=0.5, accuracy=0.8")</code>
        </div>
      </div>

      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
        <el-form-item label="算法名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入算法名称" />
        </el-form-item>
        <el-form-item label="算法类型">
          <el-select v-model="createForm.algorithm_type" placeholder="可选择或输入自定义类型" style="width: 100%" filterable allow-create clearable default-first-option>
            <el-option v-for="t in allTypeOptions" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" rows="2" />
        </el-form-item>
        <el-form-item label="上传方式">
          <el-radio-group v-model="uploadMode">
            <el-radio value="file">本地文件</el-radio>
            <el-radio value="code">直接输入</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="脚本文件" v-if="uploadMode === 'file'">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            accept=".py"
            drag>
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽文件到此处或<em>点击上传</em></div>
            <template #tip>
              <div class="el-upload__tip">只支持 .py 文件</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="脚本内容" v-if="uploadMode === 'code'">
          <el-input v-model="createForm.script_content" type="textarea" rows="12" placeholder="请输入Python脚本代码" />
        </el-form-item>
        <el-form-item label="参数定义">
          <div class="params-define">
            <div class="params-tip">
              <el-text type="info" size="small">
                <el-icon><InfoFilled /></el-icon>
                定义算法支持的训练参数，创建训练任务时必须填写这些参数
              </el-text>
            </div>
            <div class="params-warn">
              <el-icon><WarningFilled /></el-icon>
              <span><strong>注意：</strong>参数名和默认值必须与脚本中 <code>config.get('参数名', 默认值)</code> 完全一致，否则训练时将无法正确传参</span>
            </div>
            <el-table :data="createForm.params" border size="small" style="margin-top: 8px; width: 100%">
              <el-table-column label="参数名" min-width="120">
                <template #default="{ row }">
                  <el-input v-model="row.name" size="small" placeholder="参数名（与脚本一致）" />
                </template>
              </el-table-column>
              <el-table-column label="显示名" min-width="110">
                <template #default="{ row }">
                  <el-input v-model="row.label" size="small" placeholder="中文名称" />
                </template>
              </el-table-column>
              <el-table-column label="类型" min-width="90">
                <template #default="{ row }">
                  <el-select v-model="row.type" size="small">
                    <el-option label="整数" value="int" />
                    <el-option label="小数" value="float" />
                    <el-option label="字符串" value="string" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="默认值" min-width="100">
                <template #default="{ row }">
                  <el-input v-model="row.default_value" size="small" placeholder="默认值" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="60" align="center">
                <template #default="{ $index }">
                  <el-button type="danger" size="small" link @click="removeParam($index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-button size="small" type="primary" link style="margin-top: 8px;" @click="addParam">
              <el-icon><Plus /></el-icon>添加自定义参数
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 模板查看对话框 -->
    <el-dialog v-model="showTemplate" title="算法脚本模板" width="900px" top="5vh" append-to-body destroy-on-close>
      <div class="template-preview">
        <div class="template-header">
          <span>algorithm_template.py</span>
          <div style="display: flex; gap: 8px">
            <el-button size="small" type="primary" @click="copyTemplate">复制代码</el-button>
            <el-button size="small" type="success" @click="downloadTemplate">下载文件</el-button>
          </div>
        </div>
        <pre class="template-code" v-html="highlightedTemplate"></pre>
      </div>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="showEdit" title="编辑算法" width="520px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="90px">
        <el-form-item label="名称" prop="name"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="框架">
          <el-select v-model="editForm.framework" style="width:100%">
            <el-option label="PyTorch" value="PyTorch" /><el-option label="TensorFlow" value="TensorFlow" />
            <el-option label="JAX" value="JAX" /><el-option label="其他" value="Other" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务类型">
          <el-select v-model="editForm.task_type" style="width:100%">
            <el-option label="图像分类" value="image_classification" />
            <el-option label="目标检测" value="object_detection" />
            <el-option label="文本分类" value="text_classification" />
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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { algorithmsApi } from '@/api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(12)
const search = ref('')
const filterFramework = ref('')
const showCreate = ref(false)
const showEdit = ref(false)
const showTemplate = ref(false)
const saving = ref(false)
const createFormRef = ref()
const editFormRef = ref()
const uploadRef = ref()
const uploadMode = ref('file')
const uploadedFile = ref(null)

const defaultParams = [
  { name: 'epochs', label: '训练轮数', type: 'int', default_value: '10' },
  { name: 'batch_size', label: '批次大小', type: 'int', default_value: '32' },
  { name: 'learning_rate', label: '学习率', type: 'float', default_value: '0.001' }
]

const createForm = reactive({
  name: '', algorithm_type: '', description: '', script_content: '',
  params: JSON.parse(JSON.stringify(defaultParams))
})
const editForm = reactive({ id: null, name: '', framework: 'PyTorch', task_type: 'other', description: '', is_public: false })
const createRules = { name: [{ required: true, message: '算法名称不能为空', trigger: 'blur' }] }
const editRules = { name: [{ required: true, message: '名称不能为空', trigger: 'blur' }] }

const existingTypes = ref([])
const allTypeOptions = computed(() => {
  const preset = ['classification', 'regression', 'clustering', 'deep_learning']
  const merged = new Set([...preset, ...existingTypes.value])
  return [...merged].filter(Boolean)
})

const templateCode = `#!/usr/bin/env python3
"""训练脚本模板

系统环境变量（Docker 容器内自动注入）：
  DATASET_PATH  - 数据集目录  (容器内: /data/dataset)
  OUTPUT_PATH   - 输出目录    (容器内: /data/output)
  训练参数通过 config.json 传入，包含 epochs/batch_size/learning_rate 等
"""
import os
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset


def load_config():
    """加载训练配置（系统自动生成 config.json）"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
    return {
        'epochs': int(config.get('epochs', 10)),
        'batch_size': int(config.get('batch_size', 32)),
        'learning_rate': float(config.get('learning_rate', 0.001)),
        'dataset_path': config.get('dataset_path', os.environ.get('DATASET_PATH', '/data/dataset')),
        'output_path': config.get('output_path', os.environ.get('OUTPUT_PATH', '/data/output')),
    }


class SimpleModel(nn.Module):
    """示例模型 - 请替换为实际模型"""
    def __init__(self, input_dim=784, num_classes=10):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, num_classes)
        )

    def forward(self, x):
        return self.fc(x.view(x.size(0), -1))


def main():
    config = load_config()
    print(f"Config: epochs={config['epochs']}, batch_size={config['batch_size']}, lr={config['learning_rate']}")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # === 请在此处加载您的数据集 ===
    X = torch.randn(1000, 784)
    y = torch.randint(0, 10, (1000,))
    loader = DataLoader(TensorDataset(X, y), batch_size=config['batch_size'], shuffle=True)

    model = SimpleModel().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=config['learning_rate'])

    for epoch in range(1, config['epochs'] + 1):
        model.train()
        total_loss, correct, total = 0, 0, 0
        for batch_x, batch_y in loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad()
            output = model(batch_x)
            loss = criterion(output, batch_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * batch_x.size(0)
            correct += (output.argmax(1) == batch_y).sum().item()
            total += batch_x.size(0)
        avg_loss = total_loss / total
        accuracy = correct / total
        # ===== 关键：输出训练指标（平台通过此行采集数据）=====
        print(f"[METRIC] epoch={epoch}, loss={avg_loss:.4f}, accuracy={accuracy:.4f}")

    os.makedirs(config['output_path'], exist_ok=True)
    torch.save(model.state_dict(), os.path.join(config['output_path'], 'model.pth'))
    print("Training complete.")


if __name__ == '__main__':
    main()
`

const highlightedTemplate = computed(() => {
  const escapeHtml = (str) => str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return templateCode.split('\n').map(line => {
    const escaped = escapeHtml(line)
    if (line.includes('[METRIC]') || line.includes('METRICS:')) return `<span class="hl-key">${escaped}</span>`
    if (line.includes('# ===== 关键') || line.includes('# 打印配置')) return `<span class="hl-comment">${escaped}</span>`
    if (/^\s*#/.test(line)) return `<span class="hl-dim">${escaped}</span>`
    return escaped
  }).join('\n')
})

const TASK_TYPES = { image_classification: '图像分类', object_detection: '目标检测', text_classification: '文本分类', language_model: '语言模型', other: '其他' }
function taskTypeLabel(t) { return TASK_TYPES[t] || t || '其他' }
function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-' }

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value, search: search.value }
    if (filterFramework.value) params.framework = filterFramework.value
    const res = await algorithmsApi.list(params)
    list.value = res.data.data.items
    total.value = res.data.data.total
    const types = list.value.map(i => i.algorithm_type).filter(Boolean)
    existingTypes.value = [...new Set(types)]
  } finally { loading.value = false }
}

function addParam() {
  createForm.params.push({ name: '', label: '', type: 'float', default_value: '' })
}
function removeParam(index) {
  createForm.params.splice(index, 1)
}

function handleFileChange(file) {
  uploadedFile.value = file.raw
  if (!createForm.name && file.name) {
    createForm.name = file.name.replace('.py', '')
  }
}
function handleFileRemove() {
  uploadedFile.value = null
}

function downloadTemplate() {
  const blob = new Blob([templateCode], { type: 'text/x-python' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'algorithm_template.py'
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('模板文件已下载')
}

function copyTemplate() {
  navigator.clipboard.writeText(templateCode).then(() => {
    ElMessage.success('模板代码已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败，请手动复制')
  })
}

function openCreate() {
  Object.assign(createForm, {
    name: '', algorithm_type: '', description: '', script_content: templateCode,
    params: JSON.parse(JSON.stringify(defaultParams))
  })
  uploadMode.value = 'file'
  uploadedFile.value = null
  showCreate.value = true
}

async function handleCreate() {
  await createFormRef.value.validate()

  if (uploadMode.value === 'file' && !uploadedFile.value) {
    ElMessage.warning('请选择要上传的脚本文件')
    return
  }
  if (uploadMode.value === 'code' && !createForm.script_content) {
    ElMessage.warning('请输入脚本内容')
    return
  }

  saving.value = true
  try {
    const formData = new FormData()
    formData.append('name', createForm.name)
    formData.append('algorithm_type', createForm.algorithm_type)
    formData.append('description', createForm.description)

    if (uploadMode.value === 'file') {
      formData.append('file', uploadedFile.value)
    } else {
      formData.append('script_content', createForm.script_content)
    }

    const validParams = createForm.params.filter(p => p.name.trim())
    if (validParams.length > 0) {
      formData.append('parameters', JSON.stringify(validParams))
    }

    const res = await algorithmsApi.createWithScript(formData)
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
    await algorithmsApi.update(editForm.id, { name: editForm.name, framework: editForm.framework, task_type: editForm.task_type, description: editForm.description, is_public: editForm.is_public })
    ElMessage.success('更新成功')
    showEdit.value = false
    loadList()
  } finally { saving.value = false }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除算法 "${row.name}"？`, '删除确认', { type: 'warning' })
  await algorithmsApi.delete(row.id)
  ElMessage.success('删除成功')
  loadList()
}


onMounted(loadList)
</script>

<style scoped>
.algo-list-page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.search-form { display: flex; gap: 12px; align-items: center; }
.action-buttons { display: flex; gap: 4px; }
.pagination { display: flex; justify-content: center; padding: 20px; background: #fff; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-top: 20px; }
:deep(.el-dialog__body) { padding: 20px 30px; }
:deep(.el-form-item) { margin-bottom: 18px; }

.tip-banner { background: #fdf6ec; border: 1px solid #faecd8; border-radius: 4px; padding: 10px 14px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 6px; }
.tip-row { display: flex; align-items: center; gap: 6px; }
.tip-icon { color: #E6A23C; font-size: 15px; flex-shrink: 0; }
.tip-text { font-size: 13px; color: #606266; flex: 1; }
.tip-code { display: flex; align-items: center; gap: 6px; padding: 6px 10px; background: #fff; border: 1px solid #faecd8; border-radius: 4px; margin-left: 21px; }
.tip-code-label { font-size: 12px; color: #909399; flex-shrink: 0; }
.tip-code code { font-size: 13px; color: #e6a23c; font-family: 'Consolas', 'Monaco', monospace; font-weight: 600; }

.params-warn { display: flex; align-items: flex-start; gap: 6px; margin-top: 6px; padding: 8px 10px; background: #fdf6ec; border: 1px solid #faecd8; border-radius: 4px; font-size: 12px; color: #606266; line-height: 1.5; }
.params-warn .el-icon { color: #e6a23c; font-size: 14px; flex-shrink: 0; margin-top: 1px; }
.params-warn code { font-family: 'Consolas', 'Monaco', monospace; background: #fff3e0; padding: 1px 4px; border-radius: 3px; color: #d46b08; }

.template-preview { background: #f8f9fa; border: 1px solid #e4e7ed; border-radius: 6px; overflow: hidden; }
.template-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 14px; background: #eef1f6; border-bottom: 1px solid #e4e7ed; font-size: 13px; font-weight: 600; color: #303133; }
.template-code { max-height: 60vh; overflow-y: auto; font-size: 12px; line-height: 1.6; margin: 0; padding: 12px 14px; white-space: pre-wrap; word-break: break-all; color: #303133; font-family: 'Consolas', 'Monaco', 'Courier New', monospace; }
.template-code :deep(.hl-key) { display: inline; background: #fff7e6; color: #d46b08; font-weight: 700; border-left: 3px solid #fa8c16; padding-left: 6px; margin-left: -9px; }
.template-code :deep(.hl-comment) { color: #389e0d; font-weight: 600; }
.template-code :deep(.hl-dim) { color: #8c8c8c; }
</style>
