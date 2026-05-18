<template>
  <div class="register-container">
    <div class="tech-bg">
      <div class="tech-grid"></div>
      <div class="tech-particles"></div>
      <div class="bubbles">
        <span v-for="i in 10" :key="i" :style="getBubbleStyle(i)"></span>
      </div>
      <div class="light-rays"></div>
    </div>

    <div class="register-content">
      <div class="system-info">
        <div class="system-header">
          <div class="logo-wrapper">
            <el-icon size="48" class="logo-icon"><cpu /></el-icon>
          </div>
          <h1 class="system-title">KubeTrain 2.0</h1>
        </div>
        <p class="system-subtitle">容器化分布式 AI 训练平台</p>
        <div class="features">
          <div class="feature-item">
            <div class="feature-icon"><el-icon size="28"><video-play /></el-icon></div>
            <div class="feature-content">
              <h3>分布式训练</h3>
              <p>支持 DDP / FSDP 多节点并行训练</p>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon"><el-icon size="28"><monitor /></el-icon></div>
            <div class="feature-content">
              <h3>实时监控</h3>
              <p>实时日志流与指标可视化</p>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon"><el-icon size="28"><cpu /></el-icon></div>
            <div class="feature-content">
              <h3>资源调度</h3>
              <p>GPU 资源池化管理与智能调度</p>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon"><el-icon size="28"><box /></el-icon></div>
            <div class="feature-content">
              <h3>模型仓库</h3>
              <p>训练产物自动归档，版本化管理</p>
            </div>
          </div>
        </div>
      </div>

      <div class="register-box">
        <div class="register-header">
          <h2>注册账号</h2>
          <p class="register-subtitle">加入 KubeTrain，开启智能训练之旅</p>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" label-width="0" class="register-form">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="请输入用户名（3-50 个字符）"
              prefix-icon="User" size="large" clearable />
          </el-form-item>
          <el-form-item prop="email">
            <el-input v-model="form.email" placeholder="请输入邮箱（可选）"
              prefix-icon="Message" size="large" clearable />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="请输入密码（至少 6 位）"
              prefix-icon="Lock" size="large" show-password clearable />
          </el-form-item>
          <el-form-item prop="confirm">
            <el-input v-model="form.confirm" type="password" placeholder="请再次输入密码"
              prefix-icon="Lock" size="large" show-password clearable @keyup.enter="handleRegister" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" :loading="loading" @click="handleRegister" class="register-btn">
              <span v-if="!loading">注 册</span>
              <span v-else>注册中...</span>
            </el-button>
          </el-form-item>
        </el-form>

        <div class="register-footer">
          <span>已有账号？</span>
          <el-link type="primary" @click="$router.push('/login')">立即登录</el-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api'

const router = useRouter()
const formRef = ref()
const loading = ref(false)

const form = reactive({ username: '', email: '', password: '', confirm: '' })

const validateConfirm = (rule, value, callback) => {
  if (!value) return callback(new Error('请再次输入密码'))
  if (value !== form.password) return callback(new Error('两次密码不一致'))
  callback()
}

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度在 3-50 个字符', trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' }
  ],
  confirm: [{ required: true, validator: validateConfirm, trigger: 'blur' }]
}

