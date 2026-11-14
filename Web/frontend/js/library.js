// Trang "Thư viện": liệt kê video đã tạo, xem lại, tải về, xoá.

const LINK_LIFETIME_MS = 50 * 60 * 1000; // link xem video hết hạn sau 1 giờ, làm mới trước đó

const grid = document.getElementById('grid');
const viewer = document.getElementById('viewer');
const viewerVideo = document.getElementById('viewer-video');
const viewerError = document.getElementById('viewer-error');

let videos = [];
let loadedAt = 0;
let openedId = null;

function formatDate(iso) {
  return new Date(iso).toLocaleString('vi-VN', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

async function loadVideos() {
  const data = await api('/api/videos');
  videos = data.videos;
  loadedAt = Date.now();
  renderGrid();
}

function renderGrid() {
  document.getElementById('loading').hidden = true;
  document.getElementById('empty').hidden = videos.length > 0;
  document.getElementById('count').textContent = videos.length ? videos.length + ' video' : '';

  grid.replaceChildren();
  for (const video of videos) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'video-card';
    card.addEventListener('click', () => openViewer(video.id));

    const thumb = document.createElement('img');
    thumb.className = 'thumb';
    thumb.alt = '';
    thumb.loading = 'lazy';
    if (video.thumbnail_url) thumb.src = video.thumbnail_url;

    const info = document.createElement('div');
    info.className = 'info';
    const title = document.createElement('div');
    title.className = 'title';
    title.textContent = video.title;
    const date = document.createElement('div');
    date.className = 'muted small';
    date.textContent = formatDate(video.created_at);
    info.append(title, date);

    card.append(thumb, info);
    grid.append(card);
  }
}

async function openViewer(id) {
  // Trang mở lâu quá thì link cũ đã hết hạn: tải lại danh sách để lấy link mới
  if (Date.now() - loadedAt > LINK_LIFETIME_MS) {
    try { await loadVideos(); } catch (err) { showPageError(err.message); return; }
  }
  const video = videos.find((v) => v.id === id);
  if (!video) return;

  openedId = id;
  viewerError.hidden = true;
  document.getElementById('viewer-title').textContent = video.title;
  document.getElementById('viewer-meta').textContent =
    'Chủ đề: ' + video.prompt + ' · ' + formatDate(video.created_at);
  document.getElementById('viewer-download').href = video.download_url;
  viewerVideo.src = video.video_url;
  viewer.showModal();
}

function closeViewer() {
  viewerVideo.pause();
  viewerVideo.removeAttribute('src');
  viewerVideo.load();
  openedId = null;
  if (viewer.open) viewer.close();
}

document.getElementById('viewer-close').addEventListener('click', closeViewer);
viewer.addEventListener('close', closeViewer);          // bấm Esc
viewer.addEventListener('click', (event) => {           // bấm ra ngoài khung
  if (event.target === viewer) closeViewer();
});

document.getElementById('viewer-copy').addEventListener('click', (event) => {
  const video = videos.find((v) => v.id === openedId);
  if (video) copyText(video.caption, event.target);
});

document.getElementById('viewer-delete').addEventListener('click', async (event) => {
  const video = videos.find((v) => v.id === openedId);
  if (!video) return;
  if (!confirm('Xoá video "' + video.title + '"? Không khôi phục lại được.')) return;

  event.target.disabled = true;
  try {
    await api('/api/videos/' + video.id, { method: 'DELETE' });
    videos = videos.filter((v) => v.id !== video.id);
    closeViewer();
    renderGrid();
  } catch (err) {
    viewerError.textContent = err.message;
    viewerError.hidden = false;
  } finally {
    event.target.disabled = false;
  }
});

(async () => {
  try {
    if (!(await requireUser())) return;
    setupLogout();
    await loadVideos();
  } catch (err) {
    document.getElementById('loading').hidden = true;
    showPageError(err.message);
  }
})();
