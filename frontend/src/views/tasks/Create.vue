<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <el-button link @click="$router.push('/tasks')"><el-icon><arrow-left /></el-icon> 返回任务</el-button>
        <h1>新建训练任务</h1>
      </div>
    </div>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" size="default">
      <!-- 基本信息 -->
      <el-card shadow="never" class="form-card">
        <template #header>基本信息</template>
        <el-row :gutter="20">
          <el-col :span="12"><el-form-item label="任务名称" prop="name"><el-input v-model="form.name" placeholder="请输入任务名称" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="优先级"><el-slider v-model="form.priority" :min="1" :max="10" show-input /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="执行模式"><el-select v-model="form.execution_mode"><el-option label="自动" value="auto" /><el-option label="K8s Job" value="k8s" /><el-option label="Agent" value="agent" /></el-select></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="描述"><el-input v-model="form.description" type="textarea" rows="2" placeholder="任务描述（可选）" /></el-form-item></el-col>
        </el-row>
      </el-card>
      <!-- 数据集（二级选择器） -->
      <el-card shadow="never" class="form-card">
        <template #header>数据集</template>
        <el-row :gutter="20">
          <el-col :span="12"><el-form-item label="数据集"><el-select v-model="selectedDatasetId" placeholder="选择数据集" filterable clearable style="width:100%" @change="onDatasetGroupChange"><el-option v-for="d in datasetGroups" :key="d.id" :label="d.name" :value="d.id"><div class="opt2"><span class="opt-m">{{ d.name }}</span><span class="opt-s">{{ d.description || '暂无描述' }}</span></div></el-option></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="数据集版本"><el-select v-model="form.dataset_version_id" placeholder="选择版本" filterable clearable style="width:100%" :disabled="!selectedDatasetId"><el-option v-for="v in filteredDatasetVersions" :key="v.id" :label="`v${v.version_number}`" :value="v.id" /></el-select></el-form-item></el-col>
        </el-row>
      </el-card>
      <!-- 算法（二级选择器 + 脚本） -->
      <el-card shadow="never" class="form-card">
        <template #header>算法 & 脚本</template>
        <el-row :gutter="20">
          <el-col :span="12"><el-form-item label="算法"><el-select v-model="selectedAlgorithmId" placeholder="选择算法" filterable clearable style="width:100%" @change="onAlgorithmGroupChange"><el-option v-for="a in algorithmGroups" :key="a.id" :label="a.name" :value="a.id"><div class="opt2"><span class="opt-m">{{ a.name }}</span><span class="opt-s">{{ a.framework || 'PyTorch' }} · {{ a.description || '' }}</span></div></el-option></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="算法版本"><el-select v-model="form.algorithm_version_id" placeholder="选择版本" filterable clearable style="width:100%" :disabled="!selectedAlgorithmId" @change="onAlgorithmVersionChange"><el-option v-for="v in filteredAlgorithmVersions" :key="v.id" :label="`v${v.version_number}` + (v.version_name ? ` (${v.version_name})` : '')" :value="v.id" /></el-select></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="训练脚本" prop="training_script"><el-input v-model="form.training_script" placeholder="选择算法版本后自动填充，或手动输入"><template #append><el-dropdown trigger="click" @command="onScriptSourceCmd"><el-button>{{ {path:'路径',content:'粘贴',upload:'上传'}[scriptSource] }}</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="path">使用路径</el-dropdown-item><el-dropdown-item command="content">粘贴内容</el-dropdown-item><el-dropdown-item command="upload">上传文件</el-dropdown-item></el-dropdown-menu></template></el-dropdown></template></el-input></el-form-item></el-col>
          <el-col :span="24" v-if="scriptSource==='content'"><el-form-item label="脚本内容"><el-input v-model="form.script_content" type="textarea" rows="8" placeholder="粘贴 Python 脚本" style="font-family:monospace;font-size:13px" /></el-form-item></el-col>
          <el-col :span="24" v-if="scriptSource==='upload'"><el-form-item label="上传脚本"><el-upload :auto-upload="false" :limit="1" accept=".py,.sh" :on-change="handleScriptUpload" :on-remove="handleScriptRemove" drag class="script-upload"><el-icon class="el-icon--upload"><upload-filled /></el-icon><div class="el-upload__text">拖拽或 <em>点击上传</em></div></el-upload></el-form-item></el-col>
        </el-row>
      </el-card>
      <!-- 训练配置（动态参数） -->
      <el-card shadow="never" class="form-card">
        <template #header><div class="chf"><span>训练配置</span><el-button v-if="algoParams.length>0" size="small" text type="primary" @click="clearConfig">清空（使用默认值）</el-button></div></template>
        <div v-if="!form.algorithm_version_id" class="config-tip">请先选择算法版本，参数将自动加载</div>
        <template v-else>
          <div class="config-tip">共 {{ algoParams.length }} 个参数，留空使用脚本默认值</div>
          <div class="param-grid">
            <div class="param-row" v-for="p in algoParams" :key="p.name">
              <div class="pr-label"><span class="pr-name">{{ p.label||p.name }}</span><span class="pr-code">{{ p.name }}</span></div>
              <div class="pr-input">
                <el-input-number v-if="p.type==='int'" v-model="form.configObj[p.name]" :min="0" size="small" :placeholder="String(p.default_value??'默认')" controls-position="right" style="width:100%" />
                <el-input-number v-else-if="p.type==='float'" v-model="form.configObj[p.name]" :step="0.0001" :precision="5" size="small" :placeholder="String(p.default_value??'默认')" controls-position="right" style="width:100%" />
                <el-input v-else v-model="form.configObj[p.name]" size="small" :placeholder="String(p.default_value??'默认')" />
              </div>
            </div>
          </div>
        </template>
      </el-card>
      <!-- 预训练模型（二级选择器） -->
      <el-card shadow="never" class="form-card">
        <template #header>预训练模型（可选）</template>
        <el-row :gutter="20">
          <el-col :span="12"><el-form-item label="模型"><el-select v-model="selectedModelId" placeholder="选择模型" filterable clearable style="width:100%" @change="onModelGroupChange"><el-option v-for="m in modelGroups" :key="m.id" :label="m.name" :value="m.id"><div class="opt2"><span class="opt-m">{{ m.name }}</span><span class="opt-s">{{ m.framework||'PyTorch' }}</span></div></el-option></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="模型版本"><el-select v-model="form.model_version_id" placeholder="选择版本" filterable clearable style="width:100%" :disabled="!selectedModelId"><el-option v-for="v in filteredModelVersions" :key="v.id" :label="`v${v.version_number}`" :value="v.id" /></el-select></el-form-item></el-col>
        </el-row>
      </el-card>
      <!-- 计算资源 & 训练模式 -->
      <el-card shadow="never" class="form-card">
        <template #header><div class="chf"><span>计算资源 & 训练模式</span><el-button size="small" text type="primary" @click="refreshResources" :loading="loadingResources">刷新资源</el-button></div></template>
        <el-form-item label="计算资源">
          <div class="resource-selector">
            <div v-if="nodeDetails.length===0&&!loadingResources" style="color:#909399;font-size:13px"><el-tag type="warning" size="small">暂无在线节点</el-tag> 将使用本地进程执行</div>
            <el-radio-group v-model="form.compute_resource" v-else class="node-radio-group">
              <el-radio v-for="n in nodeDetails" :key="n.id" :value="n.id" class="node-radio-item">
                <div class="node-detail-opt">
                  <div class="node-badges">
                    <el-tag :type="n.gpu_total > 0 ? 'success' : 'info'" size="small">{{ n.gpu_total > 0 ? 'GPU' : 'CPU' }}</el-tag>
                    <el-tag type="" size="small">{{ n.node_type === 'k8s_node' ? 'K8s节点' : '独立节点' }}</el-tag>
                  </div>
                  <div class="node-info-line">
                    <span class="node-spec">{{ n.cpu_total || '?' }}核 CPU</span>
                    <span v-if="n.gpu_total > 0" class="node-spec">{{ n.gpu_total }} GPU<span v-if="n.gpu_model" style="color:#909399"> ({{ n.gpu_model }})</span></span>
                    <span class="node-spec">{{ n.memory_total ? Math.round(n.memory_total / 1024) + 'GB' : '?' }} 内存</span>
                  </div>
                  <div class="node-host">({{ n.node_type === 'k8s_node' ? 'K8s' : '独立节点' }}: {{ n.hostname || n.name || n.ip_address || 'unknown' }})</div>
                </div>
              </el-radio>
            </el-radio-group>
            <!-- Summary -->
            <div v-if="nodeDetails.length > 0" class="resource-summary">
              <el-tag type="info" size="small">{{ nodeDetails.length }} 节点在线</el-tag>
              <span v-if="computeResources.find(r=>r.type==='gpu')" style="margin-left:8px;font-size:12px;color:#67C23A">共 {{ computeResources.find(r=>r.type==='gpu')?.total_gpu || 0 }} GPU 可用</span>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="训练模式">
          <el-radio-group v-model="form.parallel_mode" @change="onParallelModeChange">
            <el-radio value="single">单机训练</el-radio>
            <el-radio value="local_ddp">单机多进程 (DDP)</el-radio>
            <el-radio value="distributed" :disabled="!canDistributed">多节点分布式</el-radio>
          </el-radio-group>
          <div v-if="form.parallel_mode==='local_ddp'" class="mode-params"><span>进程数:</span><el-input-number v-model="form.nproc_per_node" :min="2" :max="16" size="small" /></div>
          <div v-if="form.parallel_mode==='distributed'" class="mode-params"><span>节点数:</span><el-input-number v-model="form.num_nodes" :min="2" :max="availableNodeCount||8" size="small" /><span>每节点GPU:</span><el-input-number v-model="form.gpus_per_node" :min="0" :max="8" size="small" /></div>
          <div class="node-hint"><span v-if="loadingResources" style="color:#909399">检测节点...</span><span v-else-if="availableNodeCount===0" style="color:#F56C6C">无在线节点，本地执行</span><span v-else style="color:#67C23A">{{ availableNodeCount }} 个在线节点</span></div>
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="6"><el-form-item label="CPU Req"><el-input v-model="form.cpu_request" placeholder="1" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="CPU Lim"><el-input v-model="form.cpu_limit" placeholder="4" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="Mem Req"><el-input v-model="form.memory_request" placeholder="4Gi" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="Mem Lim"><el-input v-model="form.memory_limit" placeholder="8Gi" /></el-form-item></el-col>
        </el-row>
      </el-card>
      <!-- 流水线配置 -->
      <el-card shadow="never" class="form-card">
        <template #header>流水线配置</template>
        <el-switch v-model="pipelineEnabled" active-text="多阶段流水线" inactive-text="单阶段（默认）" />
        <template v-if="pipelineEnabled">
          <div v-for="(st,idx) in pipelineStages" :key="idx" class="pipe-stage">
            <div class="ps-head"><el-tag :type="st.enabled?'primary':'info'" size="small">{{ idx+1 }}</el-tag><el-input v-model="st.name" size="small" style="width:180px;margin:0 8px" placeholder="阶段名" /><el-switch v-model="st.enabled" size="small" /><el-button v-if="pipelineStages.length>2" size="small" text type="danger" @click="removeStage(idx)">删除</el-button></div>
            <el-row v-if="st.enabled" :gutter="12" style="margin-top:8px">
              <el-col :span="12"><el-select v-model="st.algorithm_version_id" placeholder="算法版本" filterable size="small" style="width:100%"><el-option v-for="a in allAlgorithmVersions" :key="a.id" :value="a.id" :label="`${a.algorithm_name} v${a.version_number}`" /></el-select></el-col>
              <el-col :span="12"><el-select v-model="st.model_version_id" placeholder="模型(可选)" filterable clearable size="small" style="width:100%"><el-option v-for="m in allModelVersions" :key="m.id" :value="m.id" :label="`${m.model_name} v${m.version_number}`" /></el-select></el-col>
              <el-col :span="8" style="margin-top:6px"><el-input-number v-model="st.config.epochs" :min="1" size="small" controls-position="right" style="width:100%" /><div class="ph">Epochs</div></el-col>
              <el-col :span="8" style="margin-top:6px"><el-input-number v-model="st.config.batch_size" :min="1" size="small" controls-position="right" style="width:100%" /><div class="ph">Batch</div></el-col>
              <el-col :span="8" style="margin-top:6px"><el-input-number v-model="st.config.learning_rate" :min="0.00001" :step="0.0001" :precision="5" size="small" controls-position="right" style="width:100%" /><div class="ph">LR</div></el-col>
            </el-row>
          </div>
          <el-button type="primary" text @click="addStage" style="margin-top:8px">+ 添加阶段</el-button>
        </template>
      </el-card>
      <!-- pip & 提交 -->
      <el-card shadow="never" class="form-card">
        <template #header>其他</template>
        <el-form-item label="pip_packages"><el-input v-model="form.pip_packages" placeholder="额外 pip 包，逗号分隔" /></el-form-item>
      </el-card>
      <div class="form-actions">
        <el-button @click="$router.back()">取消</el-button>
        <el-button :loading="saving" @click="saveTask">仅保存</el-button>
        <el-button type="primary" :loading="saving" @click="saveAndSubmit">保存并提交</el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { tasksApi, datasetsApi, algorithmsApi, modelsApi, resourcesApi } from '@/api'

