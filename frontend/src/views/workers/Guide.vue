<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <el-button link @click="$router.push('/workers')"><el-icon><arrow-left /></el-icon> 返回节点</el-button>
        <h1>Agent 节点注册引导</h1>
      </div>
    </div>

    <el-steps :active="step" finish-status="success" align-center class="steps">
      <el-step title="连通性测试" />
      <el-step title="安装 Agent" />
      <el-step title="注册节点" />
      <el-step title="完成" />
    </el-steps>

    <el-card shadow="never" class="step-card">
      <!-- Step 1: 连通性测试 -->
      <div v-if="step === 0">
        <h3>步骤 1: 测试节点连通性</h3>
        <p class="desc">输入目标服务器的 IP 地址和端口，测试网络连通性。</p>
        <el-form :model="form" label-width="100px" style="max-width:500px">
          <el-form-item label="IP 地址">
            <el-input v-model="form.ip_address" placeholder="例如: 192.168.1.100" />
          </el-form-item>
          <el-form-item label="端口">
            <el-input-number v-model="form.port" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="testConnection" :loading="testing">
              <el-icon><connection /></el-icon> 测试连通性
            </el-button>
          </el-form-item>
        </el-form>

        <el-result v-if="pingResult" :icon="pingResult.reachable ? 'success' : 'error'"
          :title="pingResult.reachable ? '端口可达' : '端口不可达'"
          :sub-title="pingResult.message">
          <template #extra>
            <div v-if="pingResult.agent_ok" class="agent-info">
              <el-tag type="success">Agent 已运行</el-tag>
              <span v-if="pingResult.agent_info?.hostname">主机名: {{ pingResult.agent_info.hostname }}</span>
            </div>
            <el-button v-if="pingResult.reachable" type="primary" @click="step = pingResult.agent_ok ? 2 : 1">
              {{ pingResult.agent_ok ? '直接注册' : '下一步: 安装 Agent' }}
            </el-button>
          </template>
        </el-result>
      </div>

      <!-- Step 2: 安装 Agent -->
      <div v-if="step === 1">
        <h3>步骤 2: 安装 Agent</h3>
        <p class="desc">在目标服务器上执行以下命令安装 KubeTrain Agent。</p>
        
        <el-tabs v-model="installMethod">
          <el-tab-pane label="一键安装" name="auto">
            <div class="code-block">
              <code>curl -sSL {{ serverUrl }}/api/workers/install-script | bash</code>
              <el-button size="small" @click="copyScript" class="copy-btn">
                <el-icon><document-copy /></el-icon>
              </el-button>
            </div>
            <el-alert type="info" :closable="false" style="margin-top:12px">
              此脚本将自动安装 Python 虚拟环境、依赖包和 Agent 程序。
            </el-alert>
          </el-tab-pane>
          
          <el-tab-pane label="手动安装" name="manual">
            <ol class="manual-steps">
              <li>
                <strong>安装依赖</strong>
                <div class="code-block"><code>pip install flask requests psutil</code></div>
              </li>
              <li>
                <strong>下载 Agent 脚本</strong>
                <div class="code-block"><code>wget {{ serverUrl }}/api/workers/install-script -O install.sh && bash install.sh</code></div>
              </li>
              <li>
                <strong>启动 Agent</strong>
                <div class="code-block"><code>KUBETRAIN_SERVER={{ serverUrl }} python agent.py</code></div>
              </li>
            </ol>
          </el-tab-pane>
          
          <el-tab-pane label="Docker 安装" name="docker">
            <div class="code-block">
              <code>docker run -d --name kubetrain-agent \
  --gpus all \
  -e KUBETRAIN_SERVER={{ serverUrl }} \
  -p 5000:5000 \
  kubetrain/agent:latest</code>
            </div>
            <el-alert type="warning" :closable="false" style="margin-top:12px">
              使用 Docker 需要安装 nvidia-docker 以支持 GPU。
            </el-alert>
          </el-tab-pane>
        </el-tabs>

        <div class="step-actions">
          <el-button @click="step = 0">上一步</el-button>
          <el-button type="primary" @click="step = 2">下一步: 注册节点</el-button>
        </div>
      </div>

      <!-- Step 3: 注册节点 -->
      <div v-if="step === 2">
        <h3>步骤 3: 注册节点</h3>
        <p class="desc">填写节点信息并注册到系统。</p>
        
        <el-form :model="form" label-width="120px" style="max-width:600px">
          <el-form-item label="节点名称">
            <el-input v-model="form.name" placeholder="例如: GPU-Server-01" />
          </el-form-item>
          <el-form-item label="IP 地址">
            <el-input v-model="form.ip_address" />
          </el-form-item>
          <el-form-item label="端口">
            <el-input-number v-model="form.port" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item label="GPU 数量">
            <el-input-number v-model="form.gpu_total" :min="0" :max="16" />
          </el-form-item>
          <el-form-item label="GPU 型号">
            <el-input v-model="form.gpu_model" placeholder="例如: NVIDIA A100" />
          </el-form-item>
          <el-form-item label="CPU 核心数">
            <el-input-number v-model="form.cpu_total" :min="1" :max="256" />
          </el-form-item>
          <el-form-item label="内存 (GB)">
            <el-input-number v-model="form.memory_total" :min="1" :max="2048" />
          </el-form-item>
          <el-form-item label="最大并行任务">
            <el-input-number v-model="form.max_tasks" :min="1" :max="32" />
          </el-form-item>
          <el-form-item label="节点池">
            <el-select v-model="form.pool_id" placeholder="选择节点池" clearable>
              <el-option v-for="p in pools" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
        </el-form>

        <div class="step-actions">
          <el-button @click="step = 1">上一步</el-button>
          <el-button type="primary" @click="registerNode" :loading="registering">注册节点</el-button>
        </div>
      </div>

      <!-- Step 4: 完成 -->
      <div v-if="step === 3">
        <el-result icon="success" title="注册成功" sub-title="Agent 节点已成功注册到系统">
          <template #extra>
            <div v-if="registeredNode" class="registered-info">
              <el-descriptions :column="2" border size="small">
                <el-descriptions-item label="节点 ID">{{ registeredNode.id }}</el-descriptions-item>
                <el-descriptions-item label="名称">{{ registeredNode.name }}</el-descriptions-item>
                <el-descriptions-item label="IP">{{ registeredNode.ip_address }}</el-descriptions-item>
                <el-descriptions-item label="状态">
                  <el-tag :type="registeredNode.status === 'online' ? 'success' : 'info'">{{ registeredNode.status }}</el-tag>
                </el-descriptions-item>
              </el-descriptions>
            </div>
            <div style="margin-top:20px">
              <el-button @click="resetGuide">注册另一个节点</el-button>
              <el-button type="primary" @click="$router.push('/workers')">查看节点列表</el-button>
            </div>
          </template>
        </el-result>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { workersApi, nodePoolsApi } from '@/api'

