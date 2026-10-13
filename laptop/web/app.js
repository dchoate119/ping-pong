// Game page. game.py streams the camera on /video and state on /events.
// The page only draws; all game logic lives in Python.

const video = document.querySelector('#video');
const canvas = document.querySelector('#overlay');
const ctx = canvas.getContext('2d');
const swingEl = document.querySelector('#swing');
const connEl = document.querySelector('#conn');
const fpsEl = document.querySelector('#fps');
const bannerEl = document.querySelector('#banner');
const resultEl = document.querySelector('#result');
const streakEl = document.querySelector('#streak');
const recordEl = document.querySelector('#record');

let state = { zones: 3, zone: null, box: null, swing: null, fps: 0, phase: 'waiting', ball: null,
              result: null };
let lastSwingId = null, lastResultId = null;
let ballId = null, ballStart = 0;  // performance.now() at launch, synced from ball.t
let trail = [];

// --- State from Python -------------------------------------------------------
const events = new EventSource('/events');
events.onopen = () => { connEl.textContent = 'live'; connEl.classList.add('on'); };
events.onerror = () => { connEl.textContent = 'reconnecting…'; connEl.classList.remove('on'); };
events.onmessage = e => {
  state = JSON.parse(e.data);
  fpsEl.textContent = `${state.fps.toFixed(0)} fps`;
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
  setNumber(streakEl, state.streak);
  setNumber(recordEl, state.record);
  bannerEl.classList.toggle('hidden', state.phase !== 'waiting');
  if (state.ball && state.ball.id !== ballId) {
    ballId = state.ball.id;
    ballStart = performance.now() - state.ball.t * 1000;
    trail = [];
  }
};

// HUD number that bumps when it changes
function setNumber(el, value) {
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

  // Paddle's zone glows
  if (state.zone !== null) {
    const x = state.zone * w / n;
    const g = ctx.createLinearGradient(0, h, 0, 0);
    g.addColorStop(0, 'rgba(57, 255, 136, 0.35)');
    g.addColorStop(1, 'rgba(57, 255, 136, 0.02)');
    ctx.fillStyle = g;
    ctx.fillRect(x, 0, w / n, h);
  }

  // Zone dividers
  ctx.strokeStyle = 'rgba(0, 229, 255, 0.6)';
  ctx.lineWidth = 2 * devicePixelRatio;
  ctx.setLineDash([12 * devicePixelRatio, 10 * devicePixelRatio]);
  for (let k = 1; k < n; k++) {
    ctx.beginPath();
    ctx.moveTo(k * w / n, 0);
    ctx.lineTo(k * w / n, h);
    ctx.stroke();
  }
  ctx.setLineDash([]);

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

  drawTable();
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);

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

  // Your lane glows where the paddle is
  if (state.zone !== null) {
    tctx.fillStyle = 'rgba(57, 255, 136, 0.25)';
    tctx.fillRect(t.x + state.zone * t.w / n, t.y + t.h / 2, t.w / n, t.h / 2);
  }

  // Incoming ball: its target lane pulses and the rest of its path is dotted
  const ball = state.ball;
  if (ball && ball.dir === 'in') {
    const pulse = 0.25 + 0.2 * Math.sin(performance.now() / 120);
    tctx.fillStyle = `rgba(255, 179, 71, ${pulse})`;
    tctx.fillRect(t.x + ball.to * t.w / n, t.y + t.h / 2, t.w / n, t.h / 2);

    const now = Math.min((performance.now() - ballStart) / 1000 / ball.duration, 1);
    tctx.fillStyle = 'rgba(255, 179, 71, 0.7)';
    for (let p = Math.ceil(now * 40) / 40; p <= 1; p += 1 / 40) {
      const { x, y } = ballGround(ball, p, t, n);
      tctx.beginPath();
      tctx.arc(x, y - ballLift(ball, p, t), 2 * px, 0, 2 * Math.PI);
      tctx.fill();
    }
  }

  // Lane dividers on your half
  tctx.strokeStyle = 'rgba(0, 229, 255, 0.6)';
  tctx.lineWidth = 2 * px;
  tctx.setLineDash([8 * px, 8 * px]);
  for (let k = 1; k < n; k++) {
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

function drawBall(t, n, px) {
  const ball = state.ball;
  if (!ball) { trail = []; return; }
  const p = Math.min((performance.now() - ballStart) / 1000 / ball.duration, 1);

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
