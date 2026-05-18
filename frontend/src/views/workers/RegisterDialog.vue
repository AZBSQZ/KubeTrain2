<template>
  <el-dialog v-model="visible" title="注册计算节点" width="680px" destroy-on-close @close="$emit('close')">
    <!-- 步骤1: 下载 Agent -->
    <div class="step-section">
      <h4>步骤1：下载 Agent 脚本到目标计算节点</h4>
      <el-button type="primary" class="download-btn" @click="downloadAgent">
        下载 te_agent.py
      </el-button>
      <p class="hint">将脚本文件复制到目标计算节点（需要 Python 3.6+ 和 requests 库）</p>
    </div>

    <!-- 步骤2: 执行注册命令 -->
    <div class="step-section">
      <h4>步骤2：在目标节点上执行注册命令</h4>
      <div class="os-tabs">
        <span class="label">目标系统：</span>
        <el-radio-group v-model="osType" size="small">
          <el-radio-button label="linux">Linux</el-radio-button>
          <el-radio-button label="windows">Windows</el-radio-button>
          <el-radio-button label="macos">macOS</el-radio-button>
        </el-radio-group>
      </div>

      <div class="cmd-block">
        <code>{{ installCmd }}</code>
        <el-button link class="copy-btn" @click="copyCmd(installCmd)">复制</el-button>
      </div>

      <p class="hint proxy-hint">无法连接 {{ serverPort }} 端口时，使用代理模式（通过前端端口转发）：</p>
      <div class="cmd-block">
        <code>{{ proxyCmd }}</code>
        <el-button link class="copy-btn" @click="copyCmd(proxyCmd)">复制</el-button>
      </div>

      <!-- 指定节点池 -->
      <div class="pool-section" v-if="pools.length > 0">
        <p class="hint">指定节点池（可选）：</p>
        <div v-for="pool in pools" :key="pool.id" class="cmd-block pool-cmd">
          <code>{{ getPoolCmd(pool) }}</code>
          <span class="pool-tag">→ {{ pool.name }}</span>
        </div>
      </div>
    </div>

    <!-- 步骤3: 验证注册 -->
    <div class="step-section">
      <h4>步骤3：验证节点注册成功</h4>
      <el-button @click="$emit('refresh')" style="width:100%">刷新节点列表</el-button>
      <p class="hint center">Agent 启动后节点会自动出现在列表中，状态为「空闲」</p>
    </div>

    <!-- 手动注册折叠面板 -->
    <el-collapse class="manual-collapse">
      <el-collapse-item title="手动注册（仅测试用，不推荐）">
        <el-form :model="manualForm" label-width="100px" size="small">
          <el-form-item label="节点名称">
            <el-input v-model="manualForm.name" placeholder="例如: GPU-Server-01" />
          </el-form-item>
          <el-form-item label="IP 地址">
            <el-input v-model="manualForm.ip_address" placeholder="192.168.1.100" />
          </el-form-item>
          <el-form-item label="端口">
            <el-input-number v-model="manualForm.port" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item label="GPU 数量">
            <el-input-number v-model="manualForm.gpu_total" :min="0" />
          </el-form-item>
          <el-form-item label="节点池">
            <el-select v-model="manualForm.pool_id" placeholder="默认池" clearable style="width:100%">
              <el-option v-for="p in pools" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="manualRegister" :loading="registering">注册</el-button>
          </el-form-item>
        </el-form>
      </el-collapse-item>
    </el-collapse>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { workersApi, nodePoolsApi } from '@/api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'close', 'refresh'])

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const osType = ref('linux')
const pools = ref([])
const registering = ref(false)

const manualForm = reactive({
  name: '', ip_address: '', port: 5000, gpu_total: 0, pool_id: null
})

const serverHost = window.location.hostname
const serverPort = '8010'
const frontendPort = window.location.port || '80'

const installCmd = computed(() => {
  if (osType.value === 'windows') {
    return `pip install requests && python te_agent.py --server http://${serverHost}:${serverPort}`
  }
  return `pip3 install requests && python3 te_agent.py --server http://${serverHost}:${serverPort}`
})

const proxyCmd = computed(() => {
  const py = osType.value === 'windows' ? 'python' : 'python3'
  return `${py} te_agent.py --server http://${serverHost}:${frontendPort} --proxy`
})

function getPoolCmd(pool) {
  const py = osType.value === 'windows' ? 'python' : 'python3'
  return `${py} te_agent.py --server http://${serverHost}:${serverPort} --pool-id ${pool.id}`
}

function downloadAgent() {
  window.open(`/api/workers/agent-download`, '_blank')
}

function copyCmd(cmd) {
  navigator.clipboard.writeText(cmd)
  ElMessage.success('已复制')
}

async function manualRegister() {
  if (!manualForm.ip_address) {
    ElMessage.warning('请输入 IP 地址')
    return
  }
  registering.value = true
  try {
    await workersApi.adminRegister({
      ...manualForm,
      name: manualForm.name || manualForm.ip_address
    })
    ElMessage.success('注册成功')
    emit('refresh')
    visible.value = false
  } catch (e) {
    ElMessage.error('注册失败: ' + (e.response?.data?.message || e.message))
  } finally {
    registering.value = false
  }
}

async function loadPools() {
  try {
    const res = await nodePoolsApi.list()
    pools.value = res.data.data || []
  } catch {}
}

onMounted(loadPools)
</script>

<style scoped>
.step-section { margin-bottom: 24px; }
.step-section h4 { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 12px; }
.download-btn { width: 100%; height: 40px; font-size: 15px; }
.hint { font-size: 12px; color: #909399; margin: 8px 0 0; }
.hint.center { text-align: center; }
.hint.proxy-hint { margin-top: 16px; }
.os-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.os-tabs .label { font-size: 13px; color: #606266; }
.cmd-block {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 10px 14px;
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
  color: #303133;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.cmd-block code { flex: 1; word-break: break-all; }
.copy-btn { color: #409eff; font-size: 13px; }
.pool-section { margin-top: 16px; }
.pool-cmd { margin-bottom: 6px; }
.pool-tag { font-size: 12px; color: #909399; margin-left: 12px; white-space: nowrap; }
.manual-collapse { margin-top: 16px; }
.manual-collapse :deep(.el-collapse-item__header) { font-size: 13px; color: #606266; }
</style>