const router = useRouter()
const formRef = ref()
const saving = ref(false)
const scriptSource = ref('path')
const loadingResources = ref(false)

// ===== 二级选择器数据 =====
const datasetGroups = ref([])
const datasetVersionsMap = ref({})
const selectedDatasetId = ref('')
const filteredDatasetVersions = computed(() => datasetVersionsMap.value[selectedDatasetId.value] || [])

const algorithmGroups = ref([])
const algorithmVersionsMap = ref({})
const selectedAlgorithmId = ref('')
const filteredAlgorithmVersions = computed(() => algorithmVersionsMap.value[selectedAlgorithmId.value] || [])

const modelGroups = ref([])
const modelVersionsMap = ref({})
const selectedModelId = ref('')
const filteredModelVersions = computed(() => modelVersionsMap.value[selectedModelId.value] || [])

// 扁平列表 for pipeline
const allAlgorithmVersions = ref([])
const allModelVersions = ref([])

// 动态参数
const algoParams = ref([])

// 计算资源
const computeResources = ref([])
const nodeDetails = ref([])   // Per-node details from API
const availableNodeCount = ref(0)
const canDistributed = computed(() => availableNodeCount.value >= 2)

// 流水线
const pipelineEnabled = ref(false)
const pipelineStages = ref([
  { name: '阶段1', enabled: true, algorithm_version_id: '', model_version_id: '', config: { epochs: 10, batch_size: 32, learning_rate: 0.001 } },
  { name: '阶段2', enabled: true, algorithm_version_id: '', model_version_id: '', config: { epochs: 5, batch_size: 32, learning_rate: 0.0001 } },
])

