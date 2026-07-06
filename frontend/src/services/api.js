import axios from 'axios';

const isProd = import.meta.env.PROD;
const API_BASE_URL = import.meta.env.VITE_API_URL || (isProd ? '/api' : 'http://localhost:8000/api');

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
  paramsSerializer: {
    indexes: null
  }
});

api.interceptors.request.use(config => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  response => response,
  error => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);
// ─── Projects ──────────────────────────────────────────────────
export const createProject = (name, description) =>
  api.post('/projects', { name, description });

export const getProjects = (page = 1, pageSize = 20) =>
  api.get('/projects', { params: { page, page_size: pageSize } });

export const getProject = (id) =>
  api.get(`/projects/${id}`);

export const deleteProject = (id) =>
  api.delete(`/projects/${id}`);

// ─── Repositories ──────────────────────────────────────────────
export const addRepository = (projectId, gitUrl, name, accessToken, branch) =>
  api.post(`/projects/${projectId}/repositories`, { git_url: gitUrl, name, access_token: accessToken, branch });

export const getRepositories = (projectId) =>
  api.get(`/projects/${projectId}/repositories`);

export const syncRepository = (repositoryId) =>
  api.post(`/repositories/${repositoryId}/sync`);

export const updateRepositoryBranch = (repositoryId, branch) =>
  api.put(`/repositories/${repositoryId}/branch`, { branch });

export const deleteRepository = (repositoryId) =>
  api.delete(`/repositories/${repositoryId}`);

// ─── Developers ────────────────────────────────────────────────
export const getProjectDevelopers = (id, params = {}) =>
  api.get(`/projects/${id}/developers`, { params });

export const updateDeveloperExclusion = (id, is_excluded) =>
  api.put(`/developers/${id}/exclusion`, { is_excluded });

// ─── Commits ───────────────────────────────────────────────────
export const getProjectCommits = (id, params = {}) =>
  api.get(`/projects/${id}/commits`, { params });

// ─── Statistics ────────────────────────────────────────────────
export const getProjectStatistics = (id, params = {}) =>
  api.get(`/projects/${id}/statistics`, { params });

// ─── Languages ─────────────────────────────────────────────────
export const getProjectLanguages = (id, params = {}) =>
  api.get(`/projects/${id}/languages`, { params });

// ─── Files ─────────────────────────────────────────────────────
export const getProjectFiles = (id, params = {}) =>
  api.get(`/projects/${id}/files`, { params: { limit: 100, ...params } });

// ─── Folders ───────────────────────────────────────────────────
export const getProjectFolders = (id, params = {}) =>
  api.get(`/projects/${id}/folders`, { params: { limit: 50, ...params } });

// ─── Reports ───────────────────────────────────────────────────
export const getReportDevelopers = (params = {}) =>
  api.get('/reports/developers', { params: { page: 1, page_size: 50, ...params } });

export const getReportProjects = (params = {}) =>
  api.get('/reports/projects', { params });

export default api;
