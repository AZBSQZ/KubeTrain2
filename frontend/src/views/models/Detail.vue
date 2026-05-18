<template>
  <div class="detail-page">
    <div class="detail-header">
      <div class="header-left">
        <el-button link @click="$router.push('/models')"><el-icon><arrow-left /></el-icon> 返回模型</el-button>
        <h1>{{ model.name }}</h1>
        <el-tag v-if="model.framework" size="small" type="info">{{ model.framework }}</el-tag>
        <el-tag v-if="model.is_public" size="small" type="success">公开</el-tag>
        <el-tag v-if="model.production_version_id" size="small" type="warning" effect="dark">已设生产版本</el-tag>
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
            <div class="info-row"><span class="info-key">框架</span><span>{{ model.framework || '-' }}</span></div>
            <div class="info-row"><span class="info-key">任务类型</span><span>{{ model.task_type || '-' }}</span></div>
            <div class="info-row"><span class="info-key">来源</span><span>{{ model.source || '-' }}</span></div>
            <div class="info-row"><span class="info-key">创建时间</span><span>{{ formatTime(model.created_at) }}</span></div>
            <div class="info-row"><span class="info-key">更新时间</span><span>{{ formatTime(model.updated_at) }}</span></div>
          </div>
        </div>
        <div class="info-card" v-if="model.description">
          <h3>描述</h3>
          <p class="desc-text">{{ model.description }}</p>
        </div>
      </div>

      <div class="version-panel">
        <div class="version-header">
          <h3>版本历史 <el-tag size="small" type="info" round>{{ versions.length }}</el-tag></h3>
        </div>
        <div v-if="versions.length" class="version-list">
          <div v-for="ver in versions" :key="ver.id" class="version-item" :class="{ 'is-prod': ver.is_production }">
            <div class="ver-top">
              <div class="ver-info">
                <span class="ver-number">{{ ver.version_number || 'v' + ver.id }}</span>
                <el-tag v-if="ver.is_production" size="small" type="warning" effect="dark">生产</el-tag>
                <span class="ver-time">{{ formatTime(ver.created_at) }}</span>
              </div>
              <div class="ver-actions">
                <el-button v-if="!ver.is_production" size="small" link type="success" @click="setProduction(ver)">设为生产</el-button>
              </div>
            </div>
            <div v-if="ver.description" class="ver-desc">{{ ver.description }}</div>
            <div class="ver-meta">
              <span v-if="ver.file_path" class="ver-path"><el-icon><folder-opened /></el-icon> {{ ver.file_path }}</span>
              <template v-if="ver.metrics">
                <span v-if="ver.metrics.final_loss != null"><el-icon><data-line /></el-icon> Loss: {{ ver.metrics.final_loss?.toFixed(4) }}</span>
                <span v-if="ver.metrics.final_accuracy != null"><el-icon><data-line /></el-icon> Acc: {{ (ver.metrics.final_accuracy * 100)?.toFixed(2) }}%</span>
              </template>
            </div>
          </div>
        </div>
        <div v-else class="empty-versions">
          <el-icon :size="36" color="#c0c4cc"><box /></el-icon>
          <p>暂无版本</p>
        </div>
      </div>
    </div>

    <el-dialog v-model="showAdd" title="新增模型版本" width="540px" destroy-on-close>
      <el-form :model="versionForm" label-width="90px">
        <el-form-item label="版本号"><el-input v-model="versionForm.version_number" placeholder="如 v1.0（可选，自动生成）" /></el-form-item>
        <el-form-item label="文件路径"><el-input v-model="versionForm.file_path" placeholder="模型文件或目录路径" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="versionForm.description" type="textarea" rows="3" placeholder="版本描述" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleAddVersion">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { modelsApi } from '@/api'

const route = useRoute()
const modelId = route.params.id
const model = ref({})
const versions = ref([])
const showAdd = ref(false)
const saving = ref(false)
const versionForm = ref({ version_number: '', file_path: '', description: '' })

function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-' }

async function loadData() {
  const [mRes, vRes] = await Promise.all([modelsApi.get(modelId), modelsApi.versions(modelId)])
  model.value = mRes.data.data
  versions.value = vRes.data.data || []
}

function openAdd() {
  versionForm.value = { version_number: '', file_path: '', description: '' }
  showAdd.value = true
}

async function setProduction(ver) {
  await modelsApi.setProduction(modelId, ver.id)
  ElMessage.success('已设为生产版本')
  loadData()
}

async function handleAddVersion() {
  saving.value = true
  try {
    await modelsApi.addVersion(modelId, versionForm.value)
    ElMessage.success('版本已添加')
    showAdd.value = false
    loadData()
  } finally { saving.value = false }
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
.version-item.is-prod { border-color: #fbbf24; background: #fffbeb; }
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
</style>
