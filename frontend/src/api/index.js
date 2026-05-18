import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('kt_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  res => res,
  err => {
    const status = err.response?.status
    const msg = err.response?.data?.message || err.message
    if (status === 401) {
      localStorage.removeItem('kt_token')
      localStorage.removeItem('kt_user')
      window.location.href = '/login'
    } else if (status !== 404) {
      ElMessage.error(msg || '请求失败')
    }
    return Promise.reject(err)
  }
)

export default api

export const authApi = {
  login: d => api.post('/auth/login', d),
  register: d => api.post('/auth/register', d),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  updateProfile: d => api.put('/auth/me/profile', d),
  changePassword: d => api.put('/auth/me/password', d),
  refresh: () => api.post('/auth/refresh'),
}

export const dashboardApi = {
  get: () => api.get('/dashboard'),
}

export const tasksApi = {
  list: p => api.get('/tasks', { params: p }),
  get: id => api.get(`/tasks/${id}`),
  create: d => api.post('/tasks', d),
  stats: () => api.get('/tasks/stats'),
  update: (id, d) => api.put(`/tasks/${id}`, d),
  delete: id => api.delete(`/tasks/${id}`),
  submit: id => api.post(`/tasks/${id}/submit`),
  cancel: id => api.post(`/tasks/${id}/cancel`),
  retry: id => api.post(`/tasks/${id}/retry`),
  stages: id => api.get(`/tasks/${id}/stages`),
  collectLogs: id => api.post(`/tasks/${id}/collect-logs`),
  logs: (id, p) => api.get(`/logs/tasks/${id}`, { params: p }),
  metrics: (id, p) => api.get(`/metrics/tasks/${id}`, { params: p }),
  metricsSummary: id => api.get(`/metrics/tasks/${id}/summary`),
  resourceStats: id => api.get(`/tasks/${id}/resource-stats`),
  clone: id => api.post(`/tasks/${id}/clone`),
  resultFiles: (id, p) => api.get(`/tasks/${id}/results/files`, { params: p }),
  downloadFile: (id, filename) => api.get(`/tasks/${id}/results/download/${filename}`, { responseType: 'blob' }),
  downloadAll: id => api.get(`/tasks/${id}/results/download-all`, { responseType: 'blob' }),
}

