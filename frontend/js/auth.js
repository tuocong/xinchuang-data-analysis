// ============================================================
// 前端统一鉴权工具
// 登录成功后 login.html 会把 token 写入 localStorage('token')
// 受保护页面请先引入本文件，再调用 requireLogin() / authFetch()
// ============================================================

function getToken() {
  return localStorage.getItem('token') || '';
}

function getLoginUser() {
  return localStorage.getItem('loginUser') || '';
}

// 页面守卫：无 token 时跳回登录页，返回 false 表示未放行
function requireLogin() {
  if (!getToken()) {
    location.href = 'login.html';
    return false;
  }
  return true;
}

// 带鉴权的 fetch：自动加 Authorization 头，401 时跳登录页
async function authFetch(url, options) {
  options = options || {};
  const headers = Object.assign({}, options.headers || {});
  headers['Authorization'] = 'Bearer ' + getToken();
  const res = await fetch(url, Object.assign({}, options, { headers: headers }));
  if (res.status === 401) {
    localStorage.removeItem('token');
    location.href = 'login.html';
    throw new Error('未登录或登录已过期');
  }
  return res;
}