const form = reactive({
  name: '', description: '', priority: 5, execution_mode: 'auto',
  training_script: '', script_content: '', algorithm_version_id: '',
  dataset_version_id: '', model_version_id: '',
  parallel_mode: 'single', num_nodes: 1, gpus_per_node: 0, nproc_per_node: 2,
  compute_resource: 'cpu',
  cpu_request: '1', cpu_limit: '4', memory_request: '4Gi', memory_limit: '8Gi',
  pip_packages: '', max_retries: 3,
  configObj: {},
})

const rules = {
  name: [{ required: true, message: '任务名称不能为空', trigger: 'blur' }],
  training_script: [{ required: true, message: '训练脚本不能为空', trigger: 'blur' }],
}

// ===== 二级选择器事件 =====
function onDatasetGroupChange(id) {
  form.dataset_version_id = ''
  if (!id) return
  if (!datasetVersionsMap.value[id]) loadDatasetVersions(id)
}
function onAlgorithmGroupChange(id) {
  form.algorithm_version_id = ''
  algoParams.value = []
  form.configObj = {}
  if (!id) return
  if (!algorithmVersionsMap.value[id]) loadAlgorithmVersions(id)
}
function onModelGroupChange(id) {
  form.model_version_id = ''
  if (!id) return
  if (!modelVersionsMap.value[id]) loadModelVersions(id)
}

