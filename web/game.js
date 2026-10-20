// game.js - shared Catan board rendering + interaction.
// Used by both the monitor page (full view) and the player client (filtered view).
(function () {
'use strict';

const RES = ['wood','brick','sheep','wheat','ore'];
const RES_LABEL = {wood:'木', brick:'土', sheep:'羊', wheat:'麦', ore:'鉄'};
const DEV_LABEL = {
  knight:'騎士', victory_point:'勝利点+1', road_building:'街道建設(道x2)',
  year_of_plenty:'収穫(資源x2)', monopoly:'独占'
};
function resName(k) { return RES_LABEL[k] || k; }
function devName(c) { return DEV_LABEL[c] || c; }
function escHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g,
    c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;'}[c]));
}
function toResKey(s) {
  s = (s || '').trim();
  const ja = {'木':'wood','土':'brick','羊':'sheep','麦':'wheat','鉄':'ore'};
  if (ja[s]) return ja[s];
  if (RES.includes(s)) return s;
  return null;
}

const TERRAIN_COLOR = {
  forest:'#2d8a4e', hills:'#c4956a', pasture:'#8bc34a',
  fields:'#f9d71c', mountains:'#9e9e9e', desert:'#e8c98a'
};
const TERRAIN_LABEL = {
  forest:'木', hills:'土', pasture:'羊', fields:'麦',
  mountains:'鉄', desert:'砂漠'
};

// ---------------------------------------------------------------------------
// Terrain textures
//   Procedurally drawn, cached offscreen. Every hex is painted once into a
//   square tile and then stamped (clipped to the hexagon) at draw time, so the
//   per-frame cost stays a single drawImage.
//
//   The look is deliberately soft / hand-painted: a gentle vertical gradient
//   for the base, a low-opacity scatter of detail marks, and no hard edges.
//   Details are seeded per terrain so they are identical every render (no
//   flicker) but differ between the six terrains.
// ---------------------------------------------------------------------------
const TEXTURE_CACHE = new Map();

// tiny deterministic PRNG so a texture always looks the same
function _rng(seed) {
  let s = seed >>> 0;
  return function () {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function _terrainStyle(t) {
  // base colour + gradient partner + detail colour per terrain
  switch (t) {
    case 'forest':    return { base:'#2f8f52', dark:'#1f6b3c', mark:'#8fd694', mark2:'#0e4f2b' };
    case 'hills':     return { base:'#c08a55', dark:'#a06e3f', mark:'#e0b483', mark2:'#8a5a30' };
    case 'pasture':   return { base:'#9ccc4e', dark:'#7cae38', mark:'#c7e88a', mark2:'#6f9c30' };
    case 'fields':    return { base:'#ecc93f', dark:'#d3a82b', mark:'#f7e08a', mark2:'#b98f1e' };
    case 'mountains': return { base:'#9a9a9a', dark:'#7d7d7d', mark:'#cfcfcf', mark2:'#636363' };
    case 'desert':    return { base:'#e6cf9a', dark:'#d5b877', mark:'#f4e6bd', mark2:'#c2a45f' };
    default:          return { base:'#777', dark:'#555', mark:'#999', mark2:'#444' };
  }
}

function _drawTerrainDetails(c, t, size, rnd) {
  const cx = size / 2, cy = size / 2;
  const R = size * 0.44;               // stay inside the hexagon
  c.save();
  c.beginPath(); c.arc(cx, cy, R, 0, Math.PI * 2); c.clip();

  if (t === 'forest') {
    // little trees: a soft blob + a lighter highlight
    for (let i = 0; i < 16; i++) {
      const x = cx + (rnd() - 0.5) * R * 1.7;
      const y = cy + (rnd() - 0.5) * R * 1.7;
      const r = R * (0.10 + rnd() * 0.07);
      c.globalAlpha = 0.55;
      c.fillStyle = '#12562f';
      c.beginPath(); c.moveTo(x, y - r); c.lineTo(x - r, y + r); c.lineTo(x + r, y + r); c.closePath(); c.fill();
      c.globalAlpha = 0.4;
      c.fillStyle = '#79c98a';
      c.beginPath(); c.moveTo(x, y - r * 0.5); c.lineTo(x - r * 0.6, y + r * 0.6); c.lineTo(x + r * 0.6, y + r * 0.6); c.closePath(); c.fill();
    }
  } else if (t === 'pasture') {
    // grass tufts + a few sheep dots
    c.strokeStyle = '#5f8f28';
    for (let i = 0; i < 26; i++) {
      const x = cx + (rnd() - 0.5) * R * 1.8;
      const y = cy + (rnd() - 0.5) * R * 1.8;
      c.globalAlpha = 0.35 + rnd() * 0.25;
      c.lineWidth = Math.max(1, size * 0.012);
      c.beginPath(); c.moveTo(x, y); c.lineTo(x + (rnd() - 0.5) * 4, y - R * 0.10); c.stroke();
    }
    c.globalAlpha = 0.5; c.fillStyle = '#f4f4ee';
    for (let i = 0; i < 5; i++) {
      const x = cx + (rnd() - 0.5) * R * 1.5, y = cy + (rnd() - 0.5) * R * 1.5;
      c.beginPath(); c.ellipse(x, y, R * 0.10, R * 0.07, 0, 0, Math.PI * 2); c.fill();
    }
  } else if (t === 'fields') {
    // rows of wheat: short golden strokes
    c.strokeStyle = '#8a6a12';
    for (let row = -3; row <= 3; row++) {
      const y0 = cy + row * R * 0.26;
      for (let i = 0; i < 6; i++) {
        const x = cx + (i - 2.5) * R * 0.28 + (rnd() - 0.5) * 3;
        c.globalAlpha = 0.4 + rnd() * 0.3;
        c.lineWidth = Math.max(1, size * 0.016);
        c.beginPath(); c.moveTo(x, y0 + R * 0.12); c.lineTo(x, y0 - R * 0.12); c.stroke();
      }
    }
  } else if (t === 'hills') {
    // rolling mounds
    for (let i = 0; i < 6; i++) {
      const x = cx + (rnd() - 0.5) * R * 1.4;
      const y = cy + (rnd() - 0.5) * R * 1.4;
      const r = R * (0.18 + rnd() * 0.14);
      c.globalAlpha = 0.5;
      c.fillStyle = '#8a5a30';
      c.beginPath(); c.ellipse(x, y + r * 0.3, r, r * 0.7, 0, 0, Math.PI * 2); c.fill();
      c.globalAlpha = 0.55;
      c.fillStyle = '#e0b483';
      c.beginPath(); c.ellipse(x, y, r * 0.9, r * 0.6, 0, 0, Math.PI * 2); c.fill();
    }
  } else if (t === 'mountains') {
    // rocky peaks with snow caps
    for (let i = 0; i < 4; i++) {
      const x = cx + (rnd() - 0.5) * R * 1.1;
      const y = cy + (rnd() - 0.5) * R * 0.9 + R * 0.15;
      const h = R * (0.45 + rnd() * 0.25), w = h * 0.9;
      c.globalAlpha = 0.7; c.fillStyle = '#6f6f6f';
      c.beginPath(); c.moveTo(x, y - h); c.lineTo(x - w, y + h * 0.5); c.lineTo(x + w, y + h * 0.5); c.closePath(); c.fill();
      c.globalAlpha = 0.85; c.fillStyle = '#efefef';
      c.beginPath(); c.moveTo(x, y - h); c.lineTo(x - w * 0.34, y - h * 0.42); c.lineTo(x + w * 0.34, y - h * 0.42); c.closePath(); c.fill();
    }
  } else if (t === 'desert') {
    // dunes + fine sand speckle
    for (let i = 0; i < 5; i++) {
      const x = cx + (rnd() - 0.5) * R * 1.4, y = cy + (rnd() - 0.5) * R * 1.4;
      c.globalAlpha = 0.4; c.strokeStyle = '#b9955a';
      c.lineWidth = Math.max(1, size * 0.014);
      c.beginPath(); c.arc(x, y, R * (0.2 + rnd() * 0.15), Math.PI * 1.05, Math.PI * 1.95); c.stroke();
    }
    c.fillStyle = '#b9955a';
    for (let i = 0; i < 60; i++) {
      c.globalAlpha = 0.15 + rnd() * 0.25;
      const x = cx + (rnd() - 0.5) * R * 1.8, y = cy + (rnd() - 0.5) * R * 1.8;
      c.fillRect(x, y, size * 0.02, size * 0.02);
    }
  }
  c.restore();
}

function terrainTexture(terrain, size) {
  const key = terrain + '@' + size;
  const hit = TEXTURE_CACHE.get(key);
  if (hit) return hit;
  const off = document.createElement('canvas');
  off.width = off.height = size;
  const c = off.getContext('2d');
  const st = _terrainStyle(terrain);
  // soft vertical gradient base
  const g = c.createLinearGradient(0, 0, 0, size);
  g.addColorStop(0, st.base);
  g.addColorStop(1, st.dark);
  c.fillStyle = g;
  c.fillRect(0, 0, size, size);
  // a soft radial light so the tile feels hand-painted, not flat
  const rg = c.createRadialGradient(size * 0.5, size * 0.38, size * 0.05,
                                    size * 0.5, size * 0.5, size * 0.62);
  rg.addColorStop(0, 'rgba(255,255,255,0.16)');
  rg.addColorStop(1, 'rgba(0,0,0,0.10)');
  c.fillStyle = rg; c.fillRect(0, 0, size, size);
  // details (deterministic seed per terrain)
  const seed = { forest: 11, hills: 22, pasture: 33, fields: 44, mountains: 55, desert: 66 }[terrain] || 7;
  _drawTerrainDetails(c, terrain, size, _rng(seed));
  TEXTURE_CACHE.set(key, off);
  return off;
}

let canvas, ctx;
let state = null;
let mode = 'none';
let scale = 50;
let TOKEN = null;
let VIEW = 'monitor';        // 'monitor' | 'client'
let booted = false;
let READONLY = false;        // monitor mode: view-only, no game actions

let pendingKnight = false;
let pendingRobberHex = null;
let pendingDiscardPid = null;

const phaseJa = {setup:'初期配置', roll:'サイコロ', main:'建設・交易', end:'終了'};

function api(path) {
  let url = path;
  const params = [];
  if (TOKEN) params.push('token=' + encodeURIComponent(TOKEN));
  // Tell the server this is the view-only monitor page. The server only grants
  // the full (debug) view to a LOCAL monitor, so a token-less player page can
  // never be upgraded to "see everything" just by being on the same machine.
  if (VIEW === 'monitor') params.push('view=monitor');
  if (params.length) url += (path.includes('?') ? '&' : '?') + params.join('&');
  return fetch(url).then(r => r.json());
}
async function getState() {
  fitCanvas();          // keep the canvas matched to its box (sheet, rotation, ...)
  const raw = await api('/state');
  if (!raw || !raw.players) {
    state = raw || {phase: 'lobby', started: false};
    // Keep whatever the lobby preview set up; game.js must not reset `state`
    // to the "not started" payload, otherwise the preview board disappears.
    if (VIEW === 'client') { location.reload(); return; }  // game was reset -> back to lobby
    const s = document.getElementById('status');
    if (s) s.innerHTML = 'ゲーム未開始（ロビー待ち）<br><span style="font-size:12px;color:#aaa;">クライアントがゲームを開始すると自動的に表示されます</span>';
    // Show the board the room is drafting on (if the lobby already has one).
    const r = await api('/room').catch(() => null);
    if (r && r.board) previewBoard(r.board);
    updateInitButton();
    render();
    return;
  }
  state = raw;
  // Tab title follows the player's own name while the game is running
  // (set again on every poll so it can never stay at the default).
  if (VIEW === 'client' && state.you !== null && state.you !== undefined &&
      state.players[state.you]) {
    const nm = state.players[state.you].name;
    document.title = nm ? ('カタン（プレイヤー：' + nm + '）') : 'カタン（プレイヤー）';
  }
  // Setup is a FIXED sequence: settlement first, then its road.
  if (state.phase === 'setup' && isMyTurn()) {
    mode = state.setup_settlement_required ? 'settle' : 'road';
    autoOpenBar();            // the player must tap the board/number: show the sheet
  }
  if (state.robber_pending && isMyTurn() && !hasPendingDiscards() && pendingRobberHex === null && mode !== 'robber') {
    mode = 'robber';
  }
  render();
  updateSidebar();
  updatePanels();
  updateMobileToggle();
}
async function post(action, extra={}) {
  const body = Object.assign({action}, extra);
  if (TOKEN) body.token = TOKEN;
  const r = await fetch('/action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}).then(x => x.json());
  await getState();   // refresh() sets the setup mode from server truth
  updateModeButtons();
  render();
  return r;
}

function isMyTurn() {
  if (!state) return false;
  if (READONLY) return false;           // monitor: viewing only
  if (VIEW === 'monitor') return true;
  return state.you !== null && state.you !== undefined && state.you === state.current;
}
function selfPlayer() {
  if (!state || !state.players) return null;
  if (VIEW === 'monitor') return state.players[state.current];
  return state.players[state.you] || null;
}
function hasPendingDiscards() {
  return state && state.pending_discards && Object.keys(state.pending_discards).length > 0;
}

function hexCenter(q, r) {
  const x = Math.sqrt(3)*q + Math.sqrt(3)/2*r;
  const y = 3/2*r;
  return {x, y};
}
function hexCorners(cx, cy) {
  const pts = [];
  for (let i=0;i<6;i++){ const a=Math.PI/180*(30+60*i); pts.push({x:cx+scale*Math.cos(a), y:cy+scale*Math.sin(a)}); }
  return pts;
}
function toCanvas(p) {
  if (!state) return p;
  return {x: canvas.width/2 + p.x*scale, y: canvas.height/2 + p.y*scale};
}
function playerColor(id) {
  const colors = ['#e53935','#1e88e5','#ab47bc','#fb8c00'];
  return colors[id] || '#888';
}
function portLabel(type) {
  if (type === 'generic') return '3:1';
  return '2:1 ' + resName(type);
}

function resize() {
  if (!canvas) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cssW = canvas.clientWidth || 800;
  const cssH = canvas.clientHeight || 600;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  scale = Math.min(canvas.width/10.6, canvas.height/10.0);
  render();
}

// Cheap check: only re-fit when the canvas backing store no longer matches the
// CSS box (device-pixel ratio included). Called from the poll loop so the board
// is always sharp/correct even if no resize event fired (e.g. bottom sheet).
function fitCanvas() {
  if (!canvas || !canvas.clientWidth) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.round(canvas.clientWidth * dpr);
  const h = Math.round(canvas.clientHeight * dpr);
  if (canvas.width !== w || canvas.height !== h) resize();
}

function render() {
  if (!ctx) return;
  ctx.fillStyle = '#1a1a1a';
  ctx.fillRect(0,0,canvas.width,canvas.height);
  if (!state || !state.board) return;
  const b = state.board;
  for (const h of b.hexes) {
    const c = hexCenter(h.q, h.r);
    const cc = toCanvas(c);
    const corners = hexCorners(cc.x, cc.y);
    ctx.beginPath();
    ctx.moveTo(corners[0].x, corners[0].y);
    for (let i=1;i<6;i++) ctx.lineTo(corners[i].x, corners[i].y);
    ctx.closePath();
    ctx.save();
    ctx.clip();                         // paint the texture only inside the hexagon
    const size = Math.round(2 * scale);
    // guard against a zero-size tile on the very first frame
    if (size > 2) {
      ctx.drawImage(terrainTexture(h.terrain, size), cc.x - scale, cc.y - scale, size, size);
    } else {
      ctx.fillStyle = TERRAIN_COLOR[h.terrain] || '#555';
      ctx.fill();
    }
    ctx.restore();
    ctx.strokeStyle = 'rgba(255,255,255,0.6)';
    ctx.lineWidth = 2;
    ctx.stroke();
    if (h.number) {
      // parchment disc so the number stays readable over the texture
      ctx.fillStyle = '#f3ead1';
      ctx.beginPath(); ctx.arc(cc.x, cc.y - 2, 19, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle = (h.number===6||h.number===8) ? '#c00' : '#5b4a2a';
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(cc.x, cc.y - 2, 19, 0, Math.PI*2); ctx.stroke();
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.beginPath(); ctx.arc(cc.x, cc.y - 2, 13, 0, Math.PI*2); ctx.fill();
      ctx.fillStyle = (h.number===6||h.number===8) ? '#c00' : '#000';
      ctx.font = 'bold 16px sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(h.number, cc.x, cc.y - 2);
    }
    const lbl = TERRAIN_LABEL[h.terrain] || '';
    ctx.font = 'bold 14px sans-serif';
    const tw = ctx.measureText(lbl).width + 14;
    ctx.fillStyle = 'rgba(0,0,0,0.85)';
    ctx.fillRect(cc.x - tw/2, cc.y + 14, tw, 20);
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
    ctx.strokeRect(cc.x - tw/2, cc.y + 14, tw, 20);
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(lbl, cc.x, cc.y + 24);
    if (h.robber) {
      ctx.fillStyle = '#111';
      ctx.beginPath(); ctx.arc(cc.x, cc.y + 16, 12, 0, Math.PI*2); ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 14px sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('R', cc.x, cc.y + 16);
    }
    if (mode === 'robber' && pendingRobberHex === null) {
      ctx.strokeStyle = 'rgba(255,80,80,0.9)';
      ctx.lineWidth = 3;
      ctx.setLineDash([6,4]);
      ctx.beginPath();
      ctx.moveTo(corners[0].x, corners[0].y);
      for (let i=1;i<6;i++) ctx.lineTo(corners[i].x, corners[i].y);
      ctx.closePath(); ctx.stroke();
      ctx.setLineDash([]);
    }
  }
  drawPorts(b);   // ports first, so roads drawn along a port edge stay visible
  for (const e of b.edges) {
    const p0 = toCanvas({x:e.points[0][0], y:e.points[0][1]});
    const p1 = toCanvas({x:e.points[1][0], y:e.points[1][1]});
    ctx.strokeStyle = e.road_owner===null ? 'rgba(255,255,255,0.15)' : playerColor(e.road_owner);
    ctx.lineWidth = e.road_owner===null ? 2 : 5;
    ctx.beginPath(); ctx.moveTo(p0.x,p0.y); ctx.lineTo(p1.x,p1.y); ctx.stroke();
  }
  const showRoads = (mode==='road' || state.phase==='setup') && isMyTurn();
  if (showRoads) {
    for (const ei of (state.valid.roads||[])) {
      const e = b.edges[ei];
      const p0 = toCanvas({x:e.points[0][0], y:e.points[0][1]});
      const p1 = toCanvas({x:e.points[1][0], y:e.points[1][1]});
      ctx.strokeStyle = '#ff0'; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(p0.x,p0.y); ctx.lineTo(p1.x,p1.y); ctx.stroke();
    }
  }
  for (const v of b.vertices) {
    const p = toCanvas({x:v.x, y:v.y});
    if (v.building) {
      ctx.fillStyle = playerColor(v.owner);
      ctx.strokeStyle = '#111'; ctx.lineWidth = 3;
      if (v.building === 'city') {
        ctx.fillRect(p.x-11, p.y-11, 22, 22);
        ctx.strokeRect(p.x-11, p.y-11, 22, 22);
        ctx.fillStyle = 'rgba(255,255,255,0.85)';
        ctx.fillRect(p.x-4, p.y-4, 8, 8);
      } else {
        ctx.beginPath(); ctx.arc(p.x, p.y, 10, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(p.x, p.y, 10, 0, Math.PI*2); ctx.stroke();
        ctx.fillStyle = 'rgba(255,255,255,0.85)';
        ctx.beginPath(); ctx.arc(p.x, p.y, 3.5, 0, Math.PI*2); ctx.fill();
      }
    } else if ((mode==='settle' || state.phase==='setup') && (state.valid.settlements||[]).includes(v.i) && isMyTurn()) {
      ctx.fillStyle='rgba(255,255,0,0.5)';
      ctx.beginPath(); ctx.arc(p.x, p.y, 9, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle='#ff0'; ctx.lineWidth=2;
      ctx.beginPath(); ctx.arc(p.x, p.y, 9, 0, Math.PI*2); ctx.stroke();
    } else if (mode==='city' && (state.valid.cities||[]).includes(v.i) && isMyTurn()) {
      ctx.strokeStyle='#ff0'; ctx.lineWidth=2;
      ctx.strokeRect(p.x-8, p.y-8, 16, 16);
    }
  }
  drawPortLabels(b);  // topmost: the port ratios must stay readable
}

function drawPorts(b) {
  for (const pe of (b.port_edges || [])) {
    const p1 = toCanvas({x:pe.x1, y:pe.y1});
    const p2 = toCanvas({x:pe.x2, y:pe.y2});
    const mid = {x:(p1.x+p2.x)/2, y:(p1.y+p2.y)/2};
    const ccx = canvas.width/2, ccy = canvas.height/2;
    let ox = mid.x - ccx, oy = mid.y - ccy;
    const ol = Math.hypot(ox, oy) || 1;
    ox /= ol; oy /= ol;
    ctx.strokeStyle = '#8d6e63'; ctx.lineWidth = 4;
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(mid.x, mid.y);
    ctx.lineTo(mid.x + ox*scale*0.55, mid.y + oy*scale*0.55);
    ctx.stroke();
  }
}

// Drawn last (on top of roads/buildings) so a port's ratio is always readable.
function drawPortLabels(b) {
  for (const pe of (b.port_edges || [])) {
    const p1 = toCanvas({x:pe.x1, y:pe.y1});
    const p2 = toCanvas({x:pe.x2, y:pe.y2});
    const mid = {x:(p1.x+p2.x)/2, y:(p1.y+p2.y)/2};
    const ccx = canvas.width/2, ccy = canvas.height/2;
    let ox = mid.x - ccx, oy = mid.y - ccy;
    const ol = Math.hypot(ox, oy) || 1;
    ox /= ol; oy /= ol;
    const lx = mid.x + ox*scale*0.9, ly = mid.y + oy*scale*0.9;
    const txt = portLabel(pe.type);
    ctx.font = 'bold 11px sans-serif';
    const tw = ctx.measureText(txt).width + 8;
    ctx.fillStyle = 'rgba(0,0,0,0.75)';
    ctx.fillRect(lx - tw/2, ly - 9, tw, 18);
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1;
    ctx.strokeRect(lx - tw/2, ly - 9, tw, 18);
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(txt, lx, ly);
  }
}

// Monitor-only helper: lets the room be sent back to the lobby (same members,
// fresh dice) - visible whenever a game exists, including after the winner is
// decided, so a finished game can be restarted without re-joining.
function updateInitButton() {
  const b = document.getElementById('btn-init');
  if (!b) return;
  const running = !!(state && state.players && state.players.length);
  b.style.display = (VIEW === 'monitor' && running) ? 'block' : 'none';
}

function updateSidebar() {
  if (!state || !state.players) return;
  updateInitButton();
  const status = document.getElementById('status');
  const cur = state.players[state.current];
  let hint = '';
  if (isMyTurn()) {
    if (state.phase === 'setup') hint = ` → 開拓地を配置`;
    else if (state.phase === 'roll') hint = ` → サイコロを振る`;
    else if (state.phase === 'main') hint = ` → 建設・交易`;
  }
  if (VIEW === 'client') {
    hint = (isMyTurn()
      ? '<span style="color:#8f8;font-weight:bold;">▶ あなたの手番です</span>'
      : '<span style="color:#aaa;">相手の手番です（待機中）</span>') + hint;
  }
  let extra = '';
  if (hasPendingDiscards()) extra = '<br><b style="color:#ff8">7: カードを捨ててください</b>';
  else if (state.robber_pending) extra = '<br><b style="color:#ff8">7: 盗賊を移動（ヘックスをクリック）</b>';
  if (state.rerolled) extra += '<br><span style="color:#8cf">7は振り直し（第1巡目）</span>';
  let mine = '';
  if (VIEW === 'client') {
    mine = (state.you !== null && state.you !== undefined)
      ? `<br><span style="color:#8cf">あなた: <b>${state.players[state.you].name}</b> (P${state.you})</span>`
      : `<br><span style="color:#f88">このゲームに参加していません（観戦モード）</span>`;
  }
  status.innerHTML = `フェーズ: <b>${phaseJa[state.phase]||state.phase}</b> | ターン ${state.turn_number||0}<br>手番: <b>${cur.name}</b> (P${cur.id})${hint}${extra}${mine}<br>サイコロ: ${state.dice.join('+')||'-'} | 勝者: ${state.winner!==null?state.players[state.winner].name:'-'}`;

  const pd = document.getElementById('players');
  pd.innerHTML = '';
  for (const p of state.players) {
    const div = document.createElement('div');
    div.className = 'player' + (p.id===state.current?' current':'') + ((VIEW==='client' && p.id===state.you)?' me':'');
    const used = (p.used_dev_cards||[]).length ? ` 使用済:[${p.used_dev_cards.map(devName).join(',')}]` : '';
    // Once the game is over every player's holding is opened up: show what is
    // left in hand (未使用) alongside what has been played (使用済).
    let held = '';
    if (p.revealed && Array.isArray(p.dev_cards)) {
      const remaining = [...p.dev_cards, ...(p.new_dev_cards||[])];
      const fresh = new Set(p.new_dev_cards||[]);
      held = ' 未使用:[' + (remaining.length
        ? remaining.map(c => devName(c) + (fresh.has(c) ? '(新規)' : '')).join(',')
        : 'なし') + ']';
    }
    div.innerHTML = `<span style="display:inline-block;width:12px;height:12px;background:${playerColor(p.id)};border:1px solid #fff;border-radius:2px;margin-right:4px;vertical-align:-1px;"></span><b>${p.name}</b> (P${p.id}) 勝利点:${p.total_vp} 手札:${p.hand_count} 発展:${p.dev_count}${p.longest_road?' [最長の道]':''}${p.largest_army?' [最大騎士団]':''}${used}${held}`;
    pd.appendChild(div);
  }

  const me = selfPlayer();
  const rd = document.getElementById('resources');
  rd.innerHTML = '';
  if (me && me.resources) {
    for (const k of RES) {
      const row = document.createElement('div'); row.className='resource';
      row.innerHTML = `<span>${resName(k)}</span><span>${me.resources[k]||0}</span>`;
      rd.appendChild(row);
    }
  }
  const bankEl = document.getElementById('bank');
  if (bankEl) {
    bankEl.textContent = '銀行の残り: ' + RES.map(k => `${resName(k)}:${state.bank ? state.bank[k] : '?'}`).join('　');
  }
  const legend = document.getElementById('legend');
  if (legend) {
    const colors = {forest:'#2d8a4e',hills:'#c4956a',pasture:'#8bc34a',fields:'#f9d71c',mountains:'#9e9e9e',desert:'#e8c98a'};
    const labels = {forest:'木',hills:'土',pasture:'羊',fields:'麦',mountains:'鉄',desert:'砂漠'};
    legend.innerHTML = Object.keys(colors).map(k =>
      `<div style="display:flex;align-items:center;gap:6px;"><span style="display:inline-block;width:14px;height:14px;background:${colors[k]};border:1px solid #fff;border-radius:2px;"></span>${labels[k]}</div>`
    ).join('');
  }
  if (READONLY) return;   // monitor: informational panels only, no action controls

  const devSel = document.getElementById('dev-select');
  const prevVal = devSel.value;
  devSel.innerHTML = '';
  if (me && me.dev_cards) {
    for (const c of me.dev_cards) {
      // a victory point card is never "played" - it is only a score
      if (c === 'victory_point') continue;
      const opt = document.createElement('option');
      opt.value = c; opt.textContent = devName(c);
      devSel.appendChild(opt);
    }
  }
  if (prevVal && [...devSel.options].some(o=>o.value===prevVal)) devSel.value = prevVal;
  updateDevParams();
  devSel.onchange = updateDevParams;
  document.getElementById('devcards').textContent =
    (me && me.dev_cards ? me.dev_cards.map(devName).join(', ') : '') +
    (me && me.new_dev_cards && me.new_dev_cards.length ? ' (新規: '+me.new_dev_cards.map(devName).join(',')+')' : '');

  updateTradeUI(me);
  updatePlayerTradeUI(me);
  updateActionAvailability();
}

function resStr(d) {
  const parts = Object.entries(d || {}).map(([k, v]) => v + ' ' + resName(k));
  return parts.length ? parts.join(', ') : 'なし';
}

function updatePlayerTradeUI(me) {
  const active = document.getElementById('pt-active');
  const builder = document.getElementById('pt-builder');
  const note = document.getElementById('pt-note');
  const offer = state.trade_offer;
  const myId = (VIEW === 'client' && state.you !== null && state.you !== undefined) ? state.you : null;
  // A player who is neither the proposer nor a target is not part of this
  // negotiation: never show them the responder panel (it would look like a
  // stuck dialog) - just a note, while their own builder stays usable.
  const involved = !!offer && (myId === offer.from || offer.targets.includes(myId));
  if (offer && VIEW === 'client' && !involved) {
    active.style.display = 'none';
    note.style.display = 'block';
    note.innerHTML = `※ ${escHtml(state.players[offer.from].name)} さんが取引を提案中です（終わるまで新しい提案はできません）`;
    builder.style.display = 'block';
    buildPtBuilder(me);
    return;
  }
  note.style.display = 'none';
  if (offer) {
    active.style.display = 'block';
    builder.style.display = 'none';
    const fromP = state.players[offer.from];
    let html = `<div style="font-size:12px;"><b>${fromP.name}</b> の提案: <b>${resStr(offer.give)}</b> を渡す／<b>${resStr(offer.want)}</b> がほしい</div>`;
    const amTarget = myId !== null && offer.targets.includes(myId) && !(offer.declined||[]).includes(myId);
    if (VIEW === 'monitor') {
      // let the monitor act on behalf of any responder / proposer
      const responders = offer.targets.filter(t => !(offer.declined || []).includes(t));
      if (responders.length === 0) {
        html += `<div style="font-size:12px;color:#f88;margin-top:4px;">応答できる相手がいません。</div>`;
      } else {
        for (const t of responders) {
          html += `<div style="margin-top:4px;font-size:12px;">${state.players[t].name}
            <button class="btn" data-pt-accept="${t}">承諾</button>
            <button class="btn" data-pt-decline="${t}">拒否</button></div>`;
        }
      }
      html += `<div style="margin-top:6px;"><button class="btn" data-pt-cancel="${offer.from}">提案を取り消す</button></div>`;
    } else if (amTarget) {
      html += `<div style="margin-top:6px;"><button class="btn" data-pt-accept="${myId}">承諾</button>
        <button class="btn" data-pt-decline="${myId}">拒否</button></div>`;
    } else if (myId === offer.from) {
      html += `<div style="margin-top:6px;"><button class="btn" data-pt-cancel="${myId}">提案を取り消す</button></div>`;
    } else {
      html += `<div style="font-size:12px;color:#aaa;margin-top:4px;">` +
        (offer.targets.includes(myId) ? '（すでに応答済みです）' : '（あなたは対象ではありません）') + `</div>`;
    }
    active.innerHTML = html;
    active.querySelectorAll('[data-pt-accept]').forEach(b =>
      b.onclick = async () => { const r = await post('trade_respond', {player: parseInt(b.dataset.ptAccept), accept: true}); if (!r.ok) alert('承諾できませんでした（資源が足りない可能性があります）。'); });
    active.querySelectorAll('[data-pt-decline]').forEach(b =>
      b.onclick = () => post('trade_respond', {player: parseInt(b.dataset.ptDecline), accept: false}));
    active.querySelectorAll('[data-pt-cancel]').forEach(b =>
      b.onclick = () => post('trade_cancel', {player: parseInt(b.dataset.ptCancel)}));
  } else {
    active.style.display = 'none';
    builder.style.display = 'block';
    buildPtBuilder(me);
  }
}

function buildPtBuilder(me) {
  const g = document.getElementById('pt-give');
  const w = document.getElementById('pt-want');
  if (!g.dataset.built) {
    g.innerHTML = ''; w.innerHTML = '';
    for (const k of RES) {
      const row = document.createElement('label');
      row.style.cssText = 'display:flex;justify-content:space-between;align-items:center;font-size:12px;margin:2px 0;';
      row.innerHTML = `<span>${resName(k)} <span class="pt-have" data-k="${k}"></span></span>
        <input type="number" min="0" value="0" data-pt="give" data-k="${k}" style="width:56px;padding:2px;background:#1a1a1a;color:#eee;border:1px solid #555;border-radius:4px;">`;
      g.appendChild(row);
      const row2 = document.createElement('label');
      row2.style.cssText = 'display:flex;justify-content:space-between;align-items:center;font-size:12px;margin:2px 0;';
      row2.innerHTML = `<span>${resName(k)}</span>
        <input type="number" min="0" value="0" data-pt="want" data-k="${k}" style="width:56px;padding:2px;background:#1a1a1a;color:#eee;border:1px solid #555;border-radius:4px;">`;
      w.appendChild(row2);
    }
    g.dataset.built = '1';
  }
  const myres = (me && me.resources) ? me.resources : {};
  g.querySelectorAll('input[data-pt="give"]').forEach(inp => { inp.max = myres[inp.dataset.k] || 0; });
  g.querySelectorAll('.pt-have').forEach(s => { s.textContent = '（所持 ' + (myres[s.dataset.k] || 0) + '）'; });
  const t = document.getElementById('pt-targets');
  const checked = new Set([...t.querySelectorAll('input:checked')].map(i => i.value));
  t.innerHTML = '';
  for (const p of state.players) {
    if (p.id === (VIEW === 'client' && state.you !== null ? state.you : state.current)) continue;
    const lbl = document.createElement('label');
    lbl.style.cssText = 'display:inline-block;margin-right:8px;font-size:12px;';
    lbl.innerHTML = `<input type="checkbox" value="${p.id}" ${checked.has(String(p.id)) ? 'checked' : ''}> ${p.name}`;
    t.appendChild(lbl);
  }
}

function updateTradeUI(me) {
  const give = document.getElementById('trade-give');
  const recv = document.getElementById('trade-receive');
  if (!give.options.length) {
    for (const k of RES) {
      const o1=document.createElement('option'); o1.value=k; o1.textContent=resName(k); give.appendChild(o1);
      const o2=document.createElement('option'); o2.value=k; o2.textContent=resName(k); recv.appendChild(o2);
    }
    recv.value = 'ore';
    give.onchange = () => updateTradeUI(selfPlayer());
    recv.onchange = () => updateTradeUI(selfPlayer());
  }
  const g = give.value || 'wood';
  const ratio = (state.trade_ratios && state.trade_ratios[g]) || 4;
  const have = (me && me.resources) ? (me.resources[g] || 0) : 0;
  document.getElementById('trade-ratio').textContent = `${ratio}:1（所持 ${have} ${resName(g)}）`;
}

// Monopoly / Year of Plenty: pick the resource(s) from a dropdown instead of
// a text prompt. Rebuilt only when the selected card actually changes so the
// player's choice is not reset every poll.
function updateDevParams() {
  const sel = document.getElementById('dev-select');
  const box = document.getElementById('dev-params');
  if (!sel || !box) return;
  const card = sel.value || '';
  if (box.dataset.card === card) return;
  box.dataset.card = card;
  const opts = (selval) => RES.map(k =>
    `<option value="${k}"${k === selval ? ' selected' : ''}>${resName(k)}</option>`).join('');
  if (card === 'year_of_plenty') {
    box.style.display = 'block';
    box.innerHTML =
      `<div style="font-size:12px;">取り出す資源（銀行から2枚）</div>
       <label style="font-size:12px;margin-right:8px;">1枚目
         <select data-r="r1" style="padding:3px;">${opts('wood')}</select></label>
       <label style="font-size:12px;">2枚目
         <select data-r="r2" style="padding:3px;">${opts('brick')}</select></label>`;
  } else if (card === 'monopoly') {
    box.style.display = 'block';
    box.innerHTML =
      `<div style="font-size:12px;">独占する資源</div>
       <select data-r="resource" style="width:100%;padding:4px;">${opts('wood')}</select>`;
  } else {
    box.style.display = 'none';
    box.innerHTML = '';
  }
}

function updateActionAvailability() {
  const blocked = hasPendingDiscards() || (state && state.robber_pending) || !isMyTurn();
  for (const id of ['btn-roll','btn-end','btn-buydev','btn-playdev','btn-trade','btn-pt-propose']) {
    const el = document.getElementById(id);
    if (el) el.disabled = !!blocked;
  }
  const rb = document.getElementById('mode-robber');
  if (rb) rb.disabled = !(state && state.robber_pending && isMyTurn());
  // During setup the sequence settlement -> road is automatic, so the manual
  // build-mode buttons are disabled to prevent placing in the wrong order.
  const inSetup = !!(state && state.phase === 'setup');
  for (const id of ['mode-road','mode-settle','mode-city']) {
    const el = document.getElementById(id);
    if (el) el.disabled = !!blocked || inSetup;
  }
  updateMobileToggle();
}

// ---------------------------------------------------------------------------
// Mobile (phone) layout helpers
//   On a narrow screen the sidebar becomes a bottom sheet: the board keeps the
//   top half of the screen and the controls live in a panel that slides up.
//   It starts closed so the whole board is visible, and opens by itself only
//   when the player must act (discard / robber / setup placement).
// ---------------------------------------------------------------------------
function isPhone() {
  return window.matchMedia('(max-width: 860px)').matches;
}

function barOpened() {
  return document.body.classList.contains('bar-open');
}

function setBar(open) {
  document.body.classList.toggle('bar-open', !!open);
  const b = document.getElementById('btn-togglebar');
  if (b) b.textContent = open ? '▼ 盤面を広く見る' : '▲ 操作パネルを開く';
  if (isPhone()) {
    // make sure the board is laid out against the new pane height
    requestAnimationFrame(() => { resize(); updateMobileToggle(); });
    setTimeout(() => { resize(); updateMobileToggle(); }, 80);
  }
}

// Open the action sheet when the player has to act (discard / robber / setup).
// While the player is actively placing something the sheet stays open, so the
// turn does not flap between "open" and "closed" on every poll.
let barHeld = false;
function autoOpenBar() {
  if (!isPhone()) return;
  if (mobileNeedsAction()) {
    barHeld = true;
    if (!barOpened()) setBar(true);
    return;
  }
  const stillActing = isMyTurn() && (mode === 'road' || mode === 'settle' || mode === 'city' || mode === 'robber');
  if (barHeld && stillActing) return;      // keep it open during the placement
  barHeld = false;
}

// Tell the closed bar what is going on, so the player knows why it opened.
function updateMobileToggle() {
  const obs = document.getElementById('m-observe');
  if (obs) obs.textContent = '監視モード（閲覧のみ）。操作はプレイヤー画面から行います。';
  const el = document.getElementById('m-bar-status');
  const bar = document.getElementById('m-bar');
  if (!el || !bar || !state || !state.players) return;
  const cur = state.players[state.current];
  const parts = [];
  if (READONLY) {
    parts.push('閲覧のみ');
    if (cur) parts.push(`手番: ${cur.name}`);
    el.textContent = parts.join('　');
    return;
  }
  parts.push(`ターン${state.turn_number || 0}`);
  parts.push(isMyTurn() ? 'あなたの手番' : `手番: ${cur.name}`);
  if (state.phase === 'setup') parts.push(isMyTurn() ? (state.setup_settlement_required ? '開拓地を配置' : '街道を配置') : '');
  else if (state.phase === 'roll') parts.push(isMyTurn() ? 'サイコロを振る' : '');
  if (hasPendingDiscards()) parts.push('カードを捨てる');
  else if (state.robber_pending) parts.push('盗賊を移動');
  el.textContent = parts.filter(Boolean).join('　');
}

// Should the action sheet open on its own? (discard / robber / setup placement)
function mobileNeedsAction() {
  if (!isPhone() || !state || !state.players || !isMyTurn()) return false;
  if (hasPendingDiscards()) return true;
  if (state.robber_pending || pendingRobberHex !== null) return true;
  if (state.phase === 'setup') return true;
  return false;
}

function updatePanels() {
  if (!state || READONLY) return;
  const myId = (VIEW === 'client' && state.you !== null && state.you !== undefined) ? state.you : null;
  // ---- discard panel ----
  const dp = document.getElementById('discard-panel');
  let discardPid = null;
  if (hasPendingDiscards()) {
    if (VIEW === 'monitor') {
      const pids = Object.keys(state.pending_discards).map(Number).sort((a,b)=>a-b);
      discardPid = pids[0];
    } else if (myId !== null && state.pending_discards[String(myId)] !== undefined) {
      discardPid = myId;
    }
  }
  if (discardPid !== null) {
    const need = state.pending_discards[String(discardPid)];
    const p = state.players[discardPid];
    dp.style.display = 'block';
    document.getElementById('discard-info').innerHTML =
      `<b>${p.name}</b> は <b>${need}</b> 枚捨てる必要があります。捨てるカードを選んでください。`;
    const box = document.getElementById('discard-inputs');
    if (pendingDiscardPid !== discardPid) {
      pendingDiscardPid = discardPid;
      box.innerHTML = '';
      const res = (p.resources) ? p.resources : {};
      for (const k of RES) {
        const have = res[k] || 0;
        const row = document.createElement('div');
        row.className = 'discard-row';
        row.innerHTML = `<label style="display:flex;align-items:center;justify-content:space-between;font-size:13px;margin:2px 0;">
          <span>${resName(k)}（所持 ${have}）</span>
          <input type="number" min="0" max="${have}" value="0" data-res="${k}" style="width:64px;padding:2px;">
        </label>`;
        box.appendChild(row);
      }
    }
  } else {
    dp.style.display = 'none';
    pendingDiscardPid = null;
  }
  if (discardPid !== null && typeof autoOpenBar === 'function') autoOpenBar();
  // ---- robber panel ----
  const rp = document.getElementById('robber-panel');
  if (pendingRobberHex !== null) {
    rp.style.display = 'block';
    const key = pendingRobberHex[0] + ',' + pendingRobberHex[1];
    const victims = (state.robber_victims && state.robber_victims[key]) || [];
    document.getElementById('robber-info').textContent = `盗賊: (${key})。奪う相手を選んでください。`;
    const sel = document.getElementById('robber-victim');
    sel.innerHTML = '';
    for (const vid of victims) {
      const vp = state.players[vid];
      const o = document.createElement('option');
      o.value = vid;
      o.textContent = `${vp.name}（手札: ${vp.hand_count}）`;
      sel.appendChild(o);
    }
  } else {
    rp.style.display = 'none';
  }
  if (pendingRobberHex !== null && typeof autoOpenBar === 'function') autoOpenBar();
}

function pointToSegDist(px,py,a,b) {
  const dx=b.x-a.x, dy=b.y-a.y;
  const t = Math.max(0, Math.min(1, ((px-a.x)*dx+(py-a.y)*dy)/(dx*dx+dy*dy||1)));
  const cx = a.x + t*dx, cy = a.y + t*dy;
  return Math.hypot(px-cx, py-cy);
}

async function sendRobberMove(hex, victim) {
  let r;
  if (pendingKnight) r = await post('play_dev', {card:'knight', hex, victim});
  else r = await post('move_robber', {hex, victim});
  pendingRobberHex = null;
  pendingKnight = false;
  mode = 'none';
  updateModeButtons();
  updatePanels();
  render();
  return r;
}

function setMode(m){ mode=m; updateModeButtons(); render(); }
function updateModeButtons() {
  for (const id of ['mode-road','mode-settle','mode-city','mode-none']) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('active', id==='mode-'+mode);
  }
}

// ---------------------------------------------------------------------------
// sidebar markup
// ---------------------------------------------------------------------------
function sidebarHTML() {
  if (READONLY) {
    // monitor (view-only): informational panels only, no action controls
    return `
    <div id="m-bar" class="m-only">
      <button class="btn" id="btn-togglebar">操作パネルを開く</button>
      <span id="m-bar-status"></span>
    </div>
    <div id="sidebar-body">
    <div id="status">読み込み中...</div>
    <div id="m-observe" class="m-only m-note"></div>
    <h2>プレイヤー</h2>
    <div id="players"></div>
    <h2>資源（現在の手番）</h2>
    <div id="resources"></div>
    <div id="bank" style="font-size:11px;color:#bbb;margin-top:2px;"></div>
    <h2>凡例</h2>
    <div id="legend" style="font-size:11px;line-height:1.6;"></div>
    </div>`;
  }
  const monitorBtns = VIEW === 'monitor'
    ? `<button class="btn" id="btn-new">新しいゲーム</button>
       <button class="btn" id="btn-auto">自動配置</button>` : '';
  return `
    <div id="m-bar" class="m-only">
      <button class="btn" id="btn-togglebar">操作パネルを開く</button>
      <span id="m-bar-status"></span>
    </div>
    <div id="sidebar-body">
    <div id="status">読み込み中...</div>
    <div>
      <button class="btn" id="btn-roll">サイコロを振る</button>
      <button class="btn" id="btn-end">ターン終了</button>
      ${monitorBtns}
    </div>
    <div class="m-only" style="margin:2px 0 6px;">
      <button id="toggle-all">▽ 交易・発展カードなども表示</button>
    </div>
    <div class="m-fold" id="fold-build">
      <button class="btn" id="mode-road">街道を建てる</button>
      <button class="btn" id="mode-settle">開拓地を建てる</button>
      <button class="btn" id="mode-city">都市を建てる</button>
      <button class="btn" id="btn-buydev">発展カードを購入</button>
      <button class="btn" id="mode-none">キャンセル</button>
      <button class="btn" id="mode-robber">盗賊を移動</button>
    </div>
    <div id="discard-panel" class="panel" style="display:none;">
      <h2>カードを捨てる</h2>
      <div id="discard-info" style="font-size:12px;margin-bottom:6px;"></div>
      <div id="discard-inputs"></div>
      <div style="margin-top:6px;"><button class="btn" id="btn-discard">捨てる</button></div>
    </div>
    <div id="robber-panel" class="panel" style="display:none;">
      <h2>奪う相手を選ぶ</h2>
      <div id="robber-info" style="font-size:12px;margin-bottom:6px;"></div>
      <select id="robber-victim" style="width:100%;padding:4px;"></select>
      <div style="margin-top:6px;">
        <button class="btn" id="btn-robber-ok">奪う</button>
        <button class="btn" id="btn-robber-cancel">キャンセル</button>
      </div>
    </div>
    <h2>プレイヤー</h2>
    <div id="players"></div>
    <h2>${VIEW === 'monitor' ? '資源（現在の手番）' : '自分の資源'}</h2>
    <div id="resources"></div>
    <div id="bank" style="font-size:11px;color:#bbb;margin-top:2px;"></div>
    <h2>銀行・港との交易</h2>
    <div id="trade-panel" class="m-fold">
      <label style="font-size:12px;">渡す</label>
      <select id="trade-give" style="width:100%;padding:4px;margin:2px 0;"></select>
      <label style="font-size:12px;">受け取る</label>
      <select id="trade-receive" style="width:100%;padding:4px;margin:2px 0;"></select>
      <div id="trade-ratio" style="font-size:12px;margin:2px 0;"></div>
      <button class="btn" id="btn-trade">交換する</button>
    </div>
    <h2>プレイヤー間交易</h2>
    <div id="playertrade-panel" class="panel m-fold">
      <div id="pt-note" style="display:none;font-size:12px;color:#ffd54f;"></div>
      <div id="pt-active" style="display:none;"></div>
      <div id="pt-builder">
        <div style="font-size:12px;">渡す（自分 &rarr; 相手）</div>
        <div id="pt-give"></div>
        <div style="font-size:12px;margin-top:4px;">ほしい（相手 &rarr; 自分）</div>
        <div id="pt-want"></div>
        <div style="font-size:12px;margin-top:4px;">相手</div>
        <div id="pt-targets"></div>
        <div style="margin-top:6px;"><button class="btn" id="btn-pt-propose">提案する</button></div>
      </div>
    </div>
    <h2>凡例</h2>
    <div id="legend" style="font-size:11px;line-height:1.6;"></div>
    <h2>発展カード</h2>
    <div id="devcards"></div>
    <div class="m-fold" id="fold-dev">
      <select id="dev-select" style="width:100%;margin:4px 0;padding:4px;"></select>
      <div id="dev-params" style="display:none;margin:4px 0;"></div>
      <button class="btn" id="btn-playdev">選んだカードを使う</button>
    </div>
    </div>`;
}

function bindCanvas() {
  canvas.addEventListener('click', async (ev) => {
    if (!state || !state.board) return;
    if (hasPendingDiscards()) return;
    if (!isMyTurn()) return;
    const rect = canvas.getBoundingClientRect();
    // rect is in CSS px; the canvas backing store may be scaled by DPR.
    const sx = rect.width ? canvas.width / rect.width : 1;
    const sy = rect.height ? canvas.height / rect.height : 1;
    const cx = (ev.clientX - rect.left) * sx, cy = (ev.clientY - rect.top) * sy;
    const wx = (cx - canvas.width/2) / scale, wy = (cy - canvas.height/2) / scale;
    if (mode === 'robber') {
      let best = null, bestd = 1e9;
      for (const h of state.board.hexes) {
        const c = hexCenter(h.q, h.r);
        const d = Math.hypot(wx - c.x, wy - c.y);
        if (d < bestd) { bestd = d; best = h; }
      }
      if (best && bestd < 1.0) {
        if (best.robber) return;
        const key = best.q + ',' + best.r;
        const victims = (state.robber_victims && state.robber_victims[key]) || [];
        if (victims.length === 0) await sendRobberMove([best.q, best.r], null);
        else { pendingRobberHex = [best.q, best.r]; updatePanels(); render(); }
      }
      return;
    }
    if (mode === 'road') {
      let best = null, bestd = 1e9;
      for (const ei of (state.valid.roads||[])) {
        const e = state.board.edges[ei];
        const p0 = {x:e.points[0][0], y:e.points[0][1]};
        const p1 = {x:e.points[1][0], y:e.points[1][1]};
        const d = pointToSegDist(wx,wy,p0,p1);
        if (d < bestd) { bestd = d; best = ei; }
      }
      if (best !== null && bestd < 0.45) {
        const r = await post('build_road', {edge: best});
        if (!r.ok) console.error('road fail', r);
        if (!(state && state.phase === 'setup')) mode = 'none';
        updateModeButtons();
      }
    } else if (mode === 'settle') {
      let best = null, bestd = 1e9;
      for (const vi of (state.valid.settlements||[])) {
        const v = state.board.vertices[vi];
        const d = Math.hypot(wx - v.x, wy - v.y);
        if (d < bestd) { bestd = d; best = vi; }
      }
      if (best !== null && bestd < 0.45) {
        const r = await post('build_settlement', {vertex: best});
        if (!r.ok) console.log('settle fail', r);
        if (!(state && state.phase === 'setup')) mode = 'none';
        updateModeButtons();
      }
    } else if (mode === 'city') {
      let best = null, bestd = 1e9;
      for (const v of state.board.vertices) {
        const d = Math.hypot(wx - v.x, wy - v.y);
        if (d < bestd) { bestd = d; best = v.i; }
      }
      if (best !== null && bestd < 0.45 && (state.valid.cities||[]).includes(best)) {
        const r = await post('build_city', {vertex: best});
        if (!r.ok) console.log('city fail', r);
        mode = 'none'; updateModeButtons();
      }
    }
  });
}

function bindButtons() {
  document.getElementById('btn-roll').onclick = async () => { await post('roll'); };
  document.getElementById('btn-end').onclick = async () => { await post('end_turn'); };
  const bn = document.getElementById('btn-new');
  if (bn) bn.onclick = async () => { await post('monitor_new'); mode='none'; pendingKnight=false; pendingRobberHex=null; };
  const ba = document.getElementById('btn-auto');
  if (ba) ba.onclick = async () => { await post('auto_setup'); };
  document.getElementById('btn-buydev').onclick = async () => { await post('buy_dev'); };
  document.getElementById('btn-playdev').onclick = async () => {
    const card = document.getElementById('dev-select').value;
    if (!card) return;
    if (card === 'knight') { pendingKnight = true; mode = 'robber'; updateModeButtons(); render(); return; }
    let params = {card};
    if (card === 'year_of_plenty') {
      const r1 = document.querySelector('#dev-params select[data-r="r1"]');
      const r2 = document.querySelector('#dev-params select[data-r="r2"]');
      if (!r1 || !r2) { alert('取り出す資源を選んでください。'); return; }
      params.r1 = r1.value; params.r2 = r2.value;
    } else if (card === 'monopoly') {
      const rs = document.querySelector('#dev-params select[data-r="resource"]');
      if (!rs) { alert('独占する資源を選んでください。'); return; }
      params.resource = rs.value;
    }
    const r = await post('play_dev', params);
    if (!r.ok) alert(r.error || 'このカードは今ターンに使えません。');
  };
  document.getElementById('btn-discard').onclick = async () => {
    if (!hasPendingDiscards()) return;
    let pid;
    if (VIEW === 'monitor') pid = Object.keys(state.pending_discards).map(Number).sort((a,b)=>a-b)[0];
    else pid = state.you;
    const need = state.pending_discards[String(pid)];
    const resources = {}; let total = 0;
    for (const inp of document.querySelectorAll('#discard-inputs input')) {
      const v = parseInt(inp.value || '0');
      if (v > 0) { resources[inp.dataset.res] = v; total += v; }
    }
    if (total !== need) { alert(`${need} 枚ちょうどを捨ててください（現在 ${total} 枚）。`); return; }
    await post('discard', {player: pid, resources});
  };
  document.getElementById('btn-robber-ok').onclick = async () => {
    if (pendingRobberHex === null) return;
    const sel = document.getElementById('robber-victim');
    const victim = sel.value === '' ? null : parseInt(sel.value);
    await sendRobberMove(pendingRobberHex, victim);
  };
  document.getElementById('btn-robber-cancel').onclick = () => {
    pendingRobberHex = null; pendingKnight = false; mode = 'none';
    updateModeButtons(); updatePanels(); render();
  };
  document.getElementById('btn-trade').onclick = async () => {
    const give = document.getElementById('trade-give').value;
    const receive = document.getElementById('trade-receive').value;
    if (!give || !receive || give === receive) { alert('渡す資源と受け取る資源は別にしてください。'); return; }
    const r = await post('trade_bank', {give, receive});
    if (!r.ok) alert('交換できませんでした（資源不足、または交換比率が違います）。');
  };
  document.getElementById('btn-pt-propose').onclick = async () => {
    const give = {}, want = {};
    document.querySelectorAll('#pt-give input').forEach(inp => { const v = parseInt(inp.value||'0'); if (v>0) give[inp.dataset.k]=v; });
    document.querySelectorAll('#pt-want input').forEach(inp => { const v = parseInt(inp.value||'0'); if (v>0) want[inp.dataset.k]=v; });
    const targets = [...document.querySelectorAll('#pt-targets input:checked')].map(i => parseInt(i.value));
    if (!Object.keys(give).length || !Object.keys(want).length) { alert('渡す資源とほしい資源の両方を指定してください。'); return; }
    if (!targets.length) { alert('提案する相手を1人以上選んでください。'); return; }
    const r = await post('trade_offer', {give, want, targets});
    if (!r.ok) alert(r.error || '提案できませんでした。');
  };
  document.getElementById('mode-road').onclick = () => setMode('road');
  document.getElementById('mode-settle').onclick = () => setMode('settle');
  document.getElementById('mode-city').onclick = () => setMode('city');
  document.getElementById('mode-none').onclick = () => setMode('none');
  document.getElementById('mode-robber').onclick = () => { pendingKnight=false; setMode('robber'); };
}

// ---------------------------------------------------------------------------
// Lobby board preview
//   While the room is still in the lobby the server already knows which map is
//   going to be played (it is reused by room_start). We render that board as a
//   read-only synthetic state so players can choose their turn order while
//   looking at the real board. Nothing is interactive (players=[], valid=[]).
// ---------------------------------------------------------------------------
let previewKey = null;
let previewHooked = false;

function previewBoard(board) {
  const c = canvas || document.getElementById('board');
  if (!c) return;
  canvas = c;
  if (!ctx) ctx = canvas.getContext('2d');
  if (!board) { previewKey = null; return; }
  if (!previewHooked) {
    previewHooked = true;
    window.addEventListener('resize', resize);
  }
  const key = JSON.stringify(board);
  if (key === previewKey) {
    // Same map: make sure the state still carries the board (getState resets
    // it to the "no game" payload on every poll) and re-fit if the box moved.
    if (!state || !state.board) {
      state = {
        phase: 'lobby', you: null, current: -1, players: [],
        board: board, dice: [], turn_number: 0, winner: null,
        valid: { roads: [], settlements: [], cities: [] },
      };
      mode = 'none';
    }
    fitCanvas();
    return;
  }
  previewKey = key;
  state = {
    phase: 'lobby', you: null, current: -1, players: [],
    board: board, dice: [], turn_number: 0, winner: null,
    valid: { roads: [], settlements: [], cities: [] },
  };
  mode = 'none';
  resize();
}

function boot(opts) {
  if (booted) return;
  booted = true;
  VIEW = (opts && opts.mode) || 'monitor';
  TOKEN = (opts && opts.token) || null;
  READONLY = !!(opts && opts.readonly);
  canvas = document.getElementById('board');
  canvas.style.cursor = READONLY ? 'default' : 'pointer';
  ctx = canvas.getContext('2d');
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.innerHTML = sidebarHTML();
  // Mobile: the action sheet starts closed so the board is fully visible.
  const tb = document.getElementById('btn-togglebar');
  if (tb) {
    tb.onclick = () => setBar(!barOpened());
    setBar(false);
  }
  const ta = document.getElementById('toggle-all');
  if (ta) {
    const syncAll = () => {
      const on = document.body.classList.toggle('show-all');
      ta.textContent = on ? '△ 基本の操作だけ表示' : '▽ 交易・発展カードなども表示';
    };
    ta.onclick = syncAll;
  }
  window.addEventListener('resize', () => { updateMobileToggle(); });
  if (!READONLY) {
    bindCanvas();
    bindButtons();
  }
  // Room-level control: available on the monitor even in view-only mode.
  const bi = document.getElementById('btn-init');
  if (bi) bi.onclick = async () => {
    if (!confirm('ゲームを初期化してロビーに戻しますか？（メンバーは残るので、ダイスを振り直して再開できます）')) return;
    await post('room_init');
    updateInitButton();
    render();
  };
  window.addEventListener('resize', resize);
  // Keep the canvas matched to its box no matter what changes it
  // (sheet open/close, orientation change, sidebar reflow, DPR change).
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => resize());
    ro.observe(document.getElementById('board-wrap'));
  }
  resize();
  getState();
  setInterval(getState, 2000);
}

window.CatanGame = {
  boot,
  previewBoard,
  resize,
  refresh: getState,
  isBooted: () => booted,
  setToken: (t) => { TOKEN = t; },
  get state() { return state; },
  get mode() { return mode; },
  set mode(v) { mode = v; },
  get view() { return VIEW; },
  get readonly() { return READONLY; },
  get scale() { return scale; },
  get canvas() { return canvas; },
  get pendingRobberHex() { return pendingRobberHex; },
  set pendingRobberHex(v) { pendingRobberHex = v; },
  get pendingKnight() { return pendingKnight; },
  set pendingKnight(v) { pendingKnight = v; },
  hexCenter, render, updatePanels, sendRobberMove, post,
  terrainTexture,
};
})();
