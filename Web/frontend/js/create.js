// Trang "Tạo video": gửi chủ đề -> theo dõi tiến độ -> hiện kết quả.

const STEP_ORDER = ['scripting', 'voicing', 'fetching_footage', 'rendering', 'uploading'];
const POLL_MS = 2000;

const views = {
  form: document.getElementById('view-form'),
  progress: document.getElementById('view-progress'),
  result: document.getElementById('view-result'),
};
const formError = document.getElementById('form-error');
const createBtn = document.getElementById('create-btn');
const failBox = document.getElementById('fail-box');

let jobId = null;
let pollTimer = null;

function show(name) {
  for (const key in views) views[key].hidden = key !== name;
}

// ---------- Vẽ tiến độ ----------
function renderJob(job) {
  jobId = job.id;
  show('progress');
  document.getElementById('progress-topic').textContent = 'Chủ đề: ' + job.topic;

  const failed = job.status === 'failed';
  const current = STEP_ORDER.indexOf(job.step); // -1 khi còn đang chờ
  document.querySelectorAll('#steps li').forEach((li, i) => {
    li.classList.remove('done', 'active', 'failed');
    const dot = li.querySelector('.dot');
    dot.textContent = '';
    if (i < current) {
      li.classList.add('done');
      dot.textContent = '✓';
    } else if (i === current) {
      li.classList.add(failed ? 'failed' : 'active');
      if (failed) dot.textContent = '!';
    }
  });

  document.getElementById('progress-bar').style.width = job.percent + '%';
  document.getElementById('progress-track').setAttribute('aria-valuenow', job.percent);
  document.getElementById('progress-percent').textContent = job.percent + '%';

  let message = job.message;
  if (job.status === 'queued' && job.ahead > 0) {
    message = 'Đang chờ tới lượt, phía trước còn ' + job.ahead + ' video…';
  }
  document.getElementById('progress-message').textContent = failed ? 'Đã dừng do lỗi.' : message;
  document.getElementById('progress-title').textContent = failed ? 'Chưa tạo được video' : 'Đang tạo video';

  failBox.hidden = !failed;
  if (failed) document.getElementById('fail-message').textContent = job.error || 'Lỗi không rõ.';
}

function renderResult(video) {
  show('result');
  document.getElementById('result-title').textContent = video.title;
  document.getElementById('result-video').src = video.video_url;
  document.getElementById('result-download').href = video.download_url;
  document.getElementById('result-caption').value = video.caption;
}

// ---------- Hỏi tiến độ định kỳ ----------
function stopPolling() {
  clearTimeout(pollTimer);
  pollTimer = null;
}

async function poll() {
  try {
    const job = await api('/api/jobs/' + jobId);
    if (job.status === 'done') {
      renderResult(job.video);
      return;
    }
    renderJob(job);
    if (job.status === 'failed') return;
  } catch (err) {
    if (err.status === 404) { // server vừa khởi động lại, job không còn
      resetToForm();
      formError.textContent = err.message + ' Hãy tạo lại video.';
      formError.hidden = false;
      return;
    }
    document.getElementById('progress-message').textContent = 'Mất kết nối tới server, đang thử lại…';
  }
  pollTimer = setTimeout(poll, POLL_MS);
}

function resetToForm() {
  stopPolling();
  jobId = null;
  formError.hidden = true;
  show('form');
}

// ---------- Sự kiện ----------
const scriptFile = document.getElementById('script-file');
const scriptInfo = document.getElementById('script-file-info');

function showScriptInfo() {
  const file = scriptFile.files[0];
  scriptInfo.hidden = !file;
  if (file) scriptInfo.textContent = '✓ Đã chọn: ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
}
scriptFile.addEventListener('change', showScriptInfo);

views.form.addEventListener('submit', async (event) => {
  event.preventDefault();
  formError.hidden = true;
  createBtn.disabled = true;
  try {
    const file = scriptFile.files[0];
    if (file && file.size > 50000) throw new Error('File kịch bản quá lớn (tối đa 50 KB).');
    const topicBox = document.getElementById('topic');
    if (file && topicBox.value.trim().length < 3) topicBox.value = file.name.replace(/\.\w+$/, '');
    const job = await api('/api/jobs', {
      method: 'POST',
      body: JSON.stringify({
        topic: document.getElementById('topic').value,
        format: document.querySelector('input[name="format"]:checked').value,
        voice: document.querySelector('input[name="voice"]:checked').value,
        rate: document.getElementById('rate').value,
        script_md: file ? await file.text() : null,
      }),
    });
    renderJob(job);
    pollTimer = setTimeout(poll, POLL_MS);
  } catch (err) {
    formError.textContent = err.message;
    formError.hidden = false;
  } finally {
    createBtn.disabled = false;
  }
});

document.getElementById('retry-btn').addEventListener('click', async (event) => {
  event.target.disabled = true;
  try {
    renderJob(await api('/api/jobs/' + jobId + '/retry', { method: 'POST' }));
    pollTimer = setTimeout(poll, POLL_MS);
  } catch (err) {
    document.getElementById('fail-message').textContent = err.message;
  } finally {
    event.target.disabled = false;
  }
});

document.getElementById('discard-btn').addEventListener('click', async () => {
  try {
    await api('/api/jobs/' + jobId, { method: 'DELETE' });
  } catch { /* job không còn thì cũng coi như đã bỏ */ }
  resetToForm();
});

document.getElementById('again-btn').addEventListener('click', () => {
  document.getElementById('result-video').pause();
  document.getElementById('topic').value = '';
  scriptFile.value = '';
  showScriptInfo();
  resetToForm();
});

document.getElementById('copy-btn').addEventListener('click', (event) => {
  copyText(document.getElementById('result-caption').value, event.target);
});

// ---------- Khởi động ----------
(async () => {
  try {
    if (!(await requireUser())) return;
    setupLogout();
    // Nếu đang có video tạo dở (vd vừa tải lại trang) thì hiện tiếp tiến độ
    const { job } = await api('/api/jobs/current');
    if (job) {
      renderJob(job);
      if (job.status !== 'failed') pollTimer = setTimeout(poll, POLL_MS);
    } else {
      show('form');
    }
  } catch (err) {
    showPageError(err.message);
  }
})();
