// Trang đăng nhập / đăng ký bằng email (Supabase Auth).

let mode = 'login'; // 'login' hoặc 'signup'

const form = document.getElementById('auth-form');
const submitBtn = document.getElementById('submit');
const notice = document.getElementById('notice');
const tabLogin = document.getElementById('tab-login');
const tabSignup = document.getElementById('tab-signup');
const passwordInput = document.getElementById('password');

function setMode(next) {
  mode = next;
  tabLogin.setAttribute('aria-selected', String(mode === 'login'));
  tabSignup.setAttribute('aria-selected', String(mode === 'signup'));
  submitBtn.textContent = mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản';
  passwordInput.autocomplete = mode === 'login' ? 'current-password' : 'new-password';
  showPageError('');
  notice.hidden = true;
}

// Đổi thông báo lỗi tiếng Anh của Supabase sang tiếng Việt
function translate(message) {
  const m = (message || '').toLowerCase();
  if (m.includes('invalid login credentials')) return 'Email hoặc mật khẩu không đúng.';
  if (m.includes('email not confirmed')) return 'Email chưa được xác nhận. Hãy mở hộp thư và bấm vào link xác nhận.';
  if (m.includes('already registered')) return 'Email này đã có tài khoản. Hãy chuyển sang "Đăng nhập".';
  if (m.includes('at least 6')) return 'Mật khẩu cần ít nhất 6 ký tự.';
  if (m.includes('rate limit')) return 'Gửi quá nhiều yêu cầu. Hãy chờ vài phút rồi thử lại.';
  if (m.includes('signups not allowed') || m.includes('signup is disabled')) return 'Trang này hiện không cho đăng ký tài khoản mới.';
  return message || 'Có lỗi xảy ra, hãy thử lại.';
}

tabLogin.addEventListener('click', () => setMode('login'));
tabSignup.addEventListener('click', () => setMode('signup'));

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  showPageError('');
  notice.hidden = true;
  submitBtn.disabled = true;

  const email = document.getElementById('email').value.trim();
  const password = passwordInput.value;

  try {
    const client = await initSupabase();
    if (mode === 'login') {
      const { error } = await client.auth.signInWithPassword({ email, password });
      if (error) throw error;
      location.replace('/');
    } else {
      const { data, error } = await client.auth.signUp({ email, password });
      if (error) throw error;
      if (data.session) {
        location.replace('/'); // Supabase đang tắt xác nhận email: vào thẳng
      } else {
        notice.textContent = 'Đã tạo tài khoản. Hãy mở email và bấm link xác nhận, sau đó quay lại đăng nhập.';
        notice.hidden = false;
        setModeKeepNotice('login');
      }
    }
  } catch (err) {
    showPageError(translate(err.message));
  } finally {
    submitBtn.disabled = false;
  }
});

function setModeKeepNotice(next) {
  const text = notice.textContent;
  setMode(next);
  notice.textContent = text;
  notice.hidden = false;
}

// Đã đăng nhập sẵn thì vào thẳng trang chính
(async () => {
  try {
    const client = await initSupabase();
    const { data } = await client.auth.getSession();
    if (data.session) location.replace('/');
  } catch (err) {
    showPageError(err.message);
  }
})();
