<template>
  <div class="detail-page">
    <!-- 页面头部 -->
    <div class="detail-header">
      <div class="header-left">
        <el-button link @click="$router.push('/datasets')"><el-icon><arrow-left /></el-icon> 返回数据集</el-button>
        <h1>{{ dataset.name }}</h1>
        <el-tag v-if="dataset.is_public" type="success" size="small">公开</el-tag>
        <el-tag v-else type="info" size="small">私有</el-tag>
        <el-tag size="small">{{ dataset.format || 'general' }}</el-tag>
      </div>
      <el-button type="primary" @click="openAddVersion"><el-icon><upload-filled /></el-icon> 上传新版本</el-button>
    </div>

    <!-- 内容区域 -->
    <div class="detail-content">
      <!-- 左侧信息 -->
      <div class="info-panel">
        <div class="info-card">
          <h3>基本信息</h3>
          <div class="info-stats">
            <div class="stat-item">
              <div class="stat-num">{{ versions.length }}</div>
              <div class="stat-label">版本数</div>
            </div>
            <div class="stat-item">
              <div class="stat-num">{{ formatSize(dataset.total_size) }}</div>
              <div class="stat-label">总大小</div>
            </div>
          </div>
          <div class="info-list">
            <div class="info-row"><span class="info-key">格式</span><span>{{ dataset.format || '-' }}</span></div>
            <div class="info-row"><span class="info-key">创建时间</span><span>{{ formatTime(dataset.created_at) }}</span></div>
            <div class="info-row"><span class="info-key">更新时间</span><span>{{ formatTime(dataset.updated_at) }}</span></div>
          </div>
        </div>
        <div class="info-card" v-if="dataset.description">
          <h3>描述</h3>
          <p class="desc-text">{{ dataset.description }}</p>
        </div>
      </div>

      <!-- 右侧版本历史 -->
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
                <el-button v-if="ver.file_path" size="small" link>
                  <el-icon><download /></el-icon> 下载
                </el-button>
              </div>
            </div>
            <div v-if="ver.description" class="ver-desc">{{ ver.description }}</div>
            <div class="ver-meta">
              <span v-if="ver.file_size"><el-icon><document /></el-icon> {{ formatSize(ver.file_size) }}</span>
              <span v-if="ver.file_path" class="ver-path"><el-icon><folder-opened /></el-icon> {{ ver.file_path }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-versions">
          <el-icon :size="36" color="#c0c4cc"><document /></el-icon>
          <p>暂无版本，点击上方按钮上传第一个版本</p>
        </div>
      </div>
    </div>

    <!-- 上传新版本对话框 -->
    <el-dialog v-model="showAdd" title="上传新版本" width="520px" destroy-on-close>
      <el-form ref="versionFormRef" :model="versionForm" label-width="90px">
        <el-form-item label="版本标签">
          <el-input v-model="versionForm.version_number" placeholder="如 v1.1（可选，自动生成）" />
        </el-form-item>
        <el-form-item label="变更类型">
          <el-select v-model="versionForm.change_type" style="width:100%">
            <el-option label="新增数据" value="addition" />
            <el-option label="数据修正" value="correction" />
            <el-option label="格式调整" value="format_change" />
            <el-option label="完整替换" value="replacement" />
          </el-select>
        </el-form-item>
        <el-form-item label="变更说明">
          <el-input v-model="versionForm.description" type="textarea" rows="3" placeholder="描述本次变更内容" />
        </el-form-item>
        <el-form-item label="上传文件">
          <el-upload drag :before-upload="() => false" :http-request="doUpload" :show-file-list="false">
            <el-icon size="36" color="#c0c4cc"><upload-filled /></el-icon>
            <div style="margin-top:6px;font-size:13px">拖拽文件到此处，或 <em>点击上传</em></div>
            <template #tip><div style="color:#909399;font-size:12px">支持 .zip / .tar.gz / .csv / .json 等格式</div></template>
          </el-upload>
          <el-progress v-if="uploadPct > 0" :percentage="uploadPct" style="margin-top:8px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { datasetsApi } from '@/api'

const route = useRoute()
const datasetId = route.params.id
const dataset = ref({})
const versions = ref([])
const showAdd = ref(false)
const uploadPct = ref(0)
const versionFormRef = ref()
const versionForm = ref({ version_number: '', change_type: 'addition', description: '' })

function formatSize(b) {
  if (!b) return '-'
  if (b < 1024) return b + 'B'
  if (b < 1048576) return (b / 1024).toFixed(1) + 'KB'
  if (b < 1073741824) return (b / 1048576).toFixed(1) + 'MB'
  return (b / 1073741824).toFixed(2) + 'GB'
}
function formatTime(t) { return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-' }

async function loadData() {
  const [dRes, vRes] = await Promise.all([datasetsApi.get(datasetId), datasetsApi.versions(datasetId)])
  dataset.value = dRes.data.data
  versions.value = vRes.data.data || []
}

function openAddVersion() {
  versionForm.value = { version_number: '', change_type: 'addition', description: '' }
  uploadPct.value = 0
  showAdd.value = true
}

async function doUpload({ file }) {
  const fd = new FormData()
  fd.append('file', file)
  if (versionForm.value.version_number) fd.append('version_number', versionForm.value.version_number)
  if (versionForm.value.description) fd.append('description', versionForm.value.description)
  if (versionForm.value.change_type) fd.append('change_type', versionForm.value.change_type)
  uploadPct.value = 0
  try {
    await datasetsApi.upload(datasetId, fd, e => { uploadPct.value = Math.round(e.loaded / e.total * 100) })
    ElMessage.success('版本上传成功')
    showAdd.value = false
    loadData()
  } catch { ElMessage.error('上传失败') }
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
</style>
