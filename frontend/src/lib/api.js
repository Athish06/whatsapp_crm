import axios from 'axios';

const API_BASE = process.env.REACT_APP_BACKEND_URL;
console.log('API Base URL:', API_BASE);

// Create axios instance with credentials enabled for cookie-based authentication
const api = axios.create({
  baseURL: `${API_BASE}/api`,
  withCredentials: true,  // CRITICAL: Enables sending and receiving cookies
});

// Global interceptor to handle expired/cleared cookies
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // If any request gets a 401 Unauthorized, the cookie is missing or expired
    if (error.response && error.response.status === 401) {
      sessionStorage.removeItem('isAuthenticated');
      // Redirect to login if not already there
      if (window.location.pathname !== '/' && window.location.pathname !== '/register') {
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// API endpoints for authentication
export const authAPI = {
  login: (email, password) => api.post('/auth/login', { email, password }),
  register: (email, password, full_name) => api.post('/auth/register', { email, password, full_name }),
  logout: () => api.post('/auth/logout'),
  sendOTP: (email) => api.post('/auth/send-otp', { email }),
  verifyOTP: (email, otp) => api.post('/auth/verify-otp', { email, otp }),
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }),
  resetPassword: (email, otp, new_password) => api.post('/auth/reset-password', { email, otp, new_password }),
};

// API endpoints for dashboard
export const dashboardAPI = {
  getStats: () => api.get('/dashboard/stats'),
};

