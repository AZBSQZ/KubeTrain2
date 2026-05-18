<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-info">
        <h1>个人设置</h1>
        <p>管理个人资料与安全设置</p>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>基本信息</template>
          <el-form ref="profileFormRef" :model="profileForm" :rules="profileRules" label-width="80px">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="profileForm.username" placeholder="3-50 个字符" clearable />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="profileForm.email" placeholder="可选" clearable />
            </el-form-item>
            <el-form-item label="角色">
              <el-tag :type="profileForm.role === 'admin' ? 'danger' : profileForm.role === 'guest' ? 'info' : ''">
                {{ { admin: '管理员', user: '普通用户', guest: '访客' }[profileForm.role] || profileForm.role }}
              </el-tag>
            </el-form-item>
            <el-form-item label="最后登录">
              <span class="info-text">{{ profileForm.last_login || '—' }}</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存修改</el-button>
              <el-button @click="loadProfile">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>修改密码</template>
          <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="100px">
            <el-form-item label="当前密码" prop="old_password">
              <el-input v-model="pwdForm.old_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="pwdForm.new_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm_password">
              <el-input v-model="pwdForm.confirm_password" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingPwd" @click="changePassword">修改密码</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const savingProfile = ref(false)
const savingPwd = ref(false)
const profileFormRef = ref()
const pwdFormRef = ref()

const profileForm = reactive({ username: '', email: '', role: '', last_login: '' })
const profileRules = {
  username: [
    { required: true, message: '用户名不能为空', trigger: 'blur' },
    { min: 3, max: 50, message: '长度在 3 到 50 个字符', trigger: 'blur' },
  ],
  email: [{ type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }],
}

const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const pwdRules = {
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [{ required: true, min: 6, message: '密码不少于6位', trigger: 'blur' }],
  confirm_password: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: (rule, val, cb) => val === pwdForm.new_password ? cb() : cb(new Error('两次密码不一致')), trigger: 'blur' }
  ]
}

function loadProfile() {
  const user = authStore.user || {}
  Object.assign(profileForm, {
    username: user.username || '',
    email: user.email || '',
    role: user.role || '',
    last_login: user.last_login || '',
  })
}

async function saveProfile() {
  await profileFormRef.value.validate()
  savingProfile.value = true
  try {
    const res = await authApi.updateProfile({ username: profileForm.username, email: profileForm.email })
    ElMessage.success('资料更新成功')
    if (res.data?.data) {
      authStore.user = { ...authStore.user, ...res.data.data }
      localStorage.setItem('kt_user', JSON.stringify(authStore.user))
    }
    await authStore.fetchProfile()
  } finally { savingProfile.value = false }
}

async function changePassword() {
  await pwdFormRef.value.validate()
  savingPwd.value = true
  try {
    await authApi.changePassword({ old_password: pwdForm.old_password, new_password: pwdForm.new_password })
    ElMessage.success('密码修改成功，请重新登录')
    Object.assign(pwdForm, { old_password: '', new_password: '', confirm_password: '' })
  } finally { savingPwd.value = false }
}

onMounted(loadProfile)
</script>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-info h1 { font-size: 24px; font-weight: 700; color: #2c3e50; margin: 0 0 6px; }
.header-info p { font-size: 14px; color: #64748b; margin: 0; }
.info-text { font-size: 13px; color: #595959; }
</style>
