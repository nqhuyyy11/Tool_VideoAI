// Thế giới 3D kiểu bruno-simon.com: một hòn đảo nổi, lái xe bằng WASD / phím mũi tên.
// Các biển chỉ đường là nút điều hướng của web: lái xe vào bệ sáng và đứng yên một chút để chuyển trang.
// Dùng chung cho mọi trang. Nếu trình duyệt không có WebGL thì tự bỏ qua, web vẫn dùng bình thường.

import * as THREE from 'three';

const page = document.body.dataset.page || 'create';
const isLogin = page === 'login';
const canvas = document.getElementById('world');
const loader = document.getElementById('loader');
const touchDevice = matchMedia('(pointer: coarse)').matches;

function giveUp() {
  document.body.classList.add('no-world', 'world-ready');
}

main().catch((err) => {
  console.warn('Không dựng được thế giới 3D:', err);
  giveUp();
});

async function main() {
  if (!canvas) return giveUp();

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  } catch {
    return giveUp();
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, touchDevice ? 1.5 : 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  // Chờ font tải xong (tối đa 1.5 giây) để chữ trên biển vẽ đúng font
  try {
    await Promise.race([
      Promise.all([document.fonts.load('800 60px "Baloo 2"'), document.fonts.load('700 30px "Baloo 2"')]),
      new Promise((resolve) => setTimeout(resolve, 1500)),
    ]);
  } catch { /* bỏ qua */ }

  // ---------------------------------------------------------------- Hằng số
  const R = 46;                       // bán kính hòn đảo
  const SPAWN = { x: 0, z: 9, heading: Math.PI };
  const SKY_FOG = 0xcfe3ff;
  const PADS = [
    { id: 'create', label: 'Tạo video', href: '/', x: -17, z: -14, color: 0xff7a3d },
    { id: 'library', label: 'Thư viện', href: '/library.html', x: 17, z: -14, color: 0x4fb8ff },
    { id: 'logout', label: 'Đăng xuất', action: 'logout', x: 0, z: -29, color: 0xff6b8b },
  ];

  function rng(seed) {
    return () => {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const rand = rng(20240607);
  const between = (a, b) => a + (b - a) * rand();

  // ---------------------------------------------------------------- Cảnh, camera, ánh sáng
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(SKY_FOG, 70, 190);

  // Bầu trời: dải màu dọc từ xanh đến hơi ấm ở chân trời
  {
    const c = document.createElement('canvas');
    c.width = 4; c.height = 256;
    const g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 0, 256);
    grad.addColorStop(0, '#5aa2ff');
    grad.addColorStop(0.55, '#b9dcff');
    grad.addColorStop(1, '#ffe3bd');
    g.fillStyle = grad; g.fillRect(0, 0, 4, 256);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    scene.background = tex;
  }

  const camera = new THREE.PerspectiveCamera(32, 1, 1, 400);
  const camOffset = new THREE.Vector3(0, 30, 26);
  const camPos = new THREE.Vector3();
  const camLook = new THREE.Vector3();

  scene.add(new THREE.HemisphereLight(0xdff0ff, 0x8a6a4a, 1.25));
  const sun = new THREE.DirectionalLight(0xfff0d8, 2.4);
  sun.castShadow = true;
  sun.shadow.mapSize.set(touchDevice ? 1024 : 2048, touchDevice ? 1024 : 2048);
  const sc = sun.shadow.camera;
  sc.left = -42; sc.right = 42; sc.top = 42; sc.bottom = -42; sc.near = 1; sc.far = 120;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.04;
  scene.add(sun, sun.target);
  const sunOffset = new THREE.Vector3(-22, 38, 16);

  // ---------------------------------------------------------------- Vật liệu & tiện ích
  const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, flatShading: true, ...extra });
  const shadowed = (mesh, cast = true, receive = true) => { mesh.castShadow = cast; mesh.receiveShadow = receive; return mesh; };

  function textTexture(lines, w, h, bg, fg, radius = 48) {
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const g = c.getContext('2d');
    if (bg) {
      g.fillStyle = bg;
      g.beginPath(); g.roundRect(0, 0, w, h, radius); g.fill();
    }
    g.fillStyle = fg;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    const rows = Array.isArray(lines) ? lines : [{ text: lines, size: h * 0.5 }];
    const total = rows.reduce((s, r) => s + r.size * 1.1, 0);
    let y = (h - total) / 2;
    for (const r of rows) {
      g.font = `${r.weight || 800} ${r.size}px "Baloo 2", "Nunito", system-ui, sans-serif`;
      g.fillStyle = r.color || fg;
      g.fillText(r.text, w / 2, y + r.size * 0.58);
      y += r.size * 1.1;
    }
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    return tex;
  }

  // ---------------------------------------------------------------- Va chạm
  const statics = [];                 // {x, z, r}
  const occupied = [];                // chỗ đã dùng, để rải cây/đá không đè lên
  const addStatic = (x, z, r) => { statics.push({ x, z, r }); occupied.push({ x, z, r: r + 1 }); };

  const spokes = PADS.map((p) => ({ x1: 0, z1: 0, x2: p.x, z2: p.z }));
  function distToSegment(px, pz, s) {
    const dx = s.x2 - s.x1, dz = s.z2 - s.z1;
    const t = Math.max(0, Math.min(1, ((px - s.x1) * dx + (pz - s.z1) * dz) / (dx * dx + dz * dz)));
    return Math.hypot(px - (s.x1 + t * dx), pz - (s.z1 + t * dz));
  }
  function isFree(x, z, r, margin = 4) {
    if (Math.hypot(x, z) > R - margin) return false;
    if (Math.hypot(x, z) < 11 + r) return false;                         // quảng trường giữa đảo
    if (Math.hypot(x - SPAWN.x, z - SPAWN.z) < 9 + r) return false;
    if (PADS.some((p) => Math.hypot(x - p.x, z - p.z) < 7 + r)) return false;
    if (spokes.some((s) => distToSegment(x, z, s) < 3.6 + r)) return false;
    return !occupied.some((o) => Math.hypot(x - o.x, z - o.z) < o.r + r);
  }

  // ---------------------------------------------------------------- Hòn đảo
  const island = new THREE.Group();
  scene.add(island);

  island.add(shadowed(new THREE.Mesh(new THREE.CircleGeometry(R, 72).rotateX(-Math.PI / 2), mat(0x86cc5c)), false, true));
  const rim = new THREE.Mesh(new THREE.CylinderGeometry(R, R * 0.96, 3.2, 72, 1, true), mat(0x9b6a45, { side: THREE.DoubleSide }));
  rim.position.y = -1.6; island.add(rim);
  const under = new THREE.Mesh(new THREE.ConeGeometry(R * 0.96, 26, 14, 1, true).rotateX(Math.PI), mat(0x70492f, { side: THREE.DoubleSide }));
  under.position.y = -3.2 - 13; island.add(under);

  // Mảng cỏ đậm/nhạt cho đỡ trống
  {
    const geo = new THREE.CircleGeometry(1, 16).rotateX(-Math.PI / 2);
    const m = new THREE.MeshStandardMaterial({ roughness: 1, flatShading: true });
    const patches = new THREE.InstancedMesh(geo, m, 46);
    const d = new THREE.Object3D();
    const cols = [0x78bd50, 0x93d667, 0x6fb347];
    for (let i = 0; i < 46; i++) {
      const a = rand() * Math.PI * 2, rr = Math.sqrt(rand()) * (R - 3);
      d.position.set(Math.cos(a) * rr, 0.03 + i * 0.0006, Math.sin(a) * rr);
      d.scale.setScalar(between(2, 5.5));
      d.updateMatrix();
      patches.setMatrixAt(i, d.matrix);
      patches.setColorAt(i, new THREE.Color(cols[i % 3]));
    }
    patches.receiveShadow = true;
    island.add(patches);
  }

  // Quảng trường + đường nối tới các bệ điều hướng
  const pathMat = mat(0xecd29a, { roughness: 1 });
  {
    const plaza = new THREE.Mesh(new THREE.CircleGeometry(10.5, 48).rotateX(-Math.PI / 2), pathMat);
    plaza.position.y = 0.06; plaza.receiveShadow = true; island.add(plaza);
    const inner = new THREE.Mesh(new THREE.RingGeometry(5.6, 6.2, 48).rotateX(-Math.PI / 2), mat(0xd9b97a, { roughness: 1 }));
    inner.position.y = 0.075; inner.receiveShadow = true; island.add(inner);
    for (const s of spokes) {
      const len = Math.hypot(s.x2, s.z2);
      const road = new THREE.Mesh(new THREE.PlaneGeometry(4.6, len).rotateX(-Math.PI / 2), pathMat);
      road.position.set(s.x2 / 2, 0.06, s.z2 / 2);
      road.rotation.y = Math.atan2(s.x2, s.z2);
      road.receiveShadow = true; island.add(road);
    }
  }

  // ---------------------------------------------------------------- Cây, đá, hoa
  {
    const spots = [];
    for (let tries = 0; tries < 400 && spots.length < 54; tries++) {
      const a = rand() * Math.PI * 2, rr = between(14, R - 3);
      const x = Math.cos(a) * rr, z = Math.sin(a) * rr, s = between(0.8, 1.5);
      if (!isFree(x, z, 1.4 * s)) continue;
      spots.push({ x, z, s });
      addStatic(x, z, 0.6 * s);
    }
    const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.2, 0.3, 1.5, 6), mat(0x7a4f2c), spots.length);
    const low = new THREE.InstancedMesh(new THREE.ConeGeometry(1.35, 2.3, 7), mat(0xffffff), spots.length);
    const top = new THREE.InstancedMesh(new THREE.ConeGeometry(0.98, 1.9, 7), mat(0xffffff), spots.length);
    const leaf = [0x3f9e4d, 0x57b955, 0x2f8a4a, 0xf0a03c, 0xff8fb1, 0x6cc24a];
    const d = new THREE.Object3D();
    spots.forEach((t, i) => {
      d.rotation.set(0, rand() * 6, 0); d.scale.setScalar(t.s);
      d.position.set(t.x, 0.75 * t.s, t.z); d.updateMatrix(); trunk.setMatrixAt(i, d.matrix);
      d.position.set(t.x, (1.5 + 0.9) * t.s, t.z); d.updateMatrix(); low.setMatrixAt(i, d.matrix);
      d.position.set(t.x, (1.5 + 2.2) * t.s, t.z); d.updateMatrix(); top.setMatrixAt(i, d.matrix);
      const col = new THREE.Color(leaf[Math.floor(rand() * leaf.length)]);
      low.setColorAt(i, col); top.setColorAt(i, col.clone().offsetHSL(0, 0, 0.06));
    });
    for (const m of [trunk, low, top]) { m.castShadow = true; m.receiveShadow = true; island.add(m); }

    // Đá
    const rocks = [];
    for (let tries = 0; tries < 200 && rocks.length < 16; tries++) {
      const a = rand() * Math.PI * 2, rr = between(14, R - 3);
      const x = Math.cos(a) * rr, z = Math.sin(a) * rr, s = between(0.8, 1.9);
      if (!isFree(x, z, 1.2 * s)) continue;
      rocks.push({ x, z, s });
      addStatic(x, z, 0.95 * s);
    }
    const rockMesh = new THREE.InstancedMesh(new THREE.DodecahedronGeometry(1, 0), mat(0x9aa3ad), rocks.length);
    rocks.forEach((r, i) => {
      d.rotation.set(rand() * 3, rand() * 6, rand() * 3);
      d.scale.set(r.s, r.s * 0.75, r.s);
      d.position.set(r.x, 0.5 * r.s, r.z); d.updateMatrix(); rockMesh.setMatrixAt(i, d.matrix);
    });
    shadowed(rockMesh); island.add(rockMesh);

    // Hoa & cỏ nhỏ
    const flowers = new THREE.InstancedMesh(new THREE.OctahedronGeometry(0.17, 0), new THREE.MeshStandardMaterial({ roughness: 0.8, flatShading: true }), 320);
    const fc = [0xffffff, 0xffe066, 0xff9ec4, 0xffa94d, 0xc6a4ff];
    let n = 0;
    d.rotation.set(0, 0, 0);
    for (let tries = 0; tries < 900 && n < 320; tries++) {
      const a = rand() * Math.PI * 2, rr = Math.sqrt(rand()) * (R - 2);
      const x = Math.cos(a) * rr, z = Math.sin(a) * rr;
      if (Math.hypot(x, z) < 11.5 || Math.hypot(x - SPAWN.x, z - SPAWN.z) < 7) continue;
      if (spokes.some((s) => distToSegment(x, z, s) < 2.8) || PADS.some((p) => Math.hypot(x - p.x, z - p.z) < 5)) continue;
      d.position.set(x, 0.17, z); d.scale.setScalar(between(0.7, 1.4)); d.updateMatrix();
      flowers.setMatrixAt(n, d.matrix); flowers.setColorAt(n, new THREE.Color(fc[n % fc.length])); n++;
    }
    flowers.count = n; island.add(flowers);
  }

  // Mây trôi bên dưới đảo
  const clouds = new THREE.Group();
  {
    const cm = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 1, flatShading: true, emissive: 0xbcd4ee, emissiveIntensity: 0.35 });
    const blob = new THREE.IcosahedronGeometry(1, 1);
    for (let i = 0; i < 26; i++) {
      const g = new THREE.Group();
      const parts = 3 + Math.floor(rand() * 3);
      for (let k = 0; k < parts; k++) {
        const m = new THREE.Mesh(blob, cm);
        m.position.set(k * 2.2 - parts, rand() * 0.8, rand() * 1.5);
        m.scale.set(between(2, 3.6), between(1.4, 2.2), between(1.8, 2.8));
        g.add(m);
      }
      const a = rand() * Math.PI * 2, rr = between(R * 0.9, 130);
      g.position.set(Math.cos(a) * rr, between(-26, -9), Math.sin(a) * rr);
      g.scale.setScalar(between(1.2, 2.4));
      g.userData.speed = between(0.01, 0.03);
      clouds.add(g);
    }
    scene.add(clouds);
  }

  // ---------------------------------------------------------------- Biển hiệu
  function makeSign(lines, x, z, rotY, w, h, bg, fg, poleColor = 0x7a4f2c) {
    const g = new THREE.Group();
    const board = new THREE.Mesh(new THREE.BoxGeometry(w, h, 0.3), [
      mat(0x4b3424), mat(0x4b3424), mat(0x4b3424), mat(0x4b3424),
      new THREE.MeshStandardMaterial({ map: textTexture(lines, 1024, Math.round(1024 * h / w), bg, fg), roughness: 0.8 }),
      mat(0x4b3424),
    ]);
    board.position.y = h / 2 + 1.6; shadowed(board);
    g.add(board);
    for (const sx of [-1, 1]) {
      const pole = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.2, h + 1.8, 6), mat(poleColor)));
      pole.position.set(sx * (w / 2 - 0.5), (h + 1.8) / 2 - 0.1, -0.05);
      g.add(pole);
    }
    g.position.set(x, 0, z); g.rotation.y = rotY;
    scene.add(g);
    for (const sx of [-1, 1]) addStatic(x + Math.cos(rotY) * sx * (w / 2 - 0.5), z - Math.sin(rotY) * sx * (w / 2 - 0.5), 0.4);
    return g;
  }

  makeSign([
    { text: 'AutoVideo', size: 190, color: '#fff6e8' },
    { text: 'Tạo video bằng AI', size: 78, weight: 700, color: '#ffc14d' },
  ], 0, -4.5, 0, 11, 4.6, '#1b1738', '#fff6e8');

  // ---------------------------------------------------------------- Bệ điều hướng
  const pads = (isLogin ? [] : PADS).map((p) => {
    const here = p.id === page;
    const g = new THREE.Group();
    g.position.set(p.x, 0, p.z);

    const base = shadowed(new THREE.Mesh(new THREE.CylinderGeometry(3.6, 3.9, 0.35, 32), mat(0x2a2550)), false, true);
    base.position.y = 0.17; g.add(base);

    const ringMat = new THREE.MeshStandardMaterial({ color: p.color, emissive: p.color, emissiveIntensity: here ? 0.2 : 0.9, roughness: 0.4 });
    const ring = new THREE.Mesh(new THREE.TorusGeometry(3.1, 0.14, 8, 48).rotateX(Math.PI / 2), ringMat);
    ring.position.y = 0.38; g.add(ring);

    const fillMat = new THREE.MeshBasicMaterial({ color: p.color, transparent: true, opacity: here ? 0.15 : 0.6 });
    const fill = new THREE.Mesh(new THREE.CircleGeometry(3.0, 32).rotateX(-Math.PI / 2), fillMat);
    fill.position.y = 0.4; fill.scale.setScalar(0.001); g.add(fill);

    const beam = new THREE.Mesh(
      new THREE.CylinderGeometry(2.9, 3.1, 11, 24, 1, true),
      new THREE.MeshBasicMaterial({ color: p.color, transparent: true, opacity: here ? 0.05 : 0.16, depthWrite: false, side: THREE.DoubleSide }));
    beam.position.y = 5.6; g.add(beam);

    const label = new THREE.Sprite(new THREE.SpriteMaterial({
      map: textTexture([
        { text: p.label, size: 118, color: '#fff6e8' },
        { text: here ? 'Bạn đang ở đây' : 'Lái xe vào để mở', size: 52, weight: 700, color: here ? '#bdb6d8' : '#ffd88a' },
      ], 768, 288, 'rgba(27,23,56,0.92)', '#fff6e8', 56),
      transparent: true, depthWrite: false, fog: false,
    }));
    label.scale.set(8, 3, 1);
    label.position.y = 7.2; g.add(label);
    // gạch màu dưới tên
    const tag = new THREE.Mesh(new THREE.BoxGeometry(5.4, 0.14, 0.14), new THREE.MeshBasicMaterial({ color: p.color }));
    tag.position.y = 5.5; g.add(tag);

    scene.add(g);
    return { ...p, here, group: g, ring, fill, fillMat, beam, label, dwell: 0, done: false };
  });

  // ---------------------------------------------------------------- Vật thể đẩy được (nón, thùng)
  const bodies = [];
  function addBody(mesh, x, z, r, mass) {
    mesh.position.set(x, 0, z);
    scene.add(mesh);
    bodies.push({ mesh, x, z, y: 0, vx: 0, vz: 0, vy: 0, r, mass, rot: rand() * 6, w: 0, spinX: 0, tilt: 0, homeX: x, homeZ: z, fall: false });
  }
  {
    const coneMat = mat(0xff7a1f), stripeMat = mat(0xfff6e8), baseMat = mat(0x2a2550);
    const coneGeo = new THREE.ConeGeometry(0.42, 1.15, 12);
    const bandGeo = new THREE.CylinderGeometry(0.27, 0.32, 0.22, 12);
    const plate = new THREE.BoxGeometry(0.95, 0.1, 0.95);
    for (let i = 0; i < 12; i++) {
      const g = new THREE.Group();
      const c = shadowed(new THREE.Mesh(coneGeo, coneMat)); c.position.y = 0.67;
      const b = shadowed(new THREE.Mesh(bandGeo, stripeMat)); b.position.y = 0.62;
      const p = shadowed(new THREE.Mesh(plate, baseMat)); p.position.y = 0.05;
      g.add(c, b, p);
      addBody(g, -23 + (i % 4) * 2.6, 3 + Math.floor(i / 4) * 2.6, 0.55, 1);
    }
    const crateGeo = new THREE.BoxGeometry(1.3, 1.3, 1.3);
    const crateMats = [0xc98a4b, 0xb8773a, 0xd9a05f].map((c) => mat(c));
    for (let i = 0; i < 9; i++) {
      const m = shadowed(new THREE.Mesh(crateGeo, crateMats[i % 3])); m.position.y = 0.65;
      const g = new THREE.Group(); g.add(m);
      addBody(g, 17 + (i % 3) * 1.5, 6 + Math.floor(i / 3) * 1.5, 0.9, 2);
    }
    for (let i = 0; i < 5; i++) {      // vài quả bóng nhẹ
      const m = shadowed(new THREE.Mesh(new THREE.IcosahedronGeometry(0.75, 1), mat([0xff5a8a, 0x5ac8ff, 0xffd34d, 0x7cf08a, 0xb48cff][i])));
      m.position.y = 0.75;
      const g = new THREE.Group(); g.add(m);
      addBody(g, -12 + i * 2.2, 20 + (i % 2) * 2, 0.8, 0.6);
    }
  }
  for (const b of bodies) occupied.push({ x: b.x, z: b.z, r: 2 });

  // ---------------------------------------------------------------- Chiếc xe
  const car = new THREE.Group();
  const carBody = new THREE.Group();
  car.add(carBody);
  scene.add(car);
  const wheelsFront = [], wheelSpinners = [];
  {
    const paint = mat(0xff5a36, { roughness: 0.55 });
    const dark = mat(0x2a2550);
    const glass = mat(0x27405e, { roughness: 0.25 });
    const add = (geo, m, x, y, z) => { const o = shadowed(new THREE.Mesh(geo, m)); o.position.set(x, y, z); carBody.add(o); return o; };

    add(new THREE.BoxGeometry(1.9, 0.55, 3.8), paint, 0, 0.78, 0);
    add(new THREE.BoxGeometry(1.7, 0.18, 1.2), paint, 0, 1.1, 1.15);                       // nắp capo
    add(new THREE.BoxGeometry(1.6, 0.55, 1.7), glass, 0, 1.3, -0.35);                      // kính cabin
    add(new THREE.BoxGeometry(1.7, 0.14, 1.9), paint, 0, 1.62, -0.35);                     // nóc
    add(new THREE.BoxGeometry(2.0, 0.22, 0.35), dark, 0, 0.55, 1.92);                      // cản trước
    add(new THREE.BoxGeometry(2.0, 0.22, 0.35), dark, 0, 0.55, -1.92);                     // cản sau
    add(new THREE.BoxGeometry(1.9, 0.08, 0.5), paint, 0, 1.45, -1.78);                     // cánh gió
    for (const sx of [-0.7, 0.7]) add(new THREE.BoxGeometry(0.1, 0.35, 0.1), dark, sx, 1.25, -1.72);
    const lightOn = new THREE.MeshStandardMaterial({ color: 0xfff3b0, emissive: 0xffe58a, emissiveIntensity: 1.6 });
    const lightRed = new THREE.MeshStandardMaterial({ color: 0xff3b3b, emissive: 0xff2020, emissiveIntensity: 1.1 });
    for (const sx of [-0.65, 0.65]) {
      add(new THREE.BoxGeometry(0.42, 0.22, 0.1), lightOn, sx, 0.85, 1.92);
      add(new THREE.BoxGeometry(0.42, 0.2, 0.1), lightRed, sx, 0.85, -1.92);
    }

    const tireGeo = new THREE.CylinderGeometry(0.44, 0.44, 0.34, 16).rotateZ(Math.PI / 2);
    const hubGeo = new THREE.CylinderGeometry(0.22, 0.22, 0.38, 8).rotateZ(Math.PI / 2);
    const tireMat = mat(0x1b1a24), hubMat = mat(0xd8d4e6);
    for (const [sx, sz] of [[-1, 1], [1, 1], [-1, -1], [1, -1]]) {
      const steer = new THREE.Group();
      steer.position.set(sx * 1.0, 0.44, sz * 1.25);
      const spin = new THREE.Group();
      const tire = shadowed(new THREE.Mesh(tireGeo, tireMat));
      const hub = new THREE.Mesh(hubGeo, hubMat);
      const spoke = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.1, 0.1), hubMat);   // để thấy bánh quay
      spoke.position.x = sx * 0.18;
      spin.add(tire, hub, spoke);
      steer.add(spin);
      carBody.add(steer);
      wheelSpinners.push(spin);
      if (sz > 0) wheelsFront.push(steer);
    }
  }

  const S = {
    x: SPAWN.x, z: SPAWN.z, y: 0, vx: 0, vz: 0, vy: 0, heading: SPAWN.heading,
    steer: 0, pitch: 0, roll: 0, prevVf: 0, falling: false, wheel: 0,
  };
  function resetCar() {
    Object.assign(S, { x: SPAWN.x, z: SPAWN.z, y: 0, vx: 0, vz: 0, vy: 0, heading: SPAWN.heading, steer: 0, falling: false });
    for (const b of bodies) {
      Object.assign(b, { x: b.homeX, z: b.homeZ, y: 0, vx: 0, vz: 0, vy: 0, w: 0, fall: false, spinX: 0 });
      b.mesh.visible = true;
    }
    snapCamera();
  }

  // ---------------------------------------------------------------- Bụi
  const dust = [];
  {
    const geo = new THREE.IcosahedronGeometry(0.3, 0);
    for (let i = 0; i < 36; i++) {
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xf6ead2, transparent: true, opacity: 0, depthWrite: false }));
      m.visible = false; scene.add(m);
      dust.push({ m, life: 0, vx: 0, vz: 0 });
    }
  }
  let dustTimer = 0, dustIdx = 0;
  function puff(x, z, vx, vz) {
    const p = dust[dustIdx++ % dust.length];
    p.life = 1; p.vx = vx * 0.2 + between(-1, 1); p.vz = vz * 0.2 + between(-1, 1);
    p.m.position.set(x, 0.3, z); p.m.visible = true;
  }

  // ---------------------------------------------------------------- Điều khiển
  const keys = { up: false, down: false, left: false, right: false, brake: false };
  const MAP = {
    ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down',
    ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right', Space: 'brake',
  };
  const body = document.body;
  const driving = () => body.classList.contains('driving');

  function setDriving(on) {
    body.classList.toggle('driving', on);
    if (on && document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
    if (!on) for (const k in keys) keys[k] = false;
    toggleBtn.textContent = on ? 'Mở bảng điều khiển' : (isLogin ? 'Lái thử xe' : 'Lái xe');
    toggleBtn.append(Object.assign(document.createElement('kbd'), { textContent: 'Esc' }));
  }

  // Giao diện nổi: nút chuyển chế độ, gợi ý phím, nút cảm ứng
  const hud = document.createElement('div');
  hud.id = 'hud';
  hud.innerHTML = `
    <div class="hud-hint" aria-hidden="true">
      <span class="keys"><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd></span><span>hoặc</span>
      <span class="keys"><kbd>←</kbd><kbd>↑</kbd><kbd>↓</kbd><kbd>→</kbd></span><span>lái xe</span>
      <span class="sep"></span><kbd class="wide">Space</kbd><span>phanh</span>
      <span class="sep"></span><kbd>R</kbd><span>về chỗ cũ</span>
    </div>
    <div class="touch" aria-hidden="true">
      <div class="pad-lr"><button data-k="left">◀</button><button data-k="right">▶</button></div>
      <div class="pad-ud"><button data-k="up">▲</button><button data-k="down">▼</button></div>
    </div>`;
  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button'; toggleBtn.id = 'drive-toggle'; toggleBtn.className = 'btn btn-primary';
  hud.append(toggleBtn);
  document.body.append(hud);
  toggleBtn.addEventListener('click', () => setDriving(!driving()));
  setDriving(false);

  hud.querySelectorAll('.touch button').forEach((b) => {
    const k = b.dataset.k;
    const set = (v) => (e) => { e.preventDefault(); keys[k] = v; };
    b.addEventListener('pointerdown', set(true));
    for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) b.addEventListener(ev, set(false));
  });

  window.addEventListener('keydown', (e) => {
    if (e.code === 'Escape' && !document.querySelector('dialog[open]')) {
      e.preventDefault(); setDriving(!driving()); return;
    }
    if (!driving() || e.ctrlKey || e.metaKey || e.altKey) return;
    if (MAP[e.code]) { keys[MAP[e.code]] = true; e.preventDefault(); }
    else if (e.code === 'KeyR') resetCar();
  });
  window.addEventListener('keyup', (e) => { if (MAP[e.code]) keys[MAP[e.code]] = false; });
  window.addEventListener('blur', () => { for (const k in keys) keys[k] = false; });

  // ---------------------------------------------------------------- Mô phỏng
  const CAR_CIRCLES = [-1.0, 0, 1.0];
  const CAR_R = 0.98, CAR_MASS = 8;

  function collideCar(dt) {
    const fx = Math.sin(S.heading), fz = Math.cos(S.heading);
    for (const off of CAR_CIRCLES) {
      const cx = S.x + fx * off, cz = S.z + fz * off;
      for (const o of statics) {
        const dx = cx - o.x, dz = cz - o.z, min = CAR_R + o.r, d2 = dx * dx + dz * dz;
        if (d2 >= min * min) continue;
        const d = Math.sqrt(d2) || 0.001, nx = dx / d, nz = dz / d, push = min - d;
        S.x += nx * push; S.z += nz * push;
        const vn = S.vx * nx + S.vz * nz;
        if (vn < 0) { S.vx -= 1.25 * vn * nx; S.vz -= 1.25 * vn * nz; S.vx *= 0.92; S.vz *= 0.92; }
      }
      for (const b of bodies) {
        if (b.fall) continue;
        const dx = cx - b.x, dz = cz - b.z, min = CAR_R + b.r, d2 = dx * dx + dz * dz;
        if (d2 >= min * min || b.y > 0.9) continue;
        const d = Math.sqrt(d2) || 0.001, nx = dx / d, nz = dz / d, push = min - d;
        const share = b.mass / (b.mass + CAR_MASS);
        b.x -= nx * push * (1 - share); b.z -= nz * push * (1 - share);
        S.x += nx * push * share; S.z += nz * push * share;
        const rel = (S.vx - b.vx) * nx + (S.vz - b.vz) * nz;
        if (rel < 0) {
          const j = (-(1.5) * rel) / (1 / CAR_MASS + 1 / b.mass);
          S.vx += nx * j / CAR_MASS; S.vz += nz * j / CAR_MASS;
          b.vx -= nx * j / b.mass; b.vz -= nz * j / b.mass;
          b.w += (rand() - 0.5) * j * 0.6;
          if (j > 2.5 && b.y <= 0.01) { b.vy = Math.min(2 + j * 0.25, 7); b.spinX = (rand() - 0.5) * 12; }
        }
      }
    }
  }

  function stepCar(dt) {
    const throttle = (keys.up ? 1 : 0) - (keys.down ? 1 : 0);
    const steerIn = (keys.right ? 1 : 0) - (keys.left ? 1 : 0);

    if (S.falling) {
      S.vy -= 28 * dt; S.y += S.vy * dt;
      S.x += S.vx * dt; S.z += S.vz * dt;
      carBody.rotation.z += dt * 2.2; carBody.rotation.x += dt * 1.1;
      if (S.y < -28) { carBody.rotation.set(0, 0, 0); resetCar(); }
      return;
    }

    let fx = Math.sin(S.heading), fz = Math.cos(S.heading);
    let rx = -Math.cos(S.heading), rz = Math.sin(S.heading);
    let vf = S.vx * fx + S.vz * fz;
    let vl = S.vx * rx + S.vz * rz;

    // Ga / số lùi / phanh
    if (throttle > 0) vf += (vf < 0 ? 38 : 17) * dt;
    else if (throttle < 0) vf -= (vf > 0 ? 38 : 10) * dt;
    else vf *= Math.exp(-0.9 * dt);
    if (keys.brake) vf *= Math.exp(-4.5 * dt);
    vf *= Math.exp(-0.12 * dt);
    vf = Math.max(-8, Math.min(19, vf));

    // Bám đường; giữ Space để trượt
    vl *= Math.exp(-(keys.brake ? 1.6 : 7.5) * dt);

    // Lái (chỉ quay được khi xe đang chạy)
    S.steer += (steerIn - S.steer) * Math.min(1, dt * 9);
    const speedFactor = Math.max(-1, Math.min(1, vf / 5)) * (1 - Math.min(0.45, Math.abs(vf) / 40));
    S.heading -= S.steer * 2.3 * speedFactor * (keys.brake ? 1.35 : 1) * dt;

    fx = Math.sin(S.heading); fz = Math.cos(S.heading);
    rx = -Math.cos(S.heading); rz = Math.sin(S.heading);
    S.vx = fx * vf + rx * vl; S.vz = fz * vf + rz * vl;
    S.x += S.vx * dt; S.z += S.vz * dt;

    collideCar(dt);

    // Bánh xe, nghiêng thân xe
    S.wheel += (vf * dt) / 0.44;
    wheelSpinners.forEach((w) => { w.rotation.x = S.wheel; });
    wheelsFront.forEach((w) => { w.rotation.y = -S.steer * 0.45; });
    const accel = (vf - S.prevVf) / Math.max(dt, 1e-3);
    S.prevVf = vf;
    S.pitch += (Math.max(-0.07, Math.min(0.07, -accel * 0.004)) - S.pitch) * Math.min(1, dt * 6);
    S.roll += (Math.max(-0.1, Math.min(0.1, S.steer * vf * 0.006)) - S.roll) * Math.min(1, dt * 6);
    carBody.rotation.set(S.pitch, 0, S.roll);

    // Bụi khi tăng tốc hoặc trượt
    dustTimer -= dt;
    if (dustTimer <= 0 && (Math.abs(vl) > 2.4 || (throttle > 0 && vf < 7 && vf > 1) || (keys.brake && Math.abs(vf) > 5))) {
      dustTimer = 0.04;
      for (const sx of [-0.85, 0.85]) puff(S.x - fx * 1.3 + rx * sx, S.z - fz * 1.3 + rz * sx, -S.vx, -S.vz);
    }

    if (Math.hypot(S.x, S.z) > R) { S.falling = true; S.vy = 0; }
  }

  function stepBodies(dt) {
    const damp = Math.exp(-1.9 * dt);
    for (const b of bodies) {
      if (b.fall) {
        b.vy -= 28 * dt; b.y += b.vy * dt;
        if (b.y < -30) { Object.assign(b, { x: b.homeX, z: b.homeZ, y: 0, vx: 0, vz: 0, vy: 0, w: 0, fall: false }); }
      } else {
        b.x += b.vx * dt; b.z += b.vz * dt;
        b.vx *= damp; b.vz *= damp; b.w *= Math.exp(-2.5 * dt);
        for (const o of statics) {
          const dx = b.x - o.x, dz = b.z - o.z, min = b.r + o.r, d2 = dx * dx + dz * dz;
          if (d2 >= min * min) continue;
          const d = Math.sqrt(d2) || 0.001, nx = dx / d, nz = dz / d;
          b.x = o.x + nx * min; b.z = o.z + nz * min;
          const vn = b.vx * nx + b.vz * nz;
          if (vn < 0) { b.vx -= 1.6 * vn * nx; b.vz -= 1.6 * vn * nz; }
        }
        b.vy -= 28 * dt; b.y += b.vy * dt;
        if (b.y <= 0) { b.y = 0; if (b.vy < -3) b.vy *= -0.3; else b.vy = 0; b.spinX *= 0.5; }
        b.rot += b.w * dt;
        if (Math.hypot(b.x, b.z) > R) b.fall = true;
      }
      b.mesh.position.set(b.x, b.y, b.z);
      b.mesh.rotation.y = b.rot;
      if (b.y > 0.02) b.mesh.rotation.x += b.spinX * dt;
      else b.mesh.rotation.x *= 0.7;
    }
  }

  function stepPads(dt) {
    const now = performance.now() / 1000;
    for (const p of pads) {
      const near = driving() && !p.here && !p.done && !S.falling && Math.hypot(S.x - p.x, S.z - p.z) < 3.2;
      p.dwell = near ? Math.min(1.25, p.dwell + dt) : Math.max(0, p.dwell - dt * 2.5);
      const k = p.dwell / 1.25;
      p.fill.scale.setScalar(Math.max(0.001, k));
      p.ring.material.emissiveIntensity = (p.here ? 0.2 : 0.8) + (near ? 0.8 : 0) + (p.here ? 0 : Math.sin(now * 3 + p.x) * 0.15);
      p.label.position.y = 7.2 + Math.sin(now * 1.6 + p.x) * 0.25;
      if (k >= 1 && !p.done) {
        p.done = true;
        if (p.action === 'logout') {
          document.getElementById('logout')?.click();
        } else {
          body.classList.add('leaving');
          setTimeout(() => { location.href = p.href; }, 450);
        }
        setTimeout(() => { p.done = false; }, 3000);
      }
    }
  }

  // ---------------------------------------------------------------- Camera
  let shiftX = 0, shiftY = 0;
  let panelEl = document.querySelector('main');
  function shiftTarget() {
    if (driving() || isLogin || !panelEl) return [0, 0];
    const w = innerWidth, h = innerHeight;
    if (w >= 900) return [(panelEl.offsetWidth + 24) / 2, 0];
    return [0, h * 0.2];
  }
  function applyView() {
    camera.setViewOffset(innerWidth, innerHeight, -shiftX, shiftY, innerWidth, innerHeight);
  }
  function snapCamera() {
    camLook.set(S.x, 0, S.z);
    camPos.copy(camLook).add(camOffset);
  }
  function stepCamera(dt) {
    const speed = Math.hypot(S.vx, S.vz);
    const k = 1 - Math.exp(-4 * dt);
    camLook.x += (S.x - camLook.x) * k; camLook.z += (S.z - camLook.z) * k;
    camLook.y += ((S.falling ? S.y * 0.5 : 0) - camLook.y) * k;
    const zoom = 1 + speed * 0.012;
    camPos.set(camLook.x + camOffset.x * zoom, camLook.y + camOffset.y * zoom, camLook.z + camOffset.z * zoom);
    camera.position.copy(camPos);
    camera.lookAt(camLook);
    const [tx, ty] = shiftTarget();
    const ks = 1 - Math.exp(-5 * dt);
    shiftX += (tx - shiftX) * ks; shiftY += (ty - shiftY) * ks;
    applyView();
    sun.position.set(camLook.x + sunOffset.x, sunOffset.y, camLook.z + sunOffset.z);
    sun.target.position.set(camLook.x, 0, camLook.z);
  }

  function resize() {
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight;
    camera.fov = innerWidth < 700 ? 42 : 32;
    camera.updateProjectionMatrix();
    panelEl = document.querySelector('main');
  }
  addEventListener('resize', resize);
  resize();
  snapCamera();

  // ---------------------------------------------------------------- Vòng lặp
  let last = performance.now(), first = true;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function frame(t) {
    requestAnimationFrame(frame);
    const dt = Math.min(0.05, (t - last) / 1000);
    last = t;

    if (!driving()) for (const k in keys) keys[k] = false;
    stepCar(dt);
    stepBodies(dt);
    stepPads(dt);

    car.position.set(S.x, S.y, S.z);
    car.rotation.y = S.heading;

    for (const p of dust) {
      if (!p.m.visible) continue;
      p.life -= dt * 1.6;
      if (p.life <= 0) { p.m.visible = false; continue; }
      p.m.position.x += p.vx * dt; p.m.position.z += p.vz * dt; p.m.position.y += dt * 0.8;
      p.m.scale.setScalar(1 + (1 - p.life) * 2.2);
      p.m.material.opacity = p.life * 0.55;
    }
    if (!reduce) clouds.children.forEach((c) => {
      const a = c.userData.speed * dt;
      const x = c.position.x, z = c.position.z;
      c.position.x = x * Math.cos(a) - z * Math.sin(a);
      c.position.z = x * Math.sin(a) + z * Math.cos(a);
    });

    stepCamera(dt);
    renderer.render(scene, camera);

    if (first) { first = false; requestAnimationFrame(() => body.classList.add('world-ready')); }
  }
  requestAnimationFrame(frame);
}
