// Game page. game.py streams the camera on /video and state on /events.
// The page only draws; all game logic lives in Python.

const video = document.querySelector('#video');
const canvas = document.querySelector('#overlay');
const ctx = canvas.getContext('2d');
const swingEl = document.querySelector('#swing');
const connEl = document.querySelector('#conn');
const boardEl = document.querySelector('#board');
const laneEl = document.querySelector('#lane');
const fpsEl = document.querySelector('#fps');
const bannerEl = document.querySelector('#banner');
const resultEl = document.querySelector('#result');
const streakEl = document.querySelector('#streak');
const recordEl = document.querySelector('#record');
const levelEl = document.querySelector('#level');
const handsEl = document.querySelector('#hands');

let state = { zones: 3, zone: null, box: null, swing: null, fps: 0, phase: 'waiting', ball: null,
              result: null };
let lastSwingId = null, lastResultId = null;
let ballId = null, ballStart = 0;  // performance.now() at launch, synced from ball.t
let trail = [], ovTrail = [];  // recent ball positions, split view and overlay view

// Two views: 'overlay' (ball on the camera) and 'split' (camera + bird's-eye table).
// T switches; the choice is remembered in this browser.
let view = 'overlay';
try { view = localStorage.getItem('view') || view; } catch (e) {}
document.body.dataset.view = view;
document.addEventListener('keydown', e => {
  if (e.key !== 't' && e.key !== 'T') return;
  view = view === 'overlay' ? 'split' : 'overlay';
  document.body.dataset.view = view;
  try { localStorage.setItem('view', view); } catch (e) {}
});

// Paddle hand: picked with the LEFT/RIGHT buttons between rallies, remembered in this
// browser, and sent to Python on every (re)connect so a restarted game.py gets it back.
let hand = 'right';
try { hand = localStorage.getItem('hand') || hand; } catch (e) {}
function sendHand() {
  fetch('/hand', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                   body: JSON.stringify({ hand }) }).catch(() => {});
}
function showHand() {
  handsEl.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.hand === hand));
}
handsEl.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
  hand = b.dataset.hand;
  try { localStorage.setItem('hand', hand); } catch (e) {}
  showHand();
  sendHand();
}));
showHand();

// --- State from Python -------------------------------------------------------
const events = new EventSource('/events');
events.onopen = () => {
  connEl.textContent = 'live';
  connEl.classList.add('on');
  sendHand();
};
events.onerror = () => {
  connEl.textContent = 'reconnecting…';
  connEl.classList.remove('on');
  boardEl.textContent = 'board: ?';
  boardEl.classList.remove('on');
};
events.onmessage = e => {
  state = JSON.parse(e.data);
  fpsEl.textContent = `${state.fps.toFixed(0)} fps  pose ${state.pose_ms.toFixed(0)} ms`;
  boardEl.textContent = state.board ? 'board: live' : 'board: offline';
  boardEl.classList.toggle('on', state.board);
  // Where the lane comes from: the YOLO paddle, or the paddle-hand wrist as a backup
  laneEl.textContent = `lane: ${state.lane_src || 'none'}`;
  laneEl.classList.toggle('on', state.lane_src === 'paddle');
  laneEl.classList.toggle('backup', state.lane_src === 'wrist');
  // Pop-ups fire when an id changes, but not for the old value seen on page load
  if (state.swing && state.swing.id !== lastSwingId) {
    if (lastSwingId !== null) pop(swingEl, state.swing.name.toUpperCase());
    lastSwingId = state.swing.id;
  }
  if (state.result && state.result.id !== lastResultId) {
    if (lastResultId !== null) {
      resultEl.classList.toggle('good', state.result.text !== 'MISS');
      pop(resultEl, state.result.text);
    }
    lastResultId = state.result.id;
  }
  setHud(streakEl, state.streak);
  setHud(recordEl, state.record);
  setHud(levelEl, state.level);
  bannerEl.classList.toggle('hidden', state.phase !== 'waiting');
  handsEl.classList.toggle('hidden', state.phase !== 'waiting');
  if (state.ball && state.ball.id !== ballId) {
    ballId = state.ball.id;
    ballStart = performance.now() - state.ball.t * 1000;
    trail = [];
    ovTrail = [];
  }
};

// HUD value that bumps when it changes
function setHud(el, value) {
  if (el.textContent === String(value)) return;
  el.textContent = value;
  el.classList.remove('bump');
  void el.offsetWidth;
  el.classList.add('bump');
}

function pop(el, text) {
  el.textContent = text;
  el.classList.remove('on');
  void el.offsetWidth;  // restart the CSS animation
  el.classList.add('on');
}

