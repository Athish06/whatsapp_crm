import axios from 'axios';

const API_BASE = process.env.REACT_APP_BACKEND_URL;

const api = axios.create({
  baseURL: `${API_BASE}/api`,
});

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;

export const dashboardAPI = {
  getStats: () => api.get('/dashboard/stats'),
};

export const customersAPI = {
  upload: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/customers/upload', formData);
  },
  list: () => api.get('/customers/list'),
  clear: () => api.delete('/customers/clear'),
};

export const templatesAPI = {
  create: (data) => api.post('/templates/create', data),
  list: () => api.get('/templates/list'),
  get: (id) => api.get(`/templates/${id}`),
  delete: (id) => api.delete(`/templates/${id}`),
};

export const batchesAPI = {
  estimate: (totalCustomers, batchSize) => api.post('/batches/estimate', null, {
    params: { total_customers: totalCustomers, batch_size: batchSize }
  }),
  create: (data) => api.post('/batches/create', data),
  list: () => api.get('/batches/list'),
  reschedule: (id) => api.post(`/batches/${id}/reschedule`),
  getMessages: (id) => api.get(`/batches/${id}/messages`),
};
