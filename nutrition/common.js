/* 儿童营养餐智能分配系统 — 公共 JS */

// API 基础路径
const API_BASE = window.NUTRITION_API_BASE || '/api/nutrition';
const NUTRITION_CONTEXT = new URLSearchParams(window.location.search);
const NUTRITION_ROLE = NUTRITION_CONTEXT.get('role') || localStorage.getItem('nutrition_role') || 'teacher';
const NUTRITION_CHILD_CODE = NUTRITION_CONTEXT.get('childCode') || '';

function nutritionHealthIslandUrl() {
  const params = new URLSearchParams({ role: NUTRITION_ROLE });
  if (NUTRITION_ROLE === 'parent' && NUTRITION_CHILD_CODE) params.set('kid', NUTRITION_CHILD_CODE);
  return `/island-health.html?${params.toString()}`;
}

function addNutritionBackButton() {
  const header = document.querySelector('.app-header');
  if (!header || header.querySelector('.nutrition-back-link')) return;
  const link = document.createElement('a');
  link.className = 'nutrition-back-link';
  link.href = nutritionHealthIslandUrl();
  link.textContent = '‹ 返回健康岛';
  link.setAttribute('aria-label', '返回健康岛');
  link.style.cssText = 'display:inline-flex;align-items:center;margin-right:14px;padding:7px 12px;border:1px solid rgba(255,255,255,.55);border-radius:8px;color:inherit;text-decoration:none;font-weight:700;font-size:13px;white-space:nowrap;';
  link.onmouseenter = () => { link.style.background = 'rgba(255,255,255,.16)'; };
  link.onmouseleave = () => { link.style.background = 'transparent'; };
  header.prepend(link);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addNutritionBackButton);
else addNutritionBackButton();

// ============================================================
// API 请求封装
// ============================================================

async function apiFetch(path, options = {}) {
  const url = API_BASE + path;
  const config = {
    headers: {
      'Content-Type': 'application/json',
      'X-User-Role': NUTRITION_ROLE,
      ...(NUTRITION_CHILD_CODE ? {'X-Nutrition-Child-Code': NUTRITION_CHILD_CODE} : {}),
      ...(options.headers || {})
    },
    ...options,
  };
  try {
    const resp = await fetch(url, config);
    if (resp.status === 401) { window.location.href = '/nutrition/login.html'; return null; }
    if (resp.status === 403) { alert('权限不足'); return null; }
    const data = await resp.json().catch(() => null);
    if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
    return data;
  } catch (err) {
    if (err.name !== 'TypeError') showError(err.message);
    console.error(`API ${options.method || 'GET'} ${path}:`, err);
    return null;
  }
}

// ============================================================
// Toast 通知
// ============================================================

function showSuccess(msg) { showToast(msg, 'success'); }
function showError(msg) { showToast(msg, 'error'); }
function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container') || createToastContainer();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3000);
}
function createToastContainer() {
  const el = document.createElement('div');
  el.id = 'toast-container';
  el.style.cssText = 'position:fixed;top:72px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
  document.body.appendChild(el);
  // Add toast styles if not already present
  if (!document.getElementById('toast-styles')) {
    const style = document.createElement('style');
    style.id = 'toast-styles';
    style.textContent = `
      .toast { padding: 12px 20px; border-radius: 8px; color: #fff; font-size: 0.9em; box-shadow: 0 4px 12px rgba(0,0,0,0.2); opacity: 1; transition: opacity 0.3s; max-width: 360px; }
      .toast-success { background: #2e7d32; }
      .toast-error { background: #c62828; }
      .toast-info { background: #1565c0; }
      .toast-warning { background: #f57f17; }
    `;
    document.head.appendChild(style);
  }
  return el;
}

// ============================================================
// 分页渲染
// ============================================================

function renderPagination(container, total, page, pageSize, onPageChange) {
  if (!container) return;
  container.innerHTML = '';
  const totalPages = Math.ceil(total / pageSize) || 1;
  const btn = (text, target, disabled) => {
    const b = document.createElement('button');
    b.textContent = text;
    b.disabled = disabled;
    if (!disabled) b.onclick = () => onPageChange(target);
    return b;
  };
  container.appendChild(btn('«', 1, page <= 1));
  container.appendChild(btn('‹', page - 1, page <= 1));
  const span = document.createElement('span');
  span.textContent = `第 ${page} / ${totalPages} 页（共 ${total} 条）`;
  container.appendChild(span);
  container.appendChild(btn('›', page + 1, page >= totalPages));
  container.appendChild(btn('»', totalPages, page >= totalPages));
}

// ============================================================
// 格式化
// ============================================================

function formatDate(d) {
  if (!d) return '-';
  if (typeof d === 'string') d = d.replace(' ', 'T');
  return new Date(d).toLocaleDateString('zh-CN');
}

function formatDateTime(d) {
  if (!d) return '-';
  if (typeof d === 'string') d = d.replace(' ', 'T');
  return new Date(d).toLocaleString('zh-CN');
}

function formatNum(n, decimals = 1) {
  if (n === null || n === undefined || n === '') return '-';
  return Number(n).toFixed(decimals);
}

function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function parseJsonField(val) {
  if (!val) return [];
  if (Array.isArray(val)) return val;
  if (typeof val === 'string') {
    try { return JSON.parse(val); } catch { return [val]; }
  }
  return [];
}

// ============================================================
// Modal
// ============================================================

function showModal(title, bodyHtml, onConfirm, confirmText = '确认') {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <h2>${escHtml(title)}</h2>
      <div>${bodyHtml}</div>
      <div class="modal-footer">
        <button class="btn btn-outline" id="modal-cancel">取消</button>
        <button class="btn btn-primary" id="modal-confirm">${confirmText}</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.querySelector('#modal-cancel').onclick = () => overlay.remove();
  overlay.querySelector('#modal-confirm').onclick = () => { if (onConfirm) onConfirm(); overlay.remove(); };
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
}

function showConfirm(title, message, onConfirm) {
  showModal(title, `<p>${escHtml(message)}</p>`, onConfirm, '确认');
}

// ============================================================
// 搜索防抖
// ============================================================

function debounce(fn, ms = 300) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}