async function onAlgorithmVersionChange(versionId) {
  algoParams.value = []
  form.configObj = {}
  if (!versionId) return
  try {
    const res = await algorithmsApi.getVersion(versionId)
    const ver = res.data.data
    if (ver.script_path) form.training_script = ver.script_path
    const params = ver.parameters || []
    algoParams.value = params
    const obj = {}
    params.forEach(p => { obj[p.name] = p.default_value ?? null })
    form.configObj = obj
  } catch {}
}

// ===== 脚本来源 =====
function onScriptSourceCmd(cmd) { scriptSource.value = cmd; if (cmd === 'path') form.script_content = '' }
function handleScriptUpload(file) {
  const reader = new FileReader()
  reader.onload = e => { form.script_content = e.target.result; form.training_script = file.name }
  reader.readAsText(file.raw)
}
function handleScriptRemove() { form.script_content = '' }

// ===== 训练模式 =====
function onParallelModeChange(val) {
  if (val === 'single') { form.num_nodes = 1; form.gpus_per_node = 0 }
  else if (val === 'local_ddp') { form.num_nodes = 1 }
  else if (val === 'distributed') { form.num_nodes = 2 }
}

// ===== 参数清空 =====
function clearConfig() {
  const obj = {}
  algoParams.value.forEach(p => { obj[p.name] = null })
  form.configObj = obj
}

