<template>
  <div class="detail-page">
    <div class="detail-header">
      <div class="header-left">
        <el-button link @click="$router.push('/algorithms')"><el-icon><arrow-left /></el-icon> 返回算法</el-button>
        <h1>{{ algorithm.name }}</h1>
        <el-tag v-if="algorithm.framework" size="small" type="info">{{ algorithm.framework }}</el-tag>
        <el-tag v-if="algorithm.is_public" size="small" type="success">公开</el-tag>
      </div>
      <el-button type="primary" @click="openAdd"><el-icon><plus /></el-icon> 新增版本</el-button>
    </div>

    <div class="detail-content">
      <div class="info-panel">
        <div class="info-card">
          <h3>基本信息</h3>
          <div class="info-stats">
            <div class="stat-item">
              <div class="stat-num">{{ versions.length }}</div>
              <div class="stat-label">版本数</div>
            </div>
          </div>
          <div class="info-list">
            <div class="info-row"><span class="info-key">框架</span><span>{{ algorithm.framework || '-' }}</span></div>
            <div class="info-row"><span class="info-key">任务类型</span><span>{{ taskTypeLabel(algorithm.task_type) }}</span></div>
            <div class="info-row"><span class="info-key">创建时间</span><span>{{ formatTime(algorithm.created_at) }}</span></div>
            <div class="info-row"><span class="info-key">更新时间</span><span>{{ formatTime(algorithm.updated_at) }}</span></div>
          </div>
        </div>
        <div class="info-card" v-if="algorithm.description">
          <h3>描述</h3>
          <p class="desc-text">{{ algorithm.description }}</p>
        </div>
      </div>

      <div class="version-panel">
        <div class="version-header">
          <h3>版本历史 <el-tag size="small" type="info" round>{{ versions.length }}</el-tag></h3>
        </div>
        <div v-if="versions.length" class="version-list">
          <div v-for="ver in versions" :key="ver.id" class="version-item">
            <div class="ver-top">
              <div class="ver-info">
                <span class="ver-number">{{ ver.version_number || 'v' + ver.id }}</span>
                <span class="ver-time">{{ formatTime(ver.created_at) }}</span>
              </div>
              <div class="ver-actions">
                <el-button size="small" link @click="viewScript(ver)"><el-icon><view /></el-icon> 查看脚本</el-button>
              </div>
            </div>
            <div v-if="ver.description" class="ver-desc">{{ ver.description }}</div>
            <div class="ver-meta">
              <span v-if="ver.entry_point"><el-icon><document /></el-icon> {{ ver.entry_point }}</span>
              <span v-if="ver.script_path" class="ver-path"><el-icon><folder-opened /></el-icon> {{ ver.script_path }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-versions">
          <el-icon :size="36" color="#c0c4cc"><cpu /></el-icon>
          <p>暂无版本，点击上方按钮新增第一个版本</p>
        </div>
      </div>
    </div>

    <!-- 新增版本 -->
    <el-dialog v-model="showAdd" title="新增版本" width="600px" destroy-on-close>
      <el-form :model="vForm" label-width="90px">
        <el-form-item label="版本号"><el-input v-model="vForm.version_number" placeholder="如 v1.0（可选，自动生成）" /></el-form-item>
        <el-form-item label="入口文件"><el-input v-model="vForm.entry_point" placeholder="如 train.py" /></el-form-item>
        <el-form-item label="脚本内容">
          <el-input v-model="vForm.script_content" type="textarea" :rows="10"
            placeholder="粘贴训练脚本代码" style="font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 13px;" />
        </el-form-item>
        <el-form-item label="变更说明"><el-input v-model="vForm.description" type="textarea" rows="2" placeholder="描述本次变更" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="addVersion">创建</el-button>
      </template>
    </el-dialog>

    <!-- 查看脚本 -->
    <el-dialog v-model="showScript" :title="`脚本预览 - ${scriptTitle}`" width="700px" destroy-on-close>
      <pre class="script-preview">{{ scriptContent }}</pre>
      <template #footer>
        <el-button @click="showScript = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { algorithmsApi } from '@/api'

const route = useRoute()
const algoId = route.params.id
const algorithm = ref({})
const versions = ref([])
const showAdd = ref(false)
const showScript = ref(false)
const scriptContent = ref('')
const scriptTitle = ref('')
const saving = ref(false)
const vForm = reactive({ version_number: '', entry_point: 'train.py', script_content: '', description: '' })

const TASK_TYPES = { image_classification: '图像分类', object_detection: '目标检测', text_classification: '文本分类', language_model: '语言模型', other: '其他' }
function taskTypeLabel(t) { return TASK_TYPES[t] || t || '-' }
function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-' }

async function loadData() {
  const [aRes, vRes] = await Promise.all([algorithmsApi.get(algoId), algorithmsApi.versions(algoId)])
  algorithm.value = aRes.data.data
  versions.value = vRes.data.data || []
}

function openAdd() {
  Object.assign(vForm, { version_number: '', entry_point: 'train.py', script_content: '', description: '' })
  showAdd.value = true
}

async function addVersion() {
  saving.value = true
  try {
    await algorithmsApi.addVersion(algoId, vForm)
    ElMessage.success('创建成功')
    showAdd.value = false
    loadData()
  } finally { saving.value = false }
}

function viewScript(ver) {
  scriptTitle.value = ver.version_number || 'v' + ver.id
  scriptContent.value = ver.script_content || '（无脚本内容）'
  showScript.value = true
}

onMounted(loadData)
</script>

<style scoped>
.detail-page { padding: 20px; }
.detail-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
.header-left { display: flex; align-items: center; gap: 12px; }
.header-left h1 { font-size: 22px; font-weight: 700; color: #2c3e50; margin: 0; }
.detail-content { display: grid; grid-template-columns: 340px 1fr; gap: 24px; }
.info-panel { display: flex; flex-direction: column; gap: 16px; }
.info-card { background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.info-card h3 { font-size: 15px; font-weight: 600; color: #2c3e50; margin: 0 0 16px; padding-bottom: 12px; border-bottom: 1px solid #f1f5f9; }
.info-stats { display: flex; gap: 24px; margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #f1f5f9; }
.stat-item { text-align: center; flex: 1; }
.stat-num { font-size: 22px; font-weight: 700; color: #2c3e50; }
.stat-label { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.info-list { display: flex; flex-direction: column; gap: 12px; }
.info-row { display: flex; justify-content: space-between; font-size: 14px; }
.info-key { color: #64748b; }
.desc-text { font-size: 14px; color: #475569; line-height: 1.6; margin: 0; }
.version-panel { background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.version-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.version-header h3 { font-size: 15px; font-weight: 600; color: #2c3e50; margin: 0; display: flex; align-items: center; gap: 8px; }
.version-list { display: flex; flex-direction: column; gap: 12px; }
.version-item { padding: 16px; border: 1px solid #f1f5f9; border-radius: 10px; transition: border-color 0.2s; }
.version-item:hover { border-color: #d0d5dd; }
.ver-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.ver-info { display: flex; align-items: center; gap: 12px; }
.ver-number { font-weight: 600; color: #2c3e50; font-size: 15px; }
.ver-time { font-size: 13px; color: #94a3b8; }
.ver-desc { font-size: 13px; color: #64748b; margin-bottom: 8px; line-height: 1.5; }
.ver-meta { display: flex; gap: 16px; font-size: 12px; color: #94a3b8; }
.ver-meta span { display: flex; align-items: center; gap: 4px; }
.ver-path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 300px; }
.empty-versions { text-align: center; padding: 40px 20px; color: #94a3b8; }
.empty-versions p { margin: 12px 0 0; font-size: 14px; }
.script-preview { background: #1e293b; color: #e2e8f0; padding: 20px; border-radius: 8px; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 13px; line-height: 1.6; max-height: 500px; overflow: auto; white-space: pre-wrap; word-break: break-word; margin: 0; }
</style>
