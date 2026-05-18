import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('kt_token') || null)
  const user = ref(JSON.parse(localStorage.getItem('kt_user') || 'null'))

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username, password) {
    const res = await api.post('/auth/login', { username, password })
    token.value = res.data.data.access_token
    user.value = res.data.data.user
    localStorage.setItem('kt_token', token.value)
    localStorage.setItem('kt_user', JSON.stringify(user.value))
    return res.data.data
  }

  async function logout() {
    try { await api.post('/auth/logout') } catch {}
    token.value = null
    user.value = null
    localStorage.removeItem('kt_token')
    localStorage.removeItem('kt_user')
  }

  async function fetchProfile() {
    const res = await api.get('/auth/me')
    user.value = res.data.data
    localStorage.setItem('kt_user', JSON.stringify(user.value))
    return user.value
  }

  return { token, user, isLoggedIn, isAdmin, login, logout, fetchProfile }
})