// ===== 流水线 =====
function addStage() {
  pipelineStages.value.push({ name: `阶段${pipelineStages.value.length + 1}`, enabled: true, algorithm_version_id: '', model_version_id: '', config: { epochs: 5, batch_size: 32, learning_rate: 0.0001 } })
}
function removeStage(idx) { pipelineStages.value.splice(idx, 1) }

// ===== 构建提交数据 =====
function buildPayload() {
  const p = {
    name: form.name, description: form.description, priority: form.priority,
    execution_mode: form.execution_mode, training_script: form.training_script,
    script_content: form.script_content || undefined,
    algorithm_version_id: form.algorithm_version_id || undefined,
    dataset_id: selectedDatasetId.value || undefined,
    dataset_version_id: form.dataset_version_id || undefined,
    model_version_id: form.model_version_id || undefined,
    parallel_mode: form.parallel_mode === 'local_ddp' ? 'ddp' : (form.parallel_mode === 'distributed' ? 'ddp' : form.parallel_mode),
    num_nodes: form.num_nodes, gpus_per_node: form.gpus_per_node,
    cpu_request: form.cpu_request, cpu_limit: form.cpu_limit,
    memory_request: form.memory_request, memory_limit: form.memory_limit,
    pip_packages: form.pip_packages, max_retries: form.max_retries,
  }
  // Build training_args from configObj (filter nulls)
  const args = {}
  Object.entries(form.configObj).forEach(([k, v]) => { if (v != null && v !== '') args[k] = v })
  if (Object.keys(args).length > 0) p.training_args = args
  // total_epochs from config
  if (args.epochs) p.total_epochs = args.epochs
  // nproc_per_node for local_ddp
  if (form.parallel_mode === 'local_ddp') {
    p.training_args = { ...(p.training_args || {}), nproc_per_node: form.nproc_per_node }
  }
  // pipeline
  if (pipelineEnabled.value) {
    p.pipeline_stages = pipelineStages.value.filter(s => s.enabled).map(s => ({
      name: s.name, algorithm_version_id: s.algorithm_version_id,
      model_version_id: s.model_version_id || undefined, config: s.config,
    }))
  }
  return p
}

async function saveTask() {
  await formRef.value.validate()
  saving.value = true
  try {
    const res = await tasksApi.create(buildPayload())
    ElMessage.success('任务已创建')
    router.push(`/tasks/${res.data.data.id}`)
  } finally { saving.value = false }
}

async function saveAndSubmit() {
  await formRef.value.validate()
  saving.value = true
  try {
    const res = await tasksApi.create(buildPayload())
    await tasksApi.submit(res.data.data.id)
    ElMessage.success('任务已创建并提交')
    router.push(`/tasks/${res.data.data.id}`)
  } finally { saving.value = false }
}

// ===== 数据加载 =====
async function loadDatasetVersions(dsId) {
  try {
    const res = await datasetsApi.versions(dsId)
    datasetVersionsMap.value[dsId] = res.data.data || []
  } catch {}
}

async function loadAlgorithmVersions(algoId) {
  try {
    const res = await algorithmsApi.versions(algoId)
    const vers = res.data.data || []
    algorithmVersionsMap.value[algoId] = vers
    const algo = algorithmGroups.value.find(a => a.id === algoId)
    vers.forEach(v => {
      if (!allAlgorithmVersions.value.find(x => x.id === v.id)) {
        allAlgorithmVersions.value.push({ ...v, algorithm_name: algo?.name || '' })
      }
    })
  } catch {}
}