// --- Drawing (every animation frame, on top of the video) ---------------------
function resize() {
  const r = video.getBoundingClientRect();
  canvas.width = r.width * devicePixelRatio;
  canvas.height = r.height * devicePixelRatio;
}
new ResizeObserver(resize).observe(video);

function draw() {
  const w = canvas.width, h = canvas.height, n = state.zones;
  ctx.clearRect(0, 0, w, h);

  // Paddle's zone glows (not on levels with glow off)
  if (state.zone !== null && state.glow !== false) {
    const x = state.zone * w / n;
    const g = ctx.createLinearGradient(0, h, 0, 0);
    g.addColorStop(0, 'rgba(57, 255, 136, 0.35)');
    g.addColorStop(1, 'rgba(57, 255, 136, 0.02)');
    ctx.fillStyle = g;
    ctx.fillRect(x, 0, w / n, h);
  }

  // Overlay view: incoming ball's lane pulses, and the table is drawn in perspective
  const ball = state.ball;
  if (view === 'overlay') {
    if (ball && ball.dir === 'in' && state.glow !== false) {
      const pulse = 0.12 + 0.1 * Math.sin(performance.now() / 120);
      const g = ctx.createLinearGradient(0, h, 0, 0);
      g.addColorStop(0, `rgba(255, 179, 71, ${pulse * 2})`);
      g.addColorStop(1, 'rgba(255, 179, 71, 0)');
      ctx.fillStyle = g;
      ctx.fillRect(ball.to * w / n, 0, w / n, h);
    }
    drawPerspectiveTable(w, h);
  }

  // Zone dividers (not on levels with dividers off)
  ctx.strokeStyle = 'rgba(0, 229, 255, 0.6)';
  ctx.lineWidth = 2 * devicePixelRatio;
  ctx.setLineDash([12 * devicePixelRatio, 10 * devicePixelRatio]);
  for (let k = 1; k < n && state.dividers !== false; k++) {
    ctx.beginPath();
    ctx.moveTo(k * w / n, 0);
    ctx.lineTo(k * w / n, h);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  if (state.pose) drawSkeleton(w, h);

  // AprilTag outline with its ID
  if (state.tag) {
    const c = state.tag.corners.map(([x, y]) => [x * w, y * h]);
    ctx.strokeStyle = '#ff3d9a';
    ctx.lineWidth = 3 * devicePixelRatio;
    ctx.beginPath();
    c.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.stroke();
    ctx.fillStyle = '#ff3d9a';
    ctx.font = `${12 * devicePixelRatio}px 'Press Start 2P', monospace`;
    ctx.textAlign = 'left';
    const left = Math.min(...c.map(p => p[0])), top = Math.min(...c.map(p => p[1]));
    ctx.fillText(`TAG ${state.tag.id}`, left, top - 8 * devicePixelRatio);
  }

  // Paddle box
  if (state.box) {
    const [x1, y1, x2, y2] = state.box;
    ctx.strokeStyle = '#39ff88';
    ctx.lineWidth = 3 * devicePixelRatio;
    ctx.shadowColor = '#39ff88';
    ctx.shadowBlur = 12 * devicePixelRatio;
    ctx.strokeRect(x1 * w, y1 * h, (x2 - x1) * w, (y2 - y1) * h);
    ctx.shadowBlur = 0;
  }

  if (view === 'overlay') drawOverlayBall(w, h, n);
  else drawTable();
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);

// --- Body pose: neon skeleton, the paddle arm bright orange ----------------------
// Same lines as SKELETON in pose.py. Points are normalized, in the mirrored view.
const SKELETON = [
  ['left_shoulder', 'right_shoulder'], ['left_hip', 'right_hip'],
  ['left_shoulder', 'left_hip'], ['right_shoulder', 'right_hip'],
  ['left_shoulder', 'left_elbow'], ['left_elbow', 'left_wrist'],
  ['right_shoulder', 'right_elbow'], ['right_elbow', 'right_wrist'],
];

function drawSkeleton(w, h) {
  const pose = state.pose, px = devicePixelRatio;
  const paddle = state.hand || hand;  // Python's choice is what the game uses
  const other = paddle === 'left' ? 'right' : 'left';
  const side = (a, b) => (a.startsWith(paddle) && b.startsWith(paddle) ? 'paddle'
                         : a.startsWith(other) && b.startsWith(other) ? 'other' : 'body');
  const STYLE = {
    body:   { color: 'rgba(242, 242, 247, 0.45)', width: 3, glow: 0 },
    other:  { color: 'rgba(0, 229, 255, 0.7)', width: 4, glow: 8 },
    paddle: { color: '#ff8c1a', width: 6, glow: 18 },
  };
  ctx.lineCap = 'round';
  // Body first, paddle arm last so it sits on top
  for (const part of ['body', 'other', 'paddle']) {
    const s = STYLE[part];
    ctx.strokeStyle = s.color;
    ctx.lineWidth = s.width * px;
    ctx.shadowColor = s.color;
    ctx.shadowBlur = s.glow * px;
    for (const [a, b] of SKELETON) {
      if (side(a, b) !== part || !pose[a] || !pose[b]) continue;
      ctx.beginPath();
      ctx.moveTo(pose[a][0] * w, pose[a][1] * h);
      ctx.lineTo(pose[b][0] * w, pose[b][1] * h);
      ctx.stroke();
    }
  }
  for (const [name, s, r] of [[`${other}_wrist`, STYLE.other, 6], [`${paddle}_wrist`, STYLE.paddle, 10]]) {
    if (!pose[name]) continue;
    ctx.fillStyle = s.color;
    ctx.shadowColor = s.color;
    ctx.shadowBlur = s.glow * px;
    ctx.beginPath();
    ctx.arc(pose[name][0] * w, pose[name][1] * h, r * px, 0, 2 * Math.PI);
    ctx.fill();
  }
  ctx.shadowBlur = 0;
  ctx.lineCap = 'butt';
}

// --- Table, bird's-eye view: opponent at the top, you at the bottom -----------
const tableCanvas = document.querySelector('#table');
const tctx = tableCanvas.getContext('2d');
const TABLE_RATIO = 2.74 / 1.525;  // real table, length / width

new ResizeObserver(() => {
  const r = tableCanvas.getBoundingClientRect();
  tableCanvas.width = r.width * devicePixelRatio;
  tableCanvas.height = r.height * devicePixelRatio;
}).observe(tableCanvas);

// Table rectangle inside the canvas, leaving room for labels and the paddle marker
function tableRect() {
  const w = tableCanvas.width, h = tableCanvas.height;
  const th = Math.min(h * 0.8, w * 0.8 * TABLE_RATIO);
  const tw = th / TABLE_RATIO;
  return { x: (w - tw) / 2, y: (h - th) / 2, w: tw, h: th };
}

function drawTable() {
  const w = tableCanvas.width, h = tableCanvas.height, n = state.zones;
  const t = tableRect();
  const px = devicePixelRatio;
  tctx.clearRect(0, 0, w, h);

  // Surface
  tctx.fillStyle = '#0d2a5c';
  tctx.fillRect(t.x, t.y, t.w, t.h);

  // Your lane glows where the paddle is (not on levels with glow off)
  if (state.zone !== null && state.glow !== false) {
    tctx.fillStyle = 'rgba(57, 255, 136, 0.25)';
    tctx.fillRect(t.x + state.zone * t.w / n, t.y + t.h / 2, t.w / n, t.h / 2);
  }

  // Incoming ball: its target lane pulses and the rest of its path is dotted
  // (neither on levels with glow off)
  const ball = state.ball;
  if (ball && ball.dir === 'in' && state.glow !== false) {
    const pulse = 0.25 + 0.2 * Math.sin(performance.now() / 120);
    tctx.fillStyle = `rgba(255, 179, 71, ${pulse})`;
    tctx.fillRect(t.x + ball.to * t.w / n, t.y + t.h / 2, t.w / n, t.h / 2);

    const now = ballProgress(ball);
    tctx.fillStyle = 'rgba(255, 179, 71, 0.7)';
    for (let p = Math.ceil(now * 40) / 40; p <= 1; p += 1 / 40) {
      const { x, y } = ballGround(ball, p, t, n);
      tctx.beginPath();
      tctx.arc(x, y - ballLift(ball, p, t), 2 * px, 0, 2 * Math.PI);
      tctx.fill();
    }
  }

  // Lane dividers on your half (not on levels with dividers off)
  tctx.strokeStyle = 'rgba(0, 229, 255, 0.6)';
  tctx.lineWidth = 2 * px;
  tctx.setLineDash([8 * px, 8 * px]);
  for (let k = 1; k < n && state.dividers !== false; k++) {
    const x = t.x + k * t.w / n;
    tctx.beginPath();
    tctx.moveTo(x, t.y + t.h / 2);
    tctx.lineTo(x, t.y + t.h);
    tctx.stroke();
  }
  tctx.setLineDash([]);

  // Border
  tctx.strokeStyle = '#f2f2f7';
  tctx.lineWidth = 3 * px;
  tctx.strokeRect(t.x, t.y, t.w, t.h);

  // Net, sticking out a little past the sides
  tctx.strokeStyle = '#00e5ff';
  tctx.lineWidth = 4 * px;
  tctx.shadowColor = '#00e5ff';
  tctx.shadowBlur = 10 * px;
  tctx.beginPath();
  tctx.moveTo(t.x - 8 * px, t.y + t.h / 2);
  tctx.lineTo(t.x + t.w + 8 * px, t.y + t.h / 2);
  tctx.stroke();
  tctx.shadowBlur = 0;

  // Labels
  tctx.fillStyle = '#8a8aa0';
  tctx.font = `${9 * px}px 'Press Start 2P', monospace`;
  tctx.textAlign = 'center';
  tctx.fillText('OPPONENT', w / 2, t.y - 12 * px);

  // Your paddle, just below your end of the table
  if (state.zone !== null) {
    const pw = t.w / n * 0.6, ph = 8 * px;
    const cx = t.x + (state.zone + 0.5) * t.w / n;
    tctx.fillStyle = '#39ff88';
    tctx.shadowColor = '#39ff88';
    tctx.shadowBlur = 14 * px;
    tctx.beginPath();
    tctx.roundRect(cx - pw / 2, t.y + t.h + 10 * px, pw, ph, ph / 2);
    tctx.fill();
    tctx.shadowBlur = 0;
  } else {
    tctx.fillText('NO PADDLE', w / 2, t.y + t.h + 22 * px);
  }

  drawBall(t, n, px);
}

// p is progress along the flight: 0 at launch, 1 on arrival.
const BOUNCE_AT = 0.75;  // hits and returns bounce once, 3/4 of the way, on the receiver's half

// Height 0..1 above the table.
function ballHeight(kind, p) {
  if (kind === 'serve') {
    // Up at your paddle, bounce on your half (p = 0.25), then the opponent's (p = 0.75)
    return Math.abs(Math.sin(2 * Math.PI * (p - 0.25)));
  }
  // Up at the hitter's paddle, one bounce, rising again toward the receiver's paddle
  return Math.abs(Math.cos(Math.PI / 2 * p / BOUNCE_AT));
}

// Position on the table surface. "out" flies from your end (bottom) to the far end,
// "in" the other way; x slides from the "from" lane to the "to" lane.
function ballGround(ball, p, t, n) {
  return {
    x: t.x + ((ball.from + 0.5) + (ball.to - ball.from) * p) * t.w / n,
    y: ball.dir === 'out' ? t.y + t.h * (1 - p) : t.y + t.h * p,
  };
}

// How far up the screen to draw the ball for its height (the bird's-eye "fake 3D")
function ballLift(ball, p, t) {
  return ballHeight(ball.kind, p) * t.h * 0.08;
}

// Progress 0..1 of the current flight, from the browser's clock
function ballProgress(ball) {
  return Math.min((performance.now() - ballStart) / 1000 / ball.duration, 1);
}

function drawBall(t, n, px) {
  const ball = state.ball;
  if (!ball) { trail = []; return; }
  const p = ballProgress(ball);

  const { x, y } = ballGround(ball, p, t, n);
  const z = ballHeight(ball.kind, p);
  const lift = ballLift(ball, p, t);
  const r = (7 + 4 * z) * px;           // a bit bigger when higher

  trail.push({ x, y: y - lift, r });
  if (trail.length > 10) trail.shift();

  // Shadow on the table
  tctx.fillStyle = `rgba(0, 0, 0, ${0.5 - 0.3 * z})`;
  tctx.beginPath();
  tctx.ellipse(x, y, r * 1.1, r * 0.6, 0, 0, 2 * Math.PI);
  tctx.fill();

  // Trail
  trail.forEach((s, i) => {
    tctx.fillStyle = `rgba(255, 179, 71, ${(i / trail.length) * 0.35})`;
    tctx.beginPath();
    tctx.arc(s.x, s.y, s.r * (0.4 + 0.6 * i / trail.length), 0, 2 * Math.PI);
    tctx.fill();
  });

  // Ball
  tctx.fillStyle = '#ffb347';
  tctx.shadowColor = '#ffb347';
  tctx.shadowBlur = 16 * px;
  tctx.beginPath();
  tctx.arc(x, y - lift, r, 0, 2 * Math.PI);
  tctx.fill();
  tctx.shadowBlur = 0;
}

// --- Overlay view: the table in fake perspective on top of the camera -------------
// Table coordinates: u across (0 = left, 1 = right), d along (0 = your end, 1 = far end).
// Your end is the bottom edge of the video at full width, so the lanes there line up
// with the camera zones. The table shrinks toward the top: s(d) is the scale at depth d.
const FAR_SCALE = 0.3;                // far end is this fraction of the near end's width
const K = 1 / FAR_SCALE - 1;
const ARC = 0.25;                     // ball height 1 = this fraction of the frame height, up close
const BALL_R = 0.04;                  // ball radius up close, as a fraction of frame width

function persp(u, d, w, h) {
  const s = 1 / (1 + K * d);
  return { x: w / 2 + (u - 0.5) * w * s, y: h * s, s };
}

function drawPerspectiveTable(w, h) {
  const px = devicePixelRatio;
  const c = [persp(0, 0, w, h), persp(1, 0, w, h), persp(1, 1, w, h), persp(0, 1, w, h)];

  // Faint surface and border
  ctx.fillStyle = 'rgba(13, 42, 92, 0.25)';
  ctx.strokeStyle = 'rgba(242, 242, 247, 0.55)';
  ctx.lineWidth = 2 * px;
  ctx.beginPath();
  c.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
  ctx.closePath();
  ctx.fill();
  ctx.stroke();

  // Center line along the table
  const a = persp(0.5, 0, w, h), b = persp(0.5, 1, w, h);
  ctx.strokeStyle = 'rgba(242, 242, 247, 0.25)';
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.stroke();

  // Net across the middle, with a little height
  const l = persp(-0.04, 0.5, w, h), r = persp(1.04, 0.5, w, h);
  const netH = 0.06 * h * l.s;
  ctx.fillStyle = 'rgba(0, 229, 255, 0.15)';
  ctx.fillRect(l.x, l.y - netH, r.x - l.x, netH);
  ctx.strokeStyle = '#00e5ff';
  ctx.lineWidth = 3 * px;
  ctx.shadowColor = '#00e5ff';
  ctx.shadowBlur = 10 * px;
  ctx.beginPath();
  ctx.moveTo(l.x, l.y - netH);
  ctx.lineTo(r.x, r.y - netH);
  ctx.stroke();
  ctx.shadowBlur = 0;
}

// Ground point and lifted ball position on screen at progress p
function overlayPoint(ball, p, w, h, n) {
  const u = ((ball.from + 0.5) + (ball.to - ball.from) * p) / n;
  const d = ball.dir === 'out' ? p : 1 - p;
  const g = persp(u, d, w, h);
  const z = ballHeight(ball.kind, p);
  return { gx: g.x, gy: g.y, x: g.x, y: g.y - z * ARC * h * g.s, s: g.s, z };
}

function drawOverlayBall(w, h, n) {
  const ball = state.ball;
  if (!ball) { ovTrail = []; return; }
  const px = devicePixelRatio;
  const p = ballProgress(ball);

  // Rest of an incoming ball's path, dotted (not on levels with glow off)
  if (ball.dir === 'in' && state.glow !== false) {
    ctx.fillStyle = 'rgba(255, 179, 71, 0.75)';
    for (let q = Math.ceil(p * 40) / 40; q <= 1; q += 1 / 40) {
      const pt = overlayPoint(ball, q, w, h, n);
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, Math.max(1.5, 3 * pt.s) * px, 0, 2 * Math.PI);
      ctx.fill();
    }
  }

  const pt = overlayPoint(ball, p, w, h, n);
  const r = BALL_R * w * pt.s;

  ovTrail.push({ x: pt.x, y: pt.y, r });
  if (ovTrail.length > 10) ovTrail.shift();

  // Shadow on the table: darker and tighter when the ball is low
  ctx.fillStyle = `rgba(0, 0, 0, ${0.55 - 0.35 * pt.z})`;
  ctx.beginPath();
  ctx.ellipse(pt.gx, pt.gy, r * 1.2, r * 0.45, 0, 0, 2 * Math.PI);
  ctx.fill();

  ovTrail.forEach((t, i) => {
    ctx.fillStyle = `rgba(255, 179, 71, ${(i / ovTrail.length) * 0.35})`;
    ctx.beginPath();
    ctx.arc(t.x, t.y, t.r * (0.4 + 0.6 * i / ovTrail.length), 0, 2 * Math.PI);
    ctx.fill();
  });

  ctx.fillStyle = '#ffb347';
  ctx.shadowColor = '#ffb347';
  ctx.shadowBlur = 20 * px;
  ctx.beginPath();
  ctx.arc(pt.x, pt.y, r, 0, 2 * Math.PI);
  ctx.fill();
  ctx.shadowBlur = 0;
}