const step = ref(0)
const testing = ref(false)
const registering = ref(false)
const pingResult = ref(null)
const registeredNode = ref(null)
const pools = ref([])
const installMethod = ref('auto')

const form = reactive({
  name: '',
  ip_address: '',
  port: 5000,
  gpu_total: 1,
  gpu_model: '',
  cpu_total: 8,
  memory_total: 32,
  max_tasks: 1,
  pool_id: null
})

const serverUrl = window.location.origin

async function testConnection() {
  if (!form.ip_address) {
    ElMessage.warning('请输入 IP 地址')
    return
  }
  testing.value = true
  pingResult.value = null
  try {
    const res = await workersApi.ping({ ip_address: form.ip_address, port: form.port })
    pingResult.value = res.data.data
    if (pingResult.value.agent_info) {
      form.name = pingResult.value.agent_info.hostname || form.ip_address
    }
  } catch (e) {
    ElMessage.error('测试失败: ' + (e.response?.data?.message || e.message))
  } finally {
    testing.value = false
  }
}

async function registerNode() {
  if (!form.ip_address || !form.name) {
    ElMessage.warning('请填写必要信息')
    return
  }
  registering.value = true
  try {
    const res = await workersApi.adminRegister(form)
    registeredNode.value = res.data.data
    step.value = 3
    ElMessage.success('注册成功')
  } catch (e) {
    ElMessage.error('注册失败: ' + (e.response?.data?.message || e.message))
  } finally {
    registering.value = false
  }
}

function copyScript() {
  navigator.clipboard.writeText(`curl -sSL ${serverUrl}/api/workers/install-script | bash`)
  ElMessage.success('已复制到剪贴板')
}

function resetGuide() {
  step.value = 0
  pingResult.value = null
  registeredNode.value = null
  Object.assign(form, { name: '', ip_address: '', port: 5000, gpu_total: 1, gpu_model: '', cpu_total: 8, memory_total: 32, max_tasks: 1, pool_id: null })
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
.page-container { display: flex; flex-direction: column; gap: 20px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-left { display: flex; align-items: center; gap: 12px; }
.header-left h1 { font-size: 22px; font-weight: 700; color: #2c3e50; margin: 0; }
.steps { margin-bottom: 20px; }
.step-card { min-height: 400px; }
.step-card h3 { margin: 0 0 8px; font-size: 18px; }
.desc { color: #666; margin-bottom: 20px; }
.code-block { background: #1e1e1e; color: #d4d4d4; padding: 12px 16px; border-radius: 6px; font-family: 'Cascadia Code', monospace; font-size: 13px; position: relative; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
.copy-btn { position: absolute; top: 8px; right: 8px; }
.manual-steps { padding-left: 20px; }
.manual-steps li { margin-bottom: 16px; }
.manual-steps .code-block { margin-top: 8px; }
.step-actions { margin-top: 24px; display: flex; gap: 12px; }
.agent-info { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.registered-info { margin-bottom: 16px; }
</style>