async function loadModelVersions(modelId) {
  try {
    const res = await modelsApi.versions(modelId)
    const vers = res.data.data || []
    modelVersionsMap.value[modelId] = vers
    const model = modelGroups.value.find(m => m.id === modelId)
    vers.forEach(v => {
      if (!allModelVersions.value.find(x => x.id === v.id)) {
        allModelVersions.value.push({ ...v, model_name: model?.name || '' })
      }
    })
  } catch {}
}

async function refreshResources() {
  loadingResources.value = true
  try {
    const res = await resourcesApi.computeResources()
    const data = res.data.data || {}
    const summary = data.summary || {}
    availableNodeCount.value = summary.online_nodes || 0
    const resList = data.resources || []
    computeResources.value = resList.length > 0 ? resList : []
    // Per-node details for FTv1-style display
    const nodes = data.node_details || []
    nodeDetails.value = nodes
    // Auto-select first node if none selected
    if (nodes.length > 0 && !form.compute_resource) {
      form.compute_resource = nodes[0].id
    }
  } catch {
    computeResources.value = []
    nodeDetails.value = []
    availableNodeCount.value = 0
  } finally { loadingResources.value = false }
}

async function loadGroups() {
  try {
    const [dRes, aRes, mRes] = await Promise.all([
      datasetsApi.list({ per_page: 200 }),
      algorithmsApi.list({ per_page: 200 }),
      modelsApi.list({ per_page: 200 }),
    ])
    datasetGroups.value = dRes.data.data?.items || []
    algorithmGroups.value = aRes.data.data?.items || []
    modelGroups.value = mRes.data.data?.items || []
  } catch {}
}

onMounted(() => {
  loadGroups()
  refreshResources()
})
</script>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-left { display: flex; align-items: center; gap: 12px; }
.header-left h1 { font-size: 22px; font-weight: 700; color: #2c3e50; margin: 0; }
.form-card { margin-bottom: 0; }
.form-actions { display: flex; justify-content: flex-end; gap: 12px; padding: 16px 0; }
.script-upload { width: 100%; }
.script-upload :deep(.el-upload-dragger) { width: 100%; padding: 30px 20px; }

/* Two-line option */
.opt2 { display: flex; flex-direction: column; padding: 2px 0; line-height: 1.4; }
.opt-m { font-weight: 600; font-size: 14px; color: #303133; }
.opt-s { font-size: 12px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Card header flex */
.chf { display: flex; justify-content: space-between; align-items: center; }

/* Config tip */
.config-tip { font-size: 13px; color: #909399; margin-bottom: 12px; display: flex; align-items: center; gap: 6px; }

/* Parameter grid */
.param-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 16px; }
.param-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
.pr-label { display: flex; flex-direction: column; min-width: 120px; }
.pr-name { font-size: 13px; font-weight: 600; color: #303133; }
.pr-code { font-size: 11px; color: #909399; font-family: monospace; }
.pr-input { flex: 1; min-width: 0; }

/* Resource selector */
.resource-selector { display: flex; flex-direction: column; gap: 8px; }
.res-opt { display: inline-flex; align-items: center; gap: 6px; }
.node-radio-group { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.node-radio-item { border: 1px solid #ebeef5; border-radius: 8px; padding: 10px 14px; width: 100%; margin-right: 0 !important; transition: border-color 0.2s; }
.node-radio-item:hover { border-color: #409EFF; }
.node-radio-item.is-checked { border-color: #409EFF; background: #ecf5ff; }
.node-detail-opt { display: flex; flex-direction: column; gap: 4px; }
.node-badges { display: flex; gap: 6px; }
.node-info-line { display: flex; gap: 12px; font-size: 13px; color: #303133; font-weight: 500; }
.node-spec { white-space: nowrap; }
.node-host { font-size: 12px; color: #909399; }
.resource-summary { display: flex; align-items: center; margin-top: 4px; }

/* Training mode */
.mode-params { display: flex; align-items: center; gap: 12px; margin-top: 8px; font-size: 13px; color: #606266; }
.node-hint { font-size: 12px; margin-top: 6px; }

/* Pipeline */
.pipe-stage { border: 1px solid #ebeef5; border-radius: 6px; padding: 12px; margin-top: 12px; }
.ps-head { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.ph { font-size: 11px; color: #909399; text-align: center; margin-top: 2px; }
</style>