// API endpoints for shops
export const shopsAPI = {
  create: (name, uploadCycle = 'monthly') => api.post('/shops/create', { shop_name: name, upload_cycle: uploadCycle }),
  list: () => api.get('/shops/list'),
  getDetail: (shopId) => api.get(`/shops/${shopId}`),
  deleteCampaign: (shopId) => api.delete(`/shops/${shopId}/campaign`),
  deleteShop: (shopId) => api.delete(`/shops/${shopId}`),
  previewTemplate: (shopId, data) => api.post(`/shops/${shopId}/preview-template`, data),
  resendCampaign: (shopId, campaignId, mode) => api.post(`/shops/${shopId}/campaigns/${campaignId}/resend`, { mode }),
  upload: (shopId, dataType, file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/shops/${shopId}/upload/${dataType}`, formData);
  },
  process: (shopId, dataType, fileId, data) =>
    api.post(`/shops/${shopId}/process/${dataType}/${fileId}`, data),
};

// API endpoints for customers
export const customersAPI = {
  upload: (file, campaignId = null) => {
    const formData = new FormData();
    formData.append('file', file);
    if (campaignId) {
      formData.append('campaign_id', campaignId);
    }
    return api.post('/customers/upload', formData);
  },
  detectColumns: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/customers/detect-columns', formData);
  },
  uploadWithMapping: (file, columnMapping, percentile = 70, campaignId = null) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('column_mapping', JSON.stringify(columnMapping));
    formData.append('percentile', percentile.toString());
    if (campaignId) {
      formData.append('campaign_id', campaignId);
    }
    return api.post('/customers/upload-with-mapping', formData);
  },
  processWithMapping: (fileId, data) => api.post(`/customers/process-file/${fileId}`, data),
  list: (shopId = null) => api.get('/customers/list', { params: shopId ? { shop_id: shopId } : {} }),
  clear: (shopId = null) => api.delete('/customers/clear', { params: shopId ? { shop_id: shopId } : {} }),
  getByFile: (fileId) => api.get(`/customers/by-file/${fileId}`),
};

// API endpoints for templates
export const templatesAPI = {
  create: (data) => api.post('/templates/create', data),
  list: (shopId = null) => api.get('/templates/list', { params: shopId ? { shop_id: shopId } : {} }),
  get: (id) => api.get(`/templates/${id}`),
  update: (id, data) => api.put(`/templates/${id}`, data),
  delete: (id) => api.delete(`/templates/${id}`),
};

// API endpoints for batches
export const batchesAPI = {
  estimate: (totalCustomers, batchSize) => api.post('/batches/estimate', null, {
    params: { total_customers: totalCustomers, batch_size: batchSize }
  }),
  create: (data) => api.post('/batches/create', data),
  list: () => api.get('/batches/list'),
  campaignsList: () => api.get('/batches/campaigns/list'),
  stopCampaign: (campaignId) => api.post(`/batches/campaigns/${campaignId}/stop`),
  reschedule: (id) => api.post(`/batches/${id}/reschedule`),
  pause: (id) => api.post(`/batches/${id}/pause`),
  resume: (id) => api.post(`/batches/${id}/resume`),
  update: (id, data) => api.patch(`/batches/${id}`, data),
  delete: (id) => api.delete(`/batches/${id}`),
  getMessages: (id) => api.get(`/batches/${id}/messages`),
  clearAll: () => api.delete('/batches/clear-all'),
  getQueueStats: () => api.get('/batches/queue/stats'),
  getFileSummary: (fileId) => api.get(`/batches/file/${fileId}/summary`),

  // ── Campaign Control (Scheduler) ──
  pauseCampaign: (campaignId) => api.post(`/batches/campaigns/${campaignId}/pause`),
  resumeCampaign: (campaignId) => api.post(`/batches/campaigns/${campaignId}/resume`),
  cancelCampaign: (campaignId) => api.post(`/batches/campaigns/${campaignId}/cancel`),
  getLiveStats: (campaignId) => api.get(`/batches/campaigns/${campaignId}/live-stats`),
  getDLQ: (campaignId) => api.get(`/batches/campaigns/${campaignId}/dlq`),

  // ── Queue Item Actions (DLQ Resolution) ──
  requeueItem: (itemId) => api.post(`/batches/queue/${itemId}/requeue`),
  resolveItem: (itemId) => api.post(`/batches/queue/${itemId}/resolve`),
};

// API endpoints for files
export const filesAPI = {
  upload: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/files/upload', formData);
  },
  getMyFiles: (skip = 0, limit = 50) => api.get('/files/my-files', {
    params: { skip, limit }
  }),
  getFileInfo: (fileId) => api.get(`/files/file/${fileId}`),
  deleteFile: (fileId) => api.delete(`/files/file/${fileId}`),
  detectColumns: (fileId) => api.get(`/files/detect-columns/${fileId}`),
};

// API endpoints for offers (Phase 3)
export const offersAPI = {
  create:       (shopId, data)           => api.post(`/shops/${shopId}/offers`, data),
  list:         (shopId, activeOnly=true, segment=null) =>
                  api.get(`/shops/${shopId}/offers`, { params: { active_only: activeOnly, ...(segment ? { segment } : {}) } }),
  get:          (shopId, offerId)        => api.get(`/shops/${shopId}/offers/${offerId}`),
  update:       (shopId, offerId, data)  => api.put(`/shops/${shopId}/offers/${offerId}`, data),
  delete:       (shopId, offerId)        => api.delete(`/shops/${shopId}/offers/${offerId}`),
  matchPreview: (shopId)                 => api.get(`/shops/${shopId}/offers/match`),
  uploadCSV:    (shopId, file)           => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/shops/${shopId}/offers/upload-csv`, formData);
  },
};

// API endpoints for monitoring (Phase 5)
export const monitoringAPI = {
  getCampaignOverview: (shopId) => api.get(`/shops/${shopId}/monitoring/campaigns`),
  getCampaignDetail: (shopId, campaignId) => api.get(`/shops/${shopId}/monitoring/campaigns/${campaignId}`),
  getBatchDetail: (shopId, batchId) => api.get(`/shops/${shopId}/monitoring/batches/${batchId}`),
  getFailedMessages: (shopId, campaignId) => api.get(`/shops/${shopId}/monitoring/failed/${campaignId}`),
  rescheduleFailed: (shopId, campaignId, mode) => api.post(`/shops/${shopId}/monitoring/reschedule/${campaignId}`, null, { params: { mode } }),
  getPeriodSummary: (shopId, periodTag) => api.get(`/shops/${shopId}/monitoring/periods`, { params: { period_tag: periodTag } }),
};

export const productsAPI = {
  list: (shopId, params) => api.get(`/shops/${shopId}/products`, { params }),
  update: (shopId, productId, data) => api.patch(`/shops/${shopId}/products/${productId}`, data),
  recalculateInsights: (shopId) => api.post(`/shops/${shopId}/recalculate-insights`),
};
