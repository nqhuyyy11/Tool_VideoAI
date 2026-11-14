// Phần dùng chung cho mọi trang: kết nối Supabase Auth, gọi API backend, đăng xuất.

let sb = null; // Supabase client (chỉ dùng cho đăng nhập/đăng xuất)

async function initSupabase() {
  if (sb) return sb;
  const res = await fetch('/api/config');
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Không tải được cấu hình từ server.');
  // anon key được phép nằm ở trình duyệt; service_role key thì không bao giờ
  sb = window.supabase.createClient(data.supabase_url, data.supabase_anon_key);
  return sb;
}

// Dùng ở các trang cần đăng nhập. Chưa đăng nhập thì chuyển sang trang login.
async function requireUser() {
  const client = await initSupabase();
  const { data } = await client.auth.getSession();
  if (!data.session) {
    location.replace('/login.html');
    return null;
  }
  return data.session.user;
}

// Gọi API của backend, tự gắn token đăng nhập.
async function api(path, options = {}) {
  const client = await initSupabase();
  const { data } = await client.auth.getSession();
  if (!data.session) {
    location.replace('/login.html');
    throw new Error('Bạn chưa đăng nhập.');
  }
  const headers = { Authorization: 'Bearer ' + data.session.access_token };
  if (options.body) headers['Content-Type'] = 'application/json';

  const res = await fetch(path, { ...options, headers });
  const body = await res.json().catch(() => ({}));
  if (res.status === 401) {
    await client.auth.signOut();
    location.replace('/login.html');
    throw new Error('Phiên đăng nhập đã hết hạn.');
  }
  if (!res.ok) {
    const err = new Error(typeof body.detail === 'string' ? body.detail : 'Có lỗi xảy ra (mã ' + res.status + ').');
    err.status = res.status;
    throw err;
  }
  return body;
}

function setupLogout() {
  const btn = document.getElementById('logout');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const client = await initSupabase();
    await client.auth.signOut();
    location.replace('/login.html');
  });
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // trình duyệt cũ hoặc trang không chạy trên https/localhost
    const area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  if (button) {
    const old = button.textContent;
    button.textContent = 'Đã copy';
    setTimeout(() => { button.textContent = old; }, 1500);
  }
}

function showPageError(message) {
  const el = document.getElementById('page-error');
  if (!el) return;
  el.textContent = message;
  el.hidden = !message;
}
