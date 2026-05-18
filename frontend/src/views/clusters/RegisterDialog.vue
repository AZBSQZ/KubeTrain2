<template>
  <el-dialog v-model="visible" title="注册K8s集群" width="560px" destroy-on-close @close="$emit('close')">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="集群名称" prop="name">
        <el-input v-model="form.name" placeholder="如: production-cluster" />
      </el-form-item>
      <el-form-item label="API Server" prop="api_server">
        <el-input v-model="form.api_server" placeholder="如: https://192.168.1.100:6443" />
      </el-form-item>
      <el-form-item label="命名空间">
        <el-input v-model="form.namespace" placeholder="default" />
      </el-form-item>
      <el-form-item label="认证方式">
        <el-radio-group v-model="form.auth_type">
          <el-radio label="kubeconfig">Kubeconfig</el-radio>
          <el-radio label="token">Bearer Token</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.auth_type === 'kubeconfig'" label="Kubeconfig" prop="kubeconfig">
        <el-input
          v-model="form.kubeconfig"
          type="textarea"
          :rows="8"
          placeholder="粘贴 kubeconfig 内容（YAML格式）"
          style="font-family: 'Cascadia Code', monospace; font-size: 12px;"
        />
      </el-form-item>
      <el-form-item v-if="form.auth_type === 'token'" label="Token" prop="token">
        <el-input
          v-model="form.token"
          type="textarea"
          :rows="4"
          placeholder="粘贴 Bearer Token"
          style="font-family: 'Cascadia Code', monospace; font-size: 12px;"
        />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitting">注册</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { clustersApi } from '@/api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'close', 'success'])

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v)
})

const formRef = ref()
const submitting = ref(false)

const form = reactive({
  name: '',
  api_server: '',
  namespace: 'default',
  auth_type: 'kubeconfig',
  kubeconfig: '',
  token: '',
  description: ''
})

const rules = {
  name: [{ required: true, message: '请输入集群名称', trigger: 'blur' }],
  api_server: [{ required: true, message: '请输入 API Server 地址', trigger: 'blur' }],
  kubeconfig: [{ required: true, message: '请粘贴 kubeconfig 内容', trigger: 'blur' }],
  token: [{ required: true, message: '请粘贴 Token', trigger: 'blur' }]
}

async function handleSubmit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    const payload = {
      name: form.name,
      api_server: form.api_server,
      namespace: form.namespace || 'default',
      auth_type: form.auth_type,
      description: form.description
    }
    if (form.auth_type === 'kubeconfig') {
      payload.kubeconfig = form.kubeconfig
    } else {
      payload.token = form.token
    }
    await clustersApi.create(payload)
    ElMessage.success('集群注册成功')
    emit('success')
    visible.value = false
  } catch (e) {
    ElMessage.error('注册失败: ' + (e.response?.data?.message || e.message))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
:deep(.el-form-item__label) {
  font-weight: 500;
}
</style>