async function handleRegister() {
  try { await formRef.value.validate() } catch { return }
  loading.value = true
  try {
    const res = await authApi.register({
      username: form.username,
      email: form.email || undefined,
      password: form.password
    })
    if (res.data.code === 200) {
      ElMessage.success('注册成功，请登录')
      router.push('/login')
    } else {
      ElMessage.error(res.data.message || '注册失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '注册失败，请重试')
  } finally {
    loading.value = false
  }
}

const getBubbleStyle = (i) => {
  const sizes =     [25, 45, 18, 60, 35, 22, 50, 30, 40, 55]
  const lefts =     [8, 18, 30, 42, 55, 65, 72, 82, 90, 12]
  const durations = [11, 14, 9, 17, 12, 10, 15, 13, 16, 11]
  const delays =    [0, 3, 1, 4, 2, 5, 1, 3, 0, 2]
  const drifts =    [35, -55, 25, -45, 45, -25, 55, -40, 15, -65]
  const idx = i - 1
  return {
    width: `${sizes[idx]}px`, height: `${sizes[idx]}px`,
    left: `${lefts[idx]}%`,
    animationDuration: `${durations[idx]}s`,
    animationDelay: `${delays[idx]}s`,
    '--bubble-drift': `${drifts[idx]}px`
  }
}
</script>

<style scoped>
.register-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #e6f4ff 0%, #bae0ff 30%, #91caff 60%, #69b1ff 100%);
}
.tech-bg { position: absolute; width: 100%; height: 100%; overflow: hidden; }
.tech-grid {
  position: absolute; width: 100%; height: 100%;
  background-image:
    linear-gradient(rgba(24,144,255,0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(24,144,255,0.08) 1px, transparent 1px);
  background-size: 60px 60px;
  animation: gridMove 25s linear infinite;
}
.tech-particles {
  position: absolute; width: 100%; height: 100%;
  background-image: radial-gradient(circle, rgba(255,255,255,0.4) 2px, transparent 2px);
  background-size: 80px 80px;
  animation: particleFloat 20s ease-in-out infinite;
}
.bubbles { position: absolute; width: 100%; height: 100%; overflow: hidden; }
.bubbles span {
  position: absolute; bottom: -100px;
  background: radial-gradient(circle, rgba(255,255,255,0.6), rgba(24,144,255,0.3));
  border-radius: 50%;
  animation: bubbleRise linear infinite;
  box-shadow: 0 0 20px rgba(255,255,255,0.5);
}
.light-rays {
  position: absolute; width: 100%; height: 100%;
  background:
    radial-gradient(ellipse at 30% 20%, rgba(255,255,255,0.3) 0%, transparent 50%),
    radial-gradient(ellipse at 70% 80%, rgba(24,144,255,0.2) 0%, transparent 50%);
  animation: lightPulse 8s ease-in-out infinite;
}
@keyframes gridMove { 100% { transform: translate(60px,60px); } }
@keyframes particleFloat { 0%,100% { opacity:.4; transform:translateY(0); } 50% { opacity:.8; transform:translateY(-30px); } }
@keyframes bubbleRise {
  0% { bottom:-100px; opacity:0; transform:translateX(0) scale(0); }
  10% { opacity:1; transform:translateX(0) scale(1); }
  90% { opacity:1; }
  100% { bottom:110vh; opacity:0; transform:translateX(var(--bubble-drift)) scale(0.5); }
}
@keyframes lightPulse { 0%,100% { opacity:.5; } 50% { opacity:.8; } }

.register-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1300px;
  width: 90%;
  gap: 80px;
  position: relative;
  z-index: 1;
}
.system-info { flex: 1; }
.system-header { display: flex; align-items: center; gap: 20px; margin-bottom: 12px; }
.logo-wrapper {
  flex-shrink: 0; padding: 14px;
  background: rgba(255,255,255,0.2); backdrop-filter: blur(10px);
  border-radius: 50%; box-shadow: 0 8px 24px rgba(0,0,0,0.1);
}
.logo-icon { color: #1890ff; display: block; }
.system-title { font-size: 34px; font-weight: 700; margin: 0; color: #0958d9; text-shadow: 0 1px 2px rgba(255,255,255,0.6); }
.system-subtitle { font-size: 15px; color: #096dd9; margin: 0 0 36px 78px; letter-spacing: 2px; }
.features { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }
.feature-item {
  display: flex; align-items: flex-start; gap: 14px; padding: 20px;
  background: rgba(255,255,255,0.18); backdrop-filter: blur(10px);
  border-radius: 12px; border: 1px solid rgba(255,255,255,0.35); transition: all 0.3s;
}
.feature-item:hover { background: rgba(255,255,255,0.28); transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.12); }
.feature-icon {
  flex-shrink: 0; width: 52px; height: 52px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,0.3); border-radius: 10px; color: #1890ff;
}
.feature-content h3 { font-size: 16px; font-weight: 600; margin: 0 0 6px; color: #0958d9; }
.feature-content p { font-size: 13px; color: #1d39c4; margin: 0; line-height: 1.6; }

.register-box {
  width: 420px; flex-shrink: 0; padding: 40px;
  background: rgba(255,255,255,0.96); backdrop-filter: blur(10px);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.14), 0 0 0 1px rgba(24,144,255,0.15);
  max-height: 92vh; overflow-y: auto;
}
.register-header { text-align: center; margin-bottom: 28px; }
.register-header h2 { margin: 0 0 10px; color: #1890ff; font-size: 26px; font-weight: 600; }
.register-subtitle { color: #8c8c8c; font-size: 14px; margin: 0; }
.register-form :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #d9d9d9 inset; transition: all 0.3s; }
.register-form :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #40a9ff inset; }
.register-form :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 2px #1890ff inset; }
.register-form :deep(.el-form-item) { margin-bottom: 20px; }
.register-btn {
  width: 100%; height: 44px; font-size: 16px; font-weight: 500;
  background: linear-gradient(135deg, #1890ff 0%, #096dd9 100%);
  border: none; box-shadow: 0 4px 12px rgba(24,144,255,0.4); transition: all 0.3s;
}
.register-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(24,144,255,0.5); }
.register-footer {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  margin-top: 20px; padding-top: 18px; border-top: 1px solid #f0f0f0;
  color: #8c8c8c; font-size: 14px;
}
</style>
