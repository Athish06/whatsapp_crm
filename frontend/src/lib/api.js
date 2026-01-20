import axios from 'axios';

const API_BASE = process.env.REACT_APP_BACKEND_URL;
console.log('API Base URL:', API_BASE);

// Create axios instance with credentials enabled for cookie-based authentication
const api = axios.create({
  baseURL: `${API_BASE}/api`,
  withCredentials: true,  // CRITICAL: Enables sending and receiving cookies
});

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

// API endpoints for customers
export const customersAPI = {
  upload: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/customers/upload', formData);
  },
  list: () => api.get('/customers/list'),
  clear: () => api.delete('/customers/clear'),
};

// API endpoints for templates
export const templatesAPI = {
  create: (data) => api.post('/templates/create', data),
  list: () => api.get('/templates/list'),
  get: (id) => api.get(`/templates/${id}`),
  delete: (id) => api.delete(`/templates/${id}`),
};

// API endpoints for batches
export const batchesAPI = {
  estimate: (totalCustomers, batchSize) => api.post('/batches/estimate', null, {
    params: { total_customers: totalCustomers, batch_size: batchSize }
  }),
  create: (data) => api.post('/batches/create', data),
  list: () => api.get('/batches/list'),
  reschedule: (id) => api.post(`/batches/${id}/reschedule`),
  getMessages: (id) => api.get(`/batches/${id}/messages`),
};
