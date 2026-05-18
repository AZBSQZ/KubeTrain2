<template>
  <div class="login-container">
    <div class="tech-bg">
      <div class="tech-grid"></div>
      <div class="tech-particles"></div>
      <div class="bubbles">
        <span v-for="i in 12" :key="i" :style="getBubbleStyle(i)"></span>
      </div>
      <div class="light-rays"></div>
    </div>

    <div class="login-content">
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
              <p>支持 DDP / FSDP 多节点并行训练，弹性扩缩容</p>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon"><el-icon size="28"><monitor /></el-icon></div>
            <div class="feature-content">
              <h3>实时监控</h3>
              <p>实时日志流、Loss/Accuracy 曲线可视化</p>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon"><el-icon size="28"><cpu /></el-icon></div>
            <div class="feature-content">
              <h3>资源调度</h3>
              <p>GPU / CPU 资源池化管理，智能任务调度</p>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon"><el-icon size="28"><box /></el-icon></div>
            <div class="feature-content">
              <h3>模型仓库</h3>
              <p>训练产物自动归档，版本化模型管理</p>
            </div>
          </div>
        </div>
      </div>

      <div class="login-box">
        <div class="login-header">
          <h2>欢迎登录</h2>
          <p class="login-subtitle">请输入您的账号信息</p>
        </div>
        <el-form ref="formRef" :model="form" :rules="rules" label-width="0" class="login-form">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="请输入用户名" prefix-icon="User"
              size="large" clearable />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="请输入密码"
              prefix-icon="Lock" size="large" show-password clearable @keyup.enter="handleLogin" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" :loading="loading" @click="handleLogin" class="login-btn">
              <span v-if="!loading">登 录</span>
              <span v-else>登录中...</span>
            </el-button>
          </el-form-item>
        </el-form>
        <div class="login-actions">
          <el-link type="primary" @click="$router.push('/register')">注册账号</el-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function handleLogin() {
  try { await formRef.value.validate() } catch { return }
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '登录失败，请检查用户名和密码')
  } finally {
    loading.value = false
  }
}

const getBubbleStyle = (i) => {
  const sizes = [30, 50, 20, 70, 40, 25, 60, 35, 45, 55, 28, 65]
  const lefts = [5, 15, 25, 35, 45, 55, 65, 75, 85, 10, 50, 80]
  const durations = [12, 15, 10, 18, 13, 11, 16, 14, 17, 12, 15, 13]
  const delays = [0, 2, 4, 1, 3, 5, 2, 4, 1, 3, 0, 2]
  const drifts = [40, -60, 30, -40, 50, -30, 60, -50, 20, -70, 45, -35]
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
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #e6f4ff 0%, #bae0ff 30%, #91caff 60%, #69b1ff 100%);
}
.tech-bg {
  position: absolute;
  width: 100%; height: 100%;
  overflow: hidden;
}
.tech-grid {
  position: absolute;
  width: 100%; height: 100%;
  background-image:
    linear-gradient(rgba(24,144,255,0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(24,144,255,0.08) 1px, transparent 1px);
  background-size: 60px 60px;
  animation: gridMove 25s linear infinite;
}
.tech-particles {
  position: absolute;
  width: 100%; height: 100%;
  background-image: radial-gradient(circle, rgba(255,255,255,0.4) 2px, transparent 2px);
  background-size: 80px 80px;
  animation: particleFloat 20s ease-in-out infinite;
}
.bubbles {
  position: absolute;
  width: 100%; height: 100%;
  overflow: hidden;
}
.bubbles span {
  position: absolute;
  bottom: -100px;
  background: radial-gradient(circle, rgba(255,255,255,0.6), rgba(24,144,255,0.3));
  border-radius: 50%;
  animation: bubbleRise linear infinite;
  box-shadow: 0 0 20px rgba(255,255,255,0.5);
}
.light-rays {
  position: absolute;
  width: 100%; height: 100%;
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

.login-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1300px;
  width: 90%;
  gap: 80px;
  position: relative;
  z-index: 1;
}
.system-info { flex: 1; color: #1890ff; }
.system-header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 12px;
}
.logo-wrapper {
  flex-shrink: 0;
  padding: 14px;
  background: rgba(255,255,255,0.2);
  backdrop-filter: blur(10px);
  border-radius: 50%;
  box-shadow: 0 8px 24px rgba(0,0,0,0.1);
}
.logo-icon { color: #1890ff; display: block; }
.system-title {
  font-size: 34px;
  font-weight: 700;
  margin: 0;
  color: #0958d9;
  text-shadow: 0 1px 2px rgba(255,255,255,0.6);
}
.system-subtitle {
  font-size: 15px;
  color: #096dd9;
  margin: 0 0 36px 78px;
  letter-spacing: 2px;
}
.features {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}
.feature-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 20px;
  background: rgba(255,255,255,0.18);
  backdrop-filter: blur(10px);
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.35);
  transition: all 0.3s;
}
.feature-item:hover {
  background: rgba(255,255,255,0.28);
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}
.feature-icon {
  flex-shrink: 0;
  width: 52px; height: 52px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,0.3);
  border-radius: 10px;
  color: #1890ff;
}
.feature-content h3 { font-size: 16px; font-weight: 600; margin: 0 0 6px; color: #0958d9; }
.feature-content p { font-size: 13px; color: #1d39c4; margin: 0; line-height: 1.6; }

.login-box {
  width: 420px;
  flex-shrink: 0;
  padding: 44px 40px;
  background: rgba(255,255,255,0.96);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.14), 0 0 0 1px rgba(24,144,255,0.15);
}
.login-header { text-align: center; margin-bottom: 32px; }
.login-header h2 { margin: 0 0 10px; color: #1890ff; font-size: 26px; font-weight: 600; }
.login-subtitle { color: #8c8c8c; font-size: 14px; margin: 0; }
.login-form :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #d9d9d9 inset;
  transition: all 0.3s;
}
.login-form :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #40a9ff inset; }
.login-form :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 2px #1890ff inset; }
.login-form :deep(.el-form-item) { margin-bottom: 22px; }
.login-btn {
  width: 100%; height: 44px;
  font-size: 16px; font-weight: 500;
  background: linear-gradient(135deg, #1890ff 0%, #096dd9 100%);
  border: none;
  box-shadow: 0 4px 12px rgba(24,144,255,0.4);
  transition: all 0.3s;
}
.login-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(24,144,255,0.5); }
.login-actions {
  display: flex;
  justify-content: center;
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid #f0f0f0;
}
</style>