export const datasetsApi = {
  list: p => api.get('/datasets', { params: p }),
  get: id => api.get(`/datasets/${id}`),
  create: d => api.post('/datasets', d),
  update: (id, d) => api.put(`/datasets/${id}`, d),
  delete: id => api.delete(`/datasets/${id}`),
  upload: (id, formData, onProgress) => api.post(`/datasets/${id}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress
  }),
  versions: id => api.get(`/datasets/${id}/versions`),
  addVersion: (id, d) => api.post(`/datasets/${id}/versions`, d),
  download: id => `${api.defaults.baseURL}/datasets/${id}/download`,
  downloadVersion: (id, vId) => `${api.defaults.baseURL}/datasets/${id}/versions/${vId}/download`,
}

export const algorithmsApi = {
  list: p => api.get('/algorithms', { params: p }),
  get: id => api.get(`/algorithms/${id}`),
  create: d => api.post('/algorithms', d),
  createWithScript: formData => api.post('/algorithms', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  update: (id, d) => api.put(`/algorithms/${id}`, d),
  delete: id => api.delete(`/algorithms/${id}`),
  versions: id => api.get(`/algorithms/${id}/versions`),
  getVersion: vId => api.get(`/algorithms/versions/${vId}`),
  getVersionDetail: (algoId, vId) => api.get(`/algorithms/${algoId}/versions/${vId}`),
  addVersion: (id, d) => api.post(`/algorithms/${id}/versions`, d),
  addVersionWithFile: (id, formData) => api.post(`/algorithms/${id}/versions`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
}

export const modelsApi = {
  list: p => api.get('/models', { params: p }),
  get: id => api.get(`/models/${id}`),
  create: d => api.post('/models', d),
  createWithFile: formData => api.post('/models', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  update: (id, d) => api.put(`/models/${id}`, d),
  delete: id => api.delete(`/models/${id}`),
  versions: id => api.get(`/models/${id}/versions`),
  setProduction: (id, vId) => api.post(`/models/${id}/versions/${vId}/production`),
  fromTask: (taskId, d) => api.post(`/models/from-task/${taskId}`, d),
  download: id => `${api.defaults.baseURL}/models/${id}/download`,
  downloadVersion: (id, vId) => `${api.defaults.baseURL}/models/${id}/versions/${vId}/download`,
}

export const resourcesApi = {
  overview: () => api.get('/resources/overview'),
  nodes: p => api.get('/resources/nodes', { params: p }),
  quotas: () => api.get('/resources/quotas'),
  createQuota: d => api.post('/resources/quotas', d),
  updateQuota: (id, d) => api.put(`/resources/quotas/${id}`, d),
  deleteQuota: id => api.delete(`/resources/quotas/${id}`),
  allocations: p => api.get('/resources/allocations', { params: p }),
  computeResources: () => api.get('/resources/compute-resources'),
}

export const nodePoolsApi = {
  list: () => api.get('/node-pools'),
  get: id => api.get(`/node-pools/${id}`),
  create: d => api.post('/node-pools', d),
  update: (id, d) => api.put(`/node-pools/${id}`, d),
  delete: id => api.delete(`/node-pools/${id}`),
  addNode: (id, d) => api.post(`/node-pools/${id}/nodes`, d),
  removeNode: (poolId, nodeId) => api.delete(`/node-pools/${poolId}/nodes/${nodeId}`),
}

export const clustersApi = {
  list: () => api.get('/clusters'),
  get: id => api.get(`/clusters/${id}`),
  create: d => api.post('/clusters', d),
  update: (id, d) => api.put(`/clusters/${id}`, d),
  delete: id => api.delete(`/clusters/${id}`),
  test: id => api.post(`/clusters/${id}/test`),
}

export const alertsApi = {
  list: p => api.get('/alerts', { params: p }),
  activeCount: () => api.get('/alerts/active/count'),
  acknowledge: id => api.post(`/alerts/${id}/acknowledge`),
  resolve: (id, d) => api.post(`/alerts/${id}/resolve`, d),
  rules: () => api.get('/alerts/rules'),
  createRule: d => api.post('/alerts/rules', d),
  updateRule: (id, d) => api.put(`/alerts/rules/${id}`, d),
  deleteRule: id => api.delete(`/alerts/rules/${id}`),
}

export const workersApi = {
  list: () => api.get('/workers'),
  get: id => api.get(`/workers/${id}`),
  adminRegister: d => api.post('/workers/admin-register', d),
  update: (id, d) => api.put(`/workers/${id}`, d),
  deregister: id => api.post(`/workers/${id}/deregister`),
  ping: d => api.post('/workers/ping', d),
  installScript: () => `${api.defaults.baseURL}/workers/install-script`,
  status: p => api.get('/workers/status', { params: p }),
  stats: () => api.get('/workers/stats'),
  discover: p => api.get('/workers/discover', { params: p }),
  findBest: d => api.post('/workers/find-best', d),
}

export const usersApi = {
  list: p => api.get('/users', { params: p }),
  get: id => api.get(`/users/${id}`),
  create: d => api.post('/users', d),
  update: (id, d) => api.put(`/users/${id}`, d),
  delete: id => api.delete(`/users/${id}`),
  setQuota: (id, d) => api.put(`/users/${id}/quota`, d),
}

export const modelGroupsApi = {
  list: p => api.get('/model-groups', { params: p }),
  get: id => api.get(`/model-groups/${id}`),
  create: d => api.post('/model-groups', d),
  update: (id, d) => api.put(`/model-groups/${id}`, d),
  delete: id => api.delete(`/model-groups/${id}`),
}

export const tagsApi = {
  list: () => api.get('/tags'),
  create: d => api.post('/tags', d),
  delete: id => api.delete(`/tags/${id}`),
}

export const operationLogsApi = {
  list: p => api.get('/operation-logs', { params: p }),
  export: p => api.get('/operation-logs/export', { params: p }),
  stats: () => api.get('/operation-logs/stats'),
  batchDelete: d => api.post('/operation-logs/batch-delete', d),
}
