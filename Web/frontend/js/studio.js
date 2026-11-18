// Trang Studio: dự án nhiều cảnh -> tạo/ném ảnh và clip -> thêm thuyết minh -> ghép thành video.

const $ = (id) => document.getElementById(id);
const views = { list: $('view-list'), editor: $('view-editor'), progress: $('view-progress'), result: $('view-result') };
const STEP_ORDER = ['voicing', 'fetching_footage', 'rendering', 'uploading'];
const POLL_MS = 2000;

let project = null;            // {id, name, data:{format, voice, rate, transition, music, music_name, music_url, scenes[]}}
let jobId = null;
let pollTimer = null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const newId = () => 's' + Math.random().toString(36).slice(2, 9) + Date.now().toString(36);

function show(name) {
  for (const key in views) views[key].hidden = key !== name;
  $('page-error').hidden = true;
}

function editorError(message) {
  const el = $('editor-error');
  el.textContent = message || '';
  el.hidden = !message;
}

function formatDate(iso) {
  return new Date(iso).toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// =============================================================== Lưu tự động
let dirty = false;
let saveTimer = null;
let saveChain = Promise.resolve();

function setSaveState(text) { $('save-state').textContent = text; }

function payload() {
  const d = project.data;
  return {
    name: project.name.trim() || 'Dự án mới',
    format: d.format, voice: d.voice, rate: d.rate, transition: d.transition,
    music: d.music || null, music_name: d.music_name || '',
    scenes: d.scenes.map((s) => ({
      id: s.id, text: s.text || '',
      kind: s.asset ? s.kind : null, asset: s.asset || null, voice: s.voice || null,
    })),
  };
}

function queueSave() {
  clearTimeout(saveTimer);
  saveChain = saveChain.then(async () => {
    if (!dirty || !project) return;
    dirty = false;
    setSaveState('Đang lưu…');
    try {
      await api('/api/studio/projects/' + project.id, { method: 'PUT', body: JSON.stringify(payload()) });
      if (!dirty) setSaveState('Đã lưu');
    } catch (err) {
      dirty = true;
      setSaveState('Lỗi lưu: ' + err.message);
    }
  });
  return saveChain;
}

function markDirty() {
  dirty = true;
  setSaveState('Chưa lưu…');
  clearTimeout(saveTimer);
  saveTimer = setTimeout(queueSave, 800);
}

// =============================================================== Danh sách dự án
async function loadList() {
  const { projects } = await api('/api/studio/projects');
  const box = $('project-list');
  box.replaceChildren();
  $('list-empty').hidden = projects.length > 0;
  for (const p of projects) {
    const card = document.createElement('div');
    card.className = 'project-card';
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'project-open';
    const title = document.createElement('strong');
    title.textContent = p.name;
    const date = document.createElement('span');
    date.className = 'muted small';
    date.textContent = 'Sửa lần cuối ' + formatDate(p.updated_at);
    open.append(title, date);
    open.addEventListener('click', () => openProject(p.id));
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn btn-plain';
    del.textContent = 'Xoá';
    del.addEventListener('click', async () => {
      if (!confirm('Xoá dự án "' + p.name + '" cùng toàn bộ ảnh/clip trong đó? Không khôi phục lại được.')) return;
      try { await api('/api/studio/projects/' + p.id, { method: 'DELETE' }); loadList(); } catch (err) { showPageError(err.message); }
    });
    card.append(open, del);
    box.append(card);
  }
  show('list');
  history.replaceState(null, '', location.pathname);
}

$('new-project').addEventListener('click', async (event) => {
  event.target.disabled = true;
  try {
    const p = await api('/api/studio/projects', { method: 'POST', body: JSON.stringify({ name: 'Dự án mới' }) });
    setProject(p);
  } catch (err) { showPageError(err.message); } finally { event.target.disabled = false; }
});

async function openProject(id) {
  try { setProject(await api('/api/studio/projects/' + id)); } catch (err) { show('list'); showPageError(err.message); }
}

function setProject(p) {
  project = p;
  dirty = false;
  for (const s of project.data.scenes) { s.busy = ''; s.err = ''; }
  $('p-name').value = project.name;
  $('p-format').value = project.data.format;
  $('p-voice').value = project.data.voice;
  $('p-rate').value = project.data.rate;
  $('p-transition').value = project.data.transition;
  setSaveState('Đã lưu');
  editorError('');
  renderMusic();
  renderScenes();
  show('editor');
  history.replaceState(null, '', '#' + project.id);
}

$('back-btn').addEventListener('click', async () => {
  clearTimeout(saveTimer);
  await queueSave();
  project = null;
  loadList().catch((err) => showPageError(err.message));
});

// =============================================================== Cài đặt dự án
$('p-name').addEventListener('input', (e) => { project.name = e.target.value; markDirty(); });
for (const [id, key] of [['p-format', 'format'], ['p-voice', 'voice'], ['p-rate', 'rate'], ['p-transition', 'transition']]) {
  $(id).addEventListener('change', (e) => { project.data[key] = e.target.value; markDirty(); });
}

function renderMusic() {
  const d = project.data;
  $('music-label').textContent = d.music ? 'Nhạc nền: ' + (d.music_name || 'đã chọn') : '+ Nhạc nền (tuỳ chọn)';
  $('music-clear').hidden = !d.music;
  const audio = $('music-audio');
  audio.hidden = !d.music;
  if (d.music && d.music_url) audio.src = d.music_url; else audio.removeAttribute('src');
}

async function setMusic(file) {
  $('music-label').textContent = 'Đang tải nhạc…';
  try {
    const a = await apiUpload('/api/studio/assets', file);
    if (a.kind !== 'audio') throw new Error('Đây không phải tệp nhạc.');
    Object.assign(project.data, { music: a.path, music_url: a.url, music_name: file.name });
    markDirty();
  } catch (err) { editorError(err.message); }
  renderMusic();
}
$('music-file').addEventListener('change', (e) => { if (e.target.files[0]) setMusic(e.target.files[0]); e.target.value = ''; });
$('music-clear').addEventListener('click', () => {
  Object.assign(project.data, { music: null, music_url: null, music_name: '' });
  markDirty(); renderMusic();
});

// =============================================================== Dải cảnh
function renderScenes() {
  // giữ lại ô đang gõ dở khi vẽ lại
  const active = document.activeElement;
  const keep = active && active.dataset && active.dataset.sid
    ? { sid: active.dataset.sid, field: active.dataset.field, pos: active.selectionStart } : null;

  const box = $('scenes');
  box.replaceChildren();
  const scenes = project.data.scenes;
  $('scenes-empty').hidden = scenes.length > 0;
  $('scene-count').textContent = scenes.length ? scenes.length + ' cảnh' : '';
  scenes.forEach((s, i) => box.append(sceneCard(s, i, scenes.length)));

  if (keep) {
    const el = box.querySelector('[data-sid="' + keep.sid + '"][data-field="' + keep.field + '"]');
    if (el) { el.focus(); try { el.setSelectionRange(keep.pos, keep.pos); } catch { /* bỏ qua */ } }
  }
}

function button(label, onClick, cls = 'btn btn-plain') {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = cls;
  b.textContent = label;
  b.addEventListener('click', onClick);
  return b;
}

function field(label, scene, key, rows, placeholder) {
  const wrap = document.createElement('label');
  wrap.textContent = label;
  const area = document.createElement('textarea');
  area.rows = rows;
  area.maxLength = key === 'text' ? 1500 : 1000;
  area.placeholder = placeholder;
  area.value = scene[key] || '';
  area.dataset.sid = scene.id;
  area.dataset.field = key;
  area.addEventListener('input', () => { scene[key] = area.value; markDirty(); });
  wrap.append(area);
  return wrap;
}

function sceneCard(s, i, total) {
  const card = document.createElement('article');
  card.className = 'scene';

  const media = document.createElement('div');
  media.className = 'scene-media';
  if (s.busy) {
    media.innerHTML = '<div class="spinner"></div>';
    const t = document.createElement('span');
    t.textContent = s.busy;
    media.append(t);
  } else if (s.asset && s.url) {
    let el;
    if (s.kind === 'video') {
      el = document.createElement('video');
      el.src = s.url + '#t=0.1';
      el.muted = true; el.loop = true; el.controls = true; el.playsInline = true; el.preload = 'metadata';
    } else {
      el = document.createElement('img');
      el.src = s.url; el.alt = ''; el.loading = 'lazy';
    }
    media.append(el);
  } else {
    const t = document.createElement('span');
    t.className = 'muted small';
    t.textContent = 'Chưa có ảnh/clip (sẽ dùng nền tối)';
    media.append(t);
  }
  const badge = document.createElement('span');
  badge.className = 'badge';
  badge.textContent = 'Cảnh ' + (i + 1) + (s.asset ? (s.kind === 'video' ? ' · Clip' : ' · Ảnh') : '');
  media.append(badge);
  card.append(media);

  if (s.err) {
    const p = document.createElement('p');
    p.className = 'error-text small';
    p.textContent = s.err;
    card.append(p);
  }

  card.append(field('Lời thuyết minh', s, 'text', 3,
    s.voice ? 'Chữ hiện làm phụ đề (để trống = không phụ đề)' : 'Máy sẽ đọc câu này (để trống = cảnh không có tiếng)'));

  if (s.voice && s.voice_url) {
    const au = document.createElement('audio');
    au.src = s.voice_url; au.controls = true; au.preload = 'none';
    card.append(au);
  }

  const row = document.createElement('div');
  row.className = 'scene-actions';
  const disabled = !!s.busy;
  const vo = document.createElement('label');
  vo.className = 'btn mini';
  vo.textContent = s.voice ? 'Đổi giọng thu' : 'Giọng thu âm';
  const vin = document.createElement('input');
  vin.type = 'file'; vin.accept = 'audio/*,.mp3,.m4a,.wav'; vin.hidden = true; vin.disabled = disabled;
  vin.addEventListener('change', () => { if (vin.files[0]) uploadVoice(s, vin.files[0]); });
  vo.append(vin);
  row.append(vo);
  if (s.voice) {
    const b = button('Bỏ giọng thu', () => { s.voice = null; s.voice_url = null; markDirty(); renderScenes(); }, 'btn mini');
    b.disabled = disabled;
    row.append(b);
  }
  const up = document.createElement('label');
  up.className = 'btn mini';
  up.textContent = 'Tải lên';
  const input = document.createElement('input');
  input.type = 'file'; input.accept = 'image/*,video/*'; input.hidden = true; input.disabled = disabled;
  input.addEventListener('change', () => { if (input.files[0]) uploadInto(s, input.files[0]); });
  up.append(input);
  row.append(up);

  const move = document.createElement('span');
  move.className = 'move';
  const bUp = button('↑', () => moveScene(i, -1), 'btn btn-plain mini'); bUp.disabled = i === 0; bUp.title = 'Đưa lên';
  const bDown = button('↓', () => moveScene(i, 1), 'btn btn-plain mini'); bDown.disabled = i === total - 1; bDown.title = 'Đưa xuống';
  const bDel = button('Xoá', () => removeScene(s), 'btn btn-plain mini');
  move.append(bUp, bDown, bDel);
  row.append(move);
  card.append(row);
  return card;
}

function moveScene(i, delta) {
  const list = project.data.scenes;
  const j = i + delta;
  if (j < 0 || j >= list.length) return;
  [list[i], list[j]] = [list[j], list[i]];
  markDirty(); renderScenes();
}

function removeScene(s) {
  if (s.asset && !confirm('Xoá cảnh này cùng ảnh/clip của nó?')) return;
  project.data.scenes = project.data.scenes.filter((x) => x !== s);
  markDirty(); renderScenes();
}

function addScene(extra = {}) {
  const s = { id: newId(), text: '', kind: null, asset: null, url: null, busy: '', err: '', ...extra };
  project.data.scenes.push(s);
  markDirty(); renderScenes();
  return s;
}

$('add-empty').addEventListener('click', () => addScene());

// =============================================================== Giọng thu âm
async function uploadVoice(scene, file) {
  const proj = project;
  scene.err = '';
  scene.busy = 'Đang tải giọng thu…';
  renderScenes();
  try {
    const a = await apiUpload('/api/studio/assets', file);
    if (a.kind !== 'audio') throw new Error('Đây không phải tệp âm thanh.');
    Object.assign(scene, { voice: a.path, voice_url: a.url });
    markDirty();
  } catch (err) {
    scene.err = file.name + ': ' + err.message;
  } finally {
    scene.busy = '';
    if (project === proj) renderScenes();
  }
}

// Nhiều file thu âm: xếp theo tên, file thứ n vào cảnh thứ n
$('voice-files').addEventListener('change', async (e) => {
  const files = [...e.target.files].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  e.target.value = '';
  const scenes = project.data.scenes;
  if (files.length > scenes.length) editorError('Có ' + files.length + ' file thu âm nhưng chỉ có ' + scenes.length + ' cảnh. Các file thừa bị bỏ qua.');
  else editorError('');
  const jobs = files.slice(0, scenes.length).map((f, i) => [scenes[i], f]);
  let next = 0;
  const worker = async () => { while (next < jobs.length) { const [s, f] = jobs[next++]; await uploadVoice(s, f); } };
  await Promise.all([worker(), worker()]);
});

// =============================================================== Tải ảnh / clip lên
async function uploadInto(scene, file) {
  const proj = project;
  scene.err = '';
  scene.busy = 'Đang tải lên…';
  renderScenes();
  try {
    const a = await apiUpload('/api/studio/assets', file);
    if (a.kind === 'audio') throw new Error('Đây là tệp nhạc. Hãy đặt ở mục "Nhạc nền".');
    Object.assign(scene, { kind: a.kind, asset: a.path, url: a.url });
    markDirty();
  } catch (err) {
    scene.err = file.name + ': ' + err.message;
  } finally {
    scene.busy = '';
    if (project === proj) renderScenes();
  }
}

const isAudio = (f) => f.type.startsWith('audio/') || /\.(mp3|m4a|wav|aac|ogg|flac)$/i.test(f.name);

async function addFiles(fileList) {
  if (!project) return;
  const files = [...fileList].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  const music = files.find(isAudio);
  if (music) setMusic(music);
  const media = files.filter((f) => !isAudio(f));
  const room = 60 - project.data.scenes.length;
  if (media.length > room) editorError('Mỗi dự án tối đa 60 cảnh, chỉ thêm được ' + Math.max(room, 0) + ' tệp.');
  const queue = media.slice(0, Math.max(room, 0)).map((file) => ({ file, scene: addScene({ busy: 'Đang tải lên…' }) }));
  let next = 0;
  const worker = async () => {
    while (next < queue.length) {
      const { file, scene } = queue[next++];
      await uploadInto(scene, file);
    }
  };
  await Promise.all([worker(), worker()]);   // tải 2 tệp cùng lúc
}

$('media-files').addEventListener('change', (e) => { addFiles(e.target.files); e.target.value = ''; });

const dz = $('dropzone');
dz.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('media-files').click(); } });
for (const ev of ['dragenter', 'dragover']) {
  document.addEventListener(ev, (e) => { e.preventDefault(); if (project && !views.editor.hidden) dz.classList.add('over'); });
}
for (const ev of ['dragleave', 'drop']) {
  document.addEventListener(ev, (e) => { if (ev === 'drop' || e.target === document || !e.relatedTarget) dz.classList.remove('over'); });
}
document.addEventListener('drop', (e) => {
  e.preventDefault();
  dz.classList.remove('over');
  if (project && !views.editor.hidden && e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
});

// =============================================================== Dán cả thuyết minh
$('split-btn').addEventListener('click', () => {
  const lines = $('script-all').value.split(/\n+/)
    .map((l) => l.replace(/^#+\s*/, '').split(' | ')[0].trim())     // bỏ dấu # và phần " | keywords" nếu dán từ file .md
    .filter(Boolean);
  if (!lines.length) { editorError('Hãy dán lời thuyết minh vào ô trước.'); return; }
  editorError('');
  const scenes = project.data.scenes;
  if (lines.length > scenes.length) {
    const extra = lines.length - scenes.length;
    if (!confirm('Có ' + lines.length + ' đoạn thuyết minh nhưng chỉ có ' + scenes.length + ' cảnh. Tạo thêm ' + extra + ' cảnh trống cho phần còn lại?')) return;
    for (let k = 0; k < extra; k++) {
      scenes.push({ id: newId(), prompt: '', text: '', kind: null, asset: null, url: null, busy: '', err: '' });
    }
  }
  lines.forEach((line, i) => { scenes[i].text = line; });
  markDirty(); renderScenes();
});

// =============================================================== Ghép video
function stopPolling() { clearTimeout(pollTimer); pollTimer = null; }

function renderJob(job) {
  jobId = job.id;
  show('progress');
  $('progress-topic').textContent = 'Dự án: ' + job.topic;
  const failed = job.status === 'failed';
  const current = STEP_ORDER.indexOf(job.step);
  document.querySelectorAll('#steps li').forEach((li, i) => {
    li.classList.remove('done', 'active', 'failed');
    const dot = li.querySelector('.dot');
    dot.textContent = '';
    if (i < current) { li.classList.add('done'); dot.textContent = '✓'; }
    else if (i === current) { li.classList.add(failed ? 'failed' : 'active'); if (failed) dot.textContent = '!'; }
  });
  $('progress-bar').style.width = job.percent + '%';
  $('progress-track').setAttribute('aria-valuenow', job.percent);
  $('progress-percent').textContent = job.percent + '%';
  let message = job.message;
  if (job.status === 'queued' && job.ahead > 0) message = 'Đang chờ tới lượt, phía trước còn ' + job.ahead + ' video…';
  $('progress-message').textContent = failed ? 'Đã dừng do lỗi.' : message;
  $('progress-title').textContent = failed ? 'Chưa ghép được video' : 'Đang ghép video';
  $('fail-box').hidden = !failed;
  if (failed) $('fail-message').textContent = job.error || 'Lỗi không rõ.';
}

function renderResult(video) {
  show('result');
  $('result-title').textContent = video.title;
  $('result-video').src = video.video_url;
  $('result-download').href = video.download_url;
}

async function poll() {
  try {
    const job = await api('/api/jobs/' + jobId);
    if (job.status === 'done') { renderResult(job.video); return; }
    renderJob(job);
    if (job.status === 'failed') return;
  } catch (err) {
    if (err.status === 404) { backToEditor('Video đang ghép không còn (server vừa khởi động lại). Hãy bấm ghép lại.'); return; }
    $('progress-message').textContent = 'Mất kết nối tới server, đang thử lại…';
  }
  pollTimer = setTimeout(poll, POLL_MS);
}

async function backToEditor(message) {
  stopPolling();
  jobId = null;
  const id = project ? project.id : location.hash.slice(1);
  if (id) await openProject(id); else await loadList();
  if (message) editorError(message);
}

$('compose-btn').addEventListener('click', async (event) => {
  editorError('');
  const scenes = project.data.scenes;
  if (!scenes.length) { editorError('Dự án chưa có cảnh nào.'); return; }
  if (scenes.some((s) => s.busy)) { editorError('Còn cảnh đang tạo/tải lên, hãy chờ xong rồi ghép.'); return; }
  const empty = scenes.filter((s) => !s.asset).length;
  if (empty && !confirm(empty + ' cảnh chưa có ảnh/clip sẽ dùng nền tối. Vẫn ghép?')) return;
  event.target.disabled = true;
  try {
    dirty = true;
    await queueSave();
    if (dirty) throw new Error('Chưa lưu được dự án, hãy thử lại.');
    renderJob(await api('/api/studio/projects/' + project.id + '/compose', { method: 'POST' }));
    pollTimer = setTimeout(poll, POLL_MS);
  } catch (err) { editorError(err.message); } finally { event.target.disabled = false; }
});

$('retry-btn').addEventListener('click', async (event) => {
  event.target.disabled = true;
  try {
    renderJob(await api('/api/jobs/' + jobId + '/retry', { method: 'POST' }));
    pollTimer = setTimeout(poll, POLL_MS);
  } catch (err) { $('fail-message').textContent = err.message; } finally { event.target.disabled = false; }
});

$('discard-btn').addEventListener('click', async () => {
  try { await api('/api/jobs/' + jobId, { method: 'DELETE' }); } catch { /* job không còn thì cũng coi như đã bỏ */ }
  backToEditor();
});

$('result-back').addEventListener('click', () => { $('result-video').pause(); backToEditor(); });

// =============================================================== Khởi động
(async () => {
  try {
    if (!(await requireUser())) return;
    setupLogout();
    const { job } = await api('/api/jobs/current');
    if (job) {
      renderJob(job);
      if (job.status !== 'failed') pollTimer = setTimeout(poll, POLL_MS);
    } else if (location.hash.length > 1) {
      await openProject(location.hash.slice(1));
    } else {
      await loadList();
    }
  } catch (err) {
    showPageError(err.message);
  }
})();

addEventListener('beforeunload', (e) => {
  if (dirty) { e.preventDefault(); e.returnValue = ''; }
});
