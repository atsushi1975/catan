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

// ---------------------------------------------------------------------------
// Sea
//   The area around the island is water. The tile is SEAMLESS: every mark is
//   drawn nine times (a 3x3 wrap) and the centre tile is cropped out, so the
//   left/right and top/bottom edges match exactly and no seam shows when the
//   tile repeats. The base colour is flat for the same reason.
// ---------------------------------------------------------------------------
function seaTexture(size) {
  const key = 'sea@' + size;
  const hit = TEXTURE_CACHE.get(key);
  if (hit) return hit;
  const off = document.createElement('canvas');
  off.width = off.height = size;
  const c = off.getContext('2d');

  // Draw everything on a 3x bigger canvas so wraps are simple offsets, then
  // crop the middle tile - the classic way to build a seamless texture.
  const big = document.createElement('canvas');
  big.width = big.height = size * 3;
  const b = big.getContext('2d');

  const base = '#84bcd4';
  b.fillStyle = base;
  b.fillRect(0, 0, size * 3, size * 3);

  const rnd = _rng(99);
  const put = (fn) => {
    for (let oy = -1; oy <= 1; oy++) {
      for (let ox = -1; ox <= 1; ox++) {
        b.save();
        b.translate(ox * size, oy * size);
        fn(b, rnd);
        b.restore();
      }
    }
  };

  // soft, gentle swells (low contrast)
  for (let i = 0; i < 20; i++) {
    const seedx = rnd(), seedy = rnd(), seedr = rnd();
    const x = seedx * size, y = seedy * size, r = size * (0.10 + seedr * 0.14);
    put((b) => {
      const rg = b.createRadialGradient(x, y, 0, x, y, r);
      rg.addColorStop(0, 'rgba(255,255,255,0.10)');
      rg.addColorStop(1, 'rgba(255,255,255,0)');
      b.fillStyle = rg;
      b.beginPath(); b.arc(x, y, r, 0, Math.PI * 2); b.fill();
    });
  }
  // a few soft, rounded wave marks
  for (let i = 0; i < 16; i++) {
    const x = rnd() * size, y = rnd() * size, r = size * (0.03 + rnd() * 0.035);
    const a0 = Math.PI * (1.15 + rnd() * 0.15), a1 = Math.PI * (1.7 + rnd() * 0.15);
    const alpha = 0.08 + rnd() * 0.08;
    put((b) => {
      b.strokeStyle = `rgba(255,255,255,${alpha})`;
      b.lineWidth = Math.max(1, size * 0.006);
      b.lineCap = 'round';
      b.beginPath(); b.arc(x, y, r, a0, a1); b.stroke();
    });
  }

  // crop the centre tile
  c.drawImage(big, size, size, size, size, 0, 0, size, size);
  TEXTURE_CACHE.set(key, off);
  return off;
}

// ---------------------------------------------------------------------------
// Dice (2d6)
//   Two dice sit in the bottom-right corner of the board so the current roll is
//   always readable without looking at the sidebar/text. They are painted, not
//   animated, and use the same soft hand-painted ivory/bone look as the rest of
//   the board (no photographic texture, no glow).
// ---------------------------------------------------------------------------

// Soft bone face texture: warm ivory gradient + gentle light + a few faint
// speckles. Drawn once per size and cached, like the terrain tiles.
function diceTexture(size) {
  const key = 'dice@' + size;
  const hit = TEXTURE_CACHE.get(key);
  if (hit) return hit;
  const off = document.createElement('canvas');
  off.width = off.height = size;
  const c = off.getContext('2d');
  const g = c.createLinearGradient(0, 0, 0, size);
  g.addColorStop(0, '#fbf6e9');
  g.addColorStop(0.55, '#f2e9d5');
  g.addColorStop(1, '#e2d4ba');
  c.fillStyle = g;
  c.fillRect(0, 0, size, size);
  // soft light from the upper-left so the face reads as slightly rounded
  const rg = c.createRadialGradient(size * 0.34, size * 0.30, size * 0.05,
                                    size * 0.5, size * 0.5, size * 0.78);
  rg.addColorStop(0, 'rgba(255,255,255,0.55)');
  rg.addColorStop(1, 'rgba(120,100,70,0.14)');
  c.fillStyle = rg; c.fillRect(0, 0, size, size);
  // faint age speckles
  const rnd = _rng(4242);
  for (let i = 0; i < 40; i++) {
    const x = rnd() * size, y = rnd() * size, r = size * (0.004 + rnd() * 0.010);
    c.globalAlpha = 0.05 + rnd() * 0.07;
    c.fillStyle = rnd() < 0.5 ? '#8a7a5a' : '#ffffff';
    c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill();
  }
  c.globalAlpha = 1;
  TEXTURE_CACHE.set(key, off);
  return off;
}

// Pip offsets in a unit square (0..1), top-left origin, for faces 1..6.
const DICE_PIPS = {
  1: [[0.5, 0.5]],
  2: [[0.28, 0.28], [0.72, 0.72]],
  3: [[0.26, 0.26], [0.5, 0.5], [0.74, 0.74]],
  4: [[0.28, 0.28], [0.72, 0.28], [0.28, 0.72], [0.72, 0.72]],
  5: [[0.28, 0.28], [0.72, 0.28], [0.5, 0.5], [0.28, 0.72], [0.72, 0.72]],
  6: [[0.28, 0.24], [0.72, 0.24], [0.28, 0.5], [0.72, 0.5], [0.28, 0.76], [0.72, 0.76]],
};

function _roundRect(c, x, y, w, h, r) {
  c.beginPath();
  c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r);
  c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r);
  c.arcTo(x, y, x + w, y, r);
  c.closePath();
}

// One die centred at (cx, cy). `value` 1..6 draws that face; anything else
// draws an empty face (the test hook uses it, the board never does).
function drawDie(cx, cy, side, value) {
  const r = side * 0.18;
  const x = cx - side / 2, y = cy - side / 2;
  // drop shadow so the die sits on the sea rather than floating
  ctx.save();
  ctx.globalAlpha = 0.28;
  ctx.fillStyle = '#000';
  _roundRect(ctx, x + side * 0.05, y + side * 0.07, side, side, r);
  ctx.fill();
  ctx.restore();
  // face
  ctx.save();
  _roundRect(ctx, x, y, side, side, r);
  ctx.clip();
  const tex = diceTexture(Math.max(8, Math.round(side)));
  ctx.drawImage(tex, x, y, side, side);
  ctx.restore();
  // thin dark outline (same weight as the pieces)
  ctx.strokeStyle = '#3a3128';
  ctx.lineWidth = Math.max(1, side * 0.045);
  _roundRect(ctx, x, y, side, side, r);
  ctx.stroke();
  // pips (the "one" pip is red, as on a Japanese die; the rest are near-black)
  if (value >= 1 && value <= 6) {
    const pipR = side * 0.085;
    const red = (value === 1);
    ctx.fillStyle = red ? '#c62828' : '#2c2620';
    for (const [px, py] of DICE_PIPS[value]) {
      ctx.beginPath();
      ctx.arc(x + px * side, y + py * side, pipR, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

// Draw the two dice in the top-right of the board (inside the sea square).
// Shown only once a game is in play AND dice have been thrown: the lobby (turn
// order draft), the initial-placement phase and a fresh turn before its roll
// all show no dice.
//
// Placement: the dice sit in the top-right corner of the sea, but are kept
// clear of the port marks (ports carry information, so the dice never cover
// them). Candidate spots are tried from the corner inwards/downwards and the
// first one that does not touch a port mark wins.
//
// Port geometry ("plan D"): a port sits on a coastal edge, and two short lines
// run from that edge's ends straight out to sea. A small mark (ship = 3:1,
// resource = 2:1) floats at their tip. Nothing is drawn ON the edge, so a port
// can never be mistaken for a road.
function _portGeom(pe) {
  const p1 = toCanvas({x:pe.x1, y:pe.y1});
  const p2 = toCanvas({x:pe.x2, y:pe.y2});
  const mid = {x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2};
  const dx = p2.x - p1.x, dy = p2.y - p1.y;
  const len = Math.hypot(dx, dy) || 1;
  let nx = -dy / len, ny = dx / len;          // edge normal
  // keep the normal pointing away from the middle of the board (= out to sea)
  if ((mid.x - canvas.width / 2) * nx + (mid.y - canvas.height / 2) * ny < 0) {
    nx = -nx; ny = -ny;
  }
  const L = Math.max(9, scale * 0.5);         // pier length
  const r = Math.max(11, scale * 0.3);        // white token radius
  const gap = Math.max(2, scale * 0.10);
  const fs = Math.max(10, Math.round(scale * 0.22));   // ratio text size
  const textGap = Math.max(2, scale * 0.05);
  // The ratio is printed under the token (above it for ports that point up, so
  // it never lands on the island). Pull the token inwards - i.e. shorten the
  // pier - when the text would otherwise leave the visible canvas (top/bottom
  // and left/right). The rightmost port of the middle row used to get cut off.
  const needV = r + textGap + fs + 3;
  const needH = r + fs * 0.8 + 4;
  let d = L + gap + r;
  if (ny < -0.2) d = Math.min(d, (mid.y - needV) / -ny);
  else if (ny > 0.2) d = Math.min(d, (canvas.height - needV - mid.y) / ny);
  if (nx > 0.2) d = Math.min(d, (canvas.width - needH - mid.x) / nx);
  else if (nx < -0.2) d = Math.min(d, (mid.x - needH) / -nx);
  d = Math.max(r + 4, d);
  const textAbove = ny < -0.2;
  const tip = {x: mid.x + nx * d, y: mid.y + ny * d};
  const textTop = textAbove ? tip.y - r - textGap - fs : tip.y + r + textGap;
  return {p1, p2, mid, nx, ny, L: Math.max(4, d - gap - r), r, fs,
          textTop, textAbove, tip};
}

function _portMarkBoxes(b) {
  const boxes = [];
  for (const pe of (b.port_edges || [])) {
    const g = _portGeom(pe);
    const r = g.r * 1.1;   // slack so a die never touches the token's rim
    boxes.push({
      x1: g.tip.x - r,
      y1: Math.min(g.tip.y - r, g.textTop),
      x2: g.tip.x + r,
      y2: Math.max(g.tip.y + r, g.textTop + g.fs),
    });
  }
  return boxes;
}

function _overlaps(box, other) {
  const m = 4;   // small clearance so the dice do not touch a label
  return !(box.x2 + m < other.x1 || box.x1 - m > other.x2 ||
           box.y2 + m < other.y1 || box.y1 - m > other.y2);
}

// Where the 2-dice group goes (centre), kept clear of the port labels AND the
// island. The old version only knew about ports and tried 12 hand-picked spots,
// so when the top-right corner happened to hold a port the dice jumped a long
// way across the board - and on a phone (where the sea is clipped) they could
// sit on the land. Now we scan the visible sea, prefer the spot nearest the
// top-right corner, and shrink the dice a little if nothing fits.
function _hexMarkBoxes(b) {
  const boxes = [];
  for (const h of (b.hexes || [])) {
    const c = toCanvas(hexCenter(h.q, h.r));
    // Circumscribed square of the hex (half = one hex radius) is plenty:
    // the dice are never allowed to touch the island.
    boxes.push({ x1: c.x - scale, y1: c.y - scale, x2: c.x + scale, y2: c.y + scale });
  }
  return boxes;
}

function _diceScan(side, half, cx, cy, labels, hexes) {
  const gap = side * 0.28;
  const groupW = side * 2 + gap;
  const groupH = side;
  const pad = side * 0.4;
  // The sea square is CENTRED in the canvas (see drawSea), but the sea is often
  // TALLER than the canvas, so its top edge lies above the visible area. Keep
  // the dice inside the intersection of the sea and the canvas.
  const sea = {
    x1: Math.max(cx - half, pad),
    y1: Math.max(cy - half, pad),
    x2: Math.min(cx + half, canvas.width - pad),
    y2: Math.min(cy + half, canvas.height - pad),
  };
  const minX = sea.x1 + groupW / 2;
  const maxX = sea.x2 - groupW / 2;
  const minY = sea.y1 + groupH / 2;
  const maxY = sea.y2 - groupH / 2;
  if (minX > maxX || minY > maxY) return null;
  const step = Math.max(6, side * 0.5);
  const cols = Math.max(1, Math.floor((maxX - minX) / step));
  const rows = Math.max(1, Math.floor((maxY - minY) / step));
  let best = null, bestD = Infinity;
  for (let iy = 0; iy <= rows; iy++) {
    const y = Math.min(maxY, minY + iy * step);
    for (let ix = 0; ix <= cols; ix++) {
      const x = Math.max(minX, maxX - ix * step);   // start at the right edge
      const box = { x1: x - groupW/2, y1: y - groupH/2,
                    x2: x + groupW/2, y2: y + groupH/2 };
      if (labels.some(l => _overlaps(box, l))) continue;
      if (hexes.some(h => _overlaps(box, h))) continue;
      const d = (maxX - x) * (maxX - x) + (minY - y) * (minY - y);
      if (d < bestD) { bestD = d; best = { x, y }; }
    }
  }
  if (!best) return null;
  const box = { x1: best.x - groupW/2, y1: best.y - groupH/2,
                x2: best.x + groupW/2, y2: best.y + groupH/2 };
  return { x: best.x, y: best.y, side, gap, groupW, groupH, box };
}

function dicePlacement() {
  const half = SEA_HALF * scale;
  const cx = canvas.width / 2, cy = canvas.height / 2;
  const baseSide = Math.max(18, scale * 0.8);
  const labels = _portMarkBoxes(state.board || {});
  const hexes = _hexMarkBoxes(state.board || {});
  let p = null;
  // Shrink up to 3 times (0.85 each) so the dice still fit when the visible sea
  // is tiny (phone with the action sheet open).
  for (let i = 0; i < 4 && !p; i++) {
    p = _diceScan(baseSide * Math.pow(0.85, i), half, cx, cy, labels, hexes);
  }
  if (p) return { x: p.x, y: p.y, side: p.side, gap: p.gap,
                  groupW: p.groupW, groupH: p.groupH, box: p.box, labels };
  // Nothing free at all: keep the old top-right corner rather than hide the
  // dice (they may overlap a port, which is at least visible and consistent).
  const side = baseSide, gap = side * 0.28;
  const groupW = side * 2 + gap, groupH = side;
  const pad = side * 0.4;
  const sea = {
    x1: Math.max(cx - half, pad),
    y1: Math.max(cy - half, pad),
    x2: Math.min(cx + half, canvas.width - pad),
    y2: Math.min(cy + half, canvas.height - pad),
  };
  const clamp = (v, lo, hi) => (lo > hi ? (lo + hi) / 2 : Math.min(hi, Math.max(lo, v)));
  const x = clamp(sea.x2 - groupW / 2, sea.x1 + groupW / 2, sea.x2 - groupW / 2);
  const y = clamp(sea.y1 + groupH / 2, sea.y1 + groupH / 2, sea.y2 - groupH / 2);
  const box = { x1: x - groupW/2, y1: y - groupH/2, x2: x + groupW/2, y2: y + groupH/2 };
  return { x, y, side, gap, groupW, groupH, box, labels };
}

function drawDice() {
  const PLAY_PHASES = ['roll', 'main', 'end'];
  if (!state || !PLAY_PHASES.includes(state.phase)) return;
  const dice = (state && Array.isArray(state.dice)) ? state.dice : [];
  if (dice.length < 2 || !dice[0] || !dice[1]) return;   // only once rolled
  const p = dicePlacement();
  const x1 = p.x - p.groupW/2 + p.side/2;
  const x2 = x1 + p.side + p.gap;
  drawDie(x1, p.y, p.side, dice[0]);
  drawDie(x2, p.y, p.side, dice[1]);
}

let canvas, ctx;
let state = null;
let mode = 'none';
let scale = 50;
let TOKEN = null;
let VIEW = 'monitor';        // 'monitor' | 'client'
// How many polls in a row have reported "no seat" (see getState).
let staleHits = 0;
let booted = false;
let READONLY = false;        // monitor mode: view-only, no game actions
// The "g | you:..." corner overlay is a debug aid, not player UI.
// It only appears when the page is opened with ?diag=1.
const DIAG_ON = (() => {
  try { return new URLSearchParams(location.search).has('diag'); } catch (e) { return false; }
})();

let pendingKnight = false;
let pendingRobberHex = null;
let pendingDiscardPid = null;

const phaseJa = {setup:'初期配置', roll:'サイコロ', main:'建設・交易', end:'終了'};

// ---------------------------------------------------------------------------
// Public event log + toasts
//   The server sends `events` (open information: dev cards played, the robber,
//   longest road / largest army, the win, ...). Clients only show events they
//   have not shown yet (`seenEventId`). A new event raises a short toast near
//   the centre of the screen AND is appended to the log panel.
// ---------------------------------------------------------------------------
let seenEventId = null;       // highest event id already handled (null = first load)
let wasMyTurn = false;        // previous poll: was it this player's turn?
let logLines = [];            // recent events, newest last
const LOG_MAX = 20;

function pushLog(ev, priv) {
  logLines.push({ id: ev.id, kind: ev.kind || 'info', text: ev.text || '', priv: !!priv });
  if (logLines.length > LOG_MAX) logLines = logLines.slice(-LOG_MAX);
}

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

function renderEventLog() {
  const el = document.getElementById('event-log');
  if (!el) return;
  if (!logLines.length) { el.innerHTML = '<div class="muted" style="font-size:12px;">まだ何もありません</div>'; return; }
  el.innerHTML = logLines.slice().reverse().map(l =>
    '<div class="log-line kind-' + l.kind + (l.priv ? ' private' : '') + '">' + escapeHtml(l.text) + '</div>').join('');
}

// A toast near the centre of the screen; fades out on its own.
function showToast(text, kind, priv, ms) {
  let host = document.getElementById('toast-host');
  if (!host) {
    host = document.createElement('div');
    host.id = 'toast-host';
    document.body.appendChild(host);
  }
  const t = document.createElement('div');
  t.className = 'toast kind-' + (kind || 'info') + (priv ? ' private' : '');
  t.textContent = text;
  host.appendChild(t);
  void t.offsetWidth;
  t.classList.add('show');
  setTimeout(() => {
    t.classList.remove('show');
    setTimeout(() => { if (t.parentNode) t.parentNode.removeChild(t); }, 400);
  }, ms || 3200);
}

// Called on every /state poll. Shows anything new since the last poll.
function handleEvents(events) {
  if (!Array.isArray(events)) return;
  if (seenEventId === null) {
    // First load: fill the log with history, but do NOT toast the whole back-log.
    for (const ev of events) pushLog(ev);
    if (events.length) seenEventId = events[events.length - 1].id;
    renderEventLog();
    return;
  }
  for (const ev of events) {
    if (ev.id > seenEventId) {
      pushLog(ev);
      // The dice are always drawn on the board, so a throw does not need a
      // toast - it would just be noise. It still goes into the log.
      if (ev.kind !== 'roll') showToast(ev.text, ev.kind);
    }
  }
  if (events.length) seenEventId = Math.max(seenEventId, events[events.length - 1].id);
  renderEventLog();
}

// Private events: text only THIS player may see (what was stolen from / by
// them, the dev card they drew, ...). The server sends them to the matching
// seat only; the monitor and spectators always get an empty list. Own id
// counter (separate from the public one).
let seenPrivateId = null;

function handlePrivateEvents(events) {
  if (!Array.isArray(events)) return;
  if (seenPrivateId !== null && events.length && events[events.length - 1].id < seenPrivateId) {
    seenPrivateId = null;       // ids restarted (a new game): start over
  }
  if (seenPrivateId === null) {
    // First load: history goes into the log, no toast for the whole back-log.
    for (const ev of events) pushLog(ev, true);
    seenPrivateId = events.length ? events[events.length - 1].id : 0;
    renderEventLog();
    return;
  }
  for (const ev of events) {
    if (ev.id > seenPrivateId) {
      pushLog(ev, true);
      showToast(ev.text, ev.kind, true);
    }
  }
  if (events.length) seenPrivateId = Math.max(seenPrivateId, events[events.length - 1].id);
  renderEventLog();
}

// A player page must never silently look like a spectator board. If the server
// says the viewer has no seat, say so on screen instead of showing the hexes
// with no explanation.
// Same idea as the status line in client.html, but from game.js: after the
// board boots we need to know what /state thinks of this browser (role/you).
// The two used to disagree - /room said "seat ok" and /state said "spectator" -
// and the page just bounced back to the lobby with no explanation.
function diagGame() {
  if (VIEW !== 'client') return;
  if (!DIAG_ON) {
    const old = document.getElementById('g-diag');
    if (old) old.remove();
    return;
  }
  let d = document.getElementById('g-diag');
  if (!d) {
    d = document.createElement('div');
    d.id = 'g-diag';
    d.style.cssText = 'position:fixed;right:4px;bottom:14px;z-index:70;font-size:10px;' +
      'color:#7f9;pointer-events:none;text-shadow:0 0 2px #000';
    document.body.appendChild(d);
  }
  const y = (state && state.you !== null && state.you !== undefined) ? state.you : '-';
  d.textContent = 'g | you:' + y +
    ' | role:' + (state ? state.role : '-') +
    ' | ph:' + (state ? state.phase : '-') +
    ' | cur:' + (state ? state.current : '-') +
    ' | n:' + (state && state.players ? state.players.length : '-');
}

function updateRoleBanner() {
  diagGame();
  if (VIEW !== 'client') return;
  const missing = !state || state.role === 'spectator';
  let bar = document.getElementById('role-bar');
  if (!missing) { if (bar) bar.remove(); return; }
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'role-bar';
    bar.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:60;padding:6px 10px;' +
      'background:#5a4500;color:#ffe9a8;font-size:12px;text-align:center';
    document.body.appendChild(bar);
  }
  bar.textContent = '観戦モード：このブラウザはこのゲームの席を持っていません';
}

// ---------------------------------------------------------------------------
// Leaving the game
//   * after the game (winner decided): "ロビーに戻る" calls leave
//   * during the game: "退出する" asks the others (exit_request); they answer
//     from a banner at the top of the screen, which never blocks the board
//   * the server aborts the game when everybody agrees and tells us through
//     state.notice (the room is reset, so /state then has no players at all)
// ---------------------------------------------------------------------------
let exitReq = null;           // pending request from the last poll (+ `got`: when we received it)
let exitVoted = null;         // id of the request this player has already answered
let exitCancelled = false;    // this player cancelled their own request: no "refused" toast

function isSeated() {
  return VIEW === 'client' && !READONLY && !!state &&
    state.you !== null && state.you !== undefined;
}
function isGameOver() {
  return !!state && state.winner !== null && state.winner !== undefined;
}

// A toast raised just before location.reload() would vanish with the page, so
// it is parked in sessionStorage and shown by the freshly loaded page (the lobby).
function flashAfterReload(text, ms) {
  try { sessionStorage.setItem('catan_flash', JSON.stringify({ text: text, ms: ms })); } catch (e) {}
}
function showFlash() {
  let f = null;
  try {
    f = JSON.parse(sessionStorage.getItem('catan_flash') || 'null');
    sessionStorage.removeItem('catan_flash');
  } catch (e) {}
  if (f && f.text) showToast(f.text, 'info', false, f.ms);
}

// Drop the saved token so the next load shows the join form (same bookkeeping
// as the stale-token branch in getState and the lobby's own leave button).
function forgetSeatLocally() {
  try {
    const t = JSON.parse(localStorage.getItem('catan_tokens') || '{}') || {};
    delete t[sessionStorage.getItem('catan_tabid')];
    localStorage.setItem('catan_tokens', JSON.stringify(t));
    const last = JSON.parse(localStorage.getItem('catan_last_seat') || '{}') || {};
    if (last && last.token && last.token === TOKEN) localStorage.removeItem('catan_last_seat');
  } catch (e) {}
}

// state.notice: the game was aborted. Handled before anything else in getState,
// so neither the "no players -> reload" shortcut nor the "connection lost"
// alert gets in the way. Every notice is shown once (the id survives reloads
// for 2 minutes, see below).
function handleNotice(raw) {
  const n = raw && raw.notice;
  if (!n || VIEW !== 'client') return false;
  // A seat in a running game means the notice is about an OLDER game (it
  // outlives the reset for a while): never throw a live player out of theirs.
  if (raw.players && raw.you !== null && raw.you !== undefined) return false;
  let seen = null;
  try { seen = JSON.parse(sessionStorage.getItem('catan_notice_seen') || 'null'); } catch (e) {}
  // Ids start again at 1 after a server restart, so a remembered id only counts
  // for a little longer than the notice lives on the server (60 s).
  if (seen && String(seen.id) === String(n.id) && Date.now() - seen.at < 120000) return false;
  try { sessionStorage.setItem('catan_notice_seen', JSON.stringify({ id: n.id, at: Date.now() })); } catch (e) {}
  flashAfterReload(n.text || 'ゲームは中止されました', 8000);
  forgetSeatLocally();
  location.reload();
  return true;
}

// Called on every poll that carries a game: remember the request, and tell the
// asker when it ended without the game being aborted.
function handleExitRequest(raw) {
  const er = raw.exit_request || null;
  const prev = exitReq;
  const gone = !er || (prev && er.id !== prev.id);
  if (prev && prev.mine && gone && !exitCancelled && !isGameOver()) {
    showToast('退出は許可されませんでした', 'info');
  }
  if (gone) exitCancelled = false;
  exitReq = er ? Object.assign({}, er, { got: Date.now() }) : null;
  updateExitUI();
}

function exitRemaining() {
  if (!exitReq) return 0;
  return Math.max(0, exitReq.remaining - Math.floor((Date.now() - exitReq.got) / 1000));
}

async function sendExit(action, extra) {
  let r = null;
  try { r = await post(action, extra || {}); } catch (e) { r = null; }
  if (!r || !r.ok) showToast((r && r.error) || '送信できませんでした', 'info');
  return !!(r && r.ok);
}

function renderExitBanner() {
  let bar = document.getElementById('exit-banner');
  const er = exitReq;
  const show = isSeated() && !!er && !isGameOver() &&
    (er.mine || (er.my_vote === null && exitVoted !== er.id));
  if (!show) { if (bar) bar.remove(); return; }
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'exit-banner';
    bar.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:65;padding:3px 8px;' +
      'background:#3a1f1f;color:#ffd0d0;font-size:12px;line-height:1.3;text-align:center;' +
      'border-bottom:2px solid #ff6b6b;box-shadow:0 2px 8px rgba(0,0,0,.5)';
    document.body.appendChild(bar);
  }
  // Rebuild the buttons only when the request (or who is looking at it) changes,
  // so the countdown tick never swallows a tap.
  const key = (er.mine ? 'm' : 'o') + er.id;
  if (bar.dataset.key !== key) {
    bar.dataset.key = key;
    bar.innerHTML = '<span class="exit-text"></span> <span class="exit-btns"></span>';
    const box = bar.querySelector('.exit-btns');
    const mk = (label, fn) => {
      const b = document.createElement('button');
      b.className = 'btn';
      b.style.cssText = 'padding:2px 10px;font-size:12px;margin:1px 2px;';   // keep the bar low
      b.textContent = label;
      b.onclick = fn;
      box.appendChild(b);
    };
    if (er.mine) {
      mk('取り消す', async () => {
        exitCancelled = true;
        if (!(await sendExit('exit_cancel'))) exitCancelled = false;
      });
    } else {
      const vote = async (approve) => {
        exitVoted = er.id;                      // close the banner at once
        renderExitBanner();
        if (!(await sendExit('exit_vote', { id: er.id, approve: approve }))) {
          exitVoted = null;                     // not counted: let the player answer again
          renderExitBanner();
        }
      };
      mk('許可する', () => vote(true));
      mk('許可しない', () => vote(false));
    }
  }
  const sec = exitRemaining();
  bar.querySelector('.exit-text').textContent = er.mine
    ? '他のプレイヤーの返事を待っています（残り' + sec + '秒）'
    : er.by + 'さんが退出ボタンを押しました。許可しますか？（残り' + sec + '秒）';
}

function updateExitUI() {
  const panel = document.getElementById('exit-panel');
  if (panel) {
    const over = isGameOver();
    panel.style.display = isSeated() ? 'block' : 'none';
    const be = document.getElementById('btn-exit');
    const bl = document.getElementById('btn-backlobby');
    const note = document.getElementById('exit-note');
    if (be) { be.style.display = over ? 'none' : ''; be.disabled = !!exitReq; }
    if (bl) bl.style.display = over ? '' : 'none';
    if (note) note.style.display = over ? 'block' : 'none';
  }
  renderExitBanner();
}

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
  if (handleNotice(raw)) return;      // game aborted: before any "no players / no seat" handling
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
  // Announce that the turn has come back to this player. The toast is fired on
  // the transition (not on every poll), so it shows up exactly once per turn.
  const myTurnNow = VIEW === 'client' && !READONLY &&
    state.you !== null && state.you !== undefined && state.you === state.current;
  if (myTurnNow && !wasMyTurn) showToast('あなたの手番です', 'mine');
  wasMyTurn = myTurnNow;
  // Stale / missing token while a game is running: our seat no longer exists
  // (e.g. the room was reset or the server restarted). There is nothing we can
  // do on this screen - go back to the lobby so the player can rejoin.
  //
  // A single null is NOT proof: right after a phone wakes up the first poll can
  // come back before the connection is really up, and acting on it would throw
  // the player's seat away for good. Require two polls in a row to agree.
  //
  // Guard with a flag that SURVIVES the reload: without it this would reload the
  // page, boot straight back into the still-running game and loop forever.
  if (VIEW === 'client' && (state.you === null || state.you === undefined)) {
    staleHits++;
    if (staleHits < 2) return;          // wait for the next poll (1.5s)
    let warned = false;
    try { warned = sessionStorage.getItem('catan_stale_warned') === '1'; } catch (e) {}
    if (!warned) {
      try { sessionStorage.setItem('catan_stale_warned', '1'); } catch (e) {}
      alert('接続が切れました（席が見つかりません）。もう一度入室してください。');
    }
    // Forget the dead token so the lobby offers the join form instead of
    // bouncing back into the game we can no longer take part in.
    try {
      const t = JSON.parse(localStorage.getItem('catan_tokens') || '{}') || {};
      delete t[sessionStorage.getItem('catan_tabid')];
      localStorage.setItem('catan_tokens', JSON.stringify(t));
      // The wake-up fallback must forget it too, or the next boot would try to
      // re-claim this dead seat again.
      const last = JSON.parse(localStorage.getItem('catan_last_seat') || '{}') || {};
      if (last && last.token && last.token === TOKEN) localStorage.removeItem('catan_last_seat');
    } catch (e) {}
    location.reload();
    return;
  }
  staleHits = 0;
  updateRoleBanner();
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
  handleEvents(state.events);
  handlePrivateEvents(state.private_events);
  handleExitRequest(state);
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
  if (VIEW === 'monitor') return playerAt(state.current);
  return playerAt(state.you);
}
// Safe lookup: `state.current` / `state.you` / `state.winner` can point outside
// the player list (a seat that left, a game that just ended, ...). Reading
// `.name` off the result used to throw and froze the whole UI mid-render.
function playerAt(id) {
  if (!state || !Array.isArray(state.players)) return null;
  if (id === null || id === undefined) return null;
  return state.players[id] || null;
}
function playerName(id) {
  const p = playerAt(id);
  return p ? (p.name || '—') : '—';
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
// Colour names come from the server (the lobby lets each seat pick one).
const COLOR_HEX = {
  red: '#e53935', blue: '#1e88e5', white: '#ffffff', orange: '#fb8c00',
};
function playerColor(id) {
  const p = (state && state.players)
    ? state.players.find(x => x && x.id === id) : null;
  if (p && p.color && COLOR_HEX[p.color]) return COLOR_HEX[p.color];
  // fallback: the classic seat order
  const byId = ['red', 'blue', 'white', 'orange'][id];
  return COLOR_HEX[byId] || '#888';
}

// A darker shade of a player colour, used for the "side" faces of a piece so a
// flat 2D shape still reads as a small block (like the original wooden pieces).
function darkenColor(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.max(0, Math.round(((n >> 16) & 255) * (1 - amt)));
  const g = Math.max(0, Math.round(((n >> 8) & 255) * (1 - amt)));
  const b = Math.max(0, Math.round((n & 255) * (1 - amt)));
  return `rgb(${r},${g},${b})`;
}

// ---------------------------------------------------------------------------
// Pieces (settlement / city)
//   Flat 2D silhouettes of the first-edition (1995) wooden blocks:
//     settlement - a small pentagon (home plate, point up)
//     city       - a bigger block with a stepped, battlement-like top edge
//   No shadows, no side faces, no internal detail: just the outline filled with
//   the player colour and a THIN black contour.
// ---------------------------------------------------------------------------
function polyPath(pts) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
}

// thin black outline, scaled with the board (default zoom: ~1.3px)
const pieceLineWidth = () => Math.max(0.8, scale * 0.026);

// Stroke the current path with a thin black contour. `miter` keeps the peaks
// SHARP (a round join would blunt the pentagon's point).
function pieceStroke() {
  ctx.strokeStyle = '#111';
  ctx.lineWidth = pieceLineWidth();
  ctx.lineJoin = 'miter';
  ctx.miterLimit = 2;
  ctx.stroke();
}

function drawSettlement(px, py, color) {
  const s = (scale / 50) * 0.7;    // 0.7x: a compact piece on a busy board
  const w = 11 * s;        // half width
  const peak = 12 * s;     // how far the point rises above the shoulders
  const h = 20 * s;        // total height
  const topY = py - h * 0.5 + peak * 0.5;
  polyPath([
    [px, topY - peak],           // apex (point up, like an upside-down home plate)
    [px + w, topY],
    [px + w, topY + h - peak],
    [px - w, topY + h - peak],
    [px - w, topY],
  ]);
  ctx.fillStyle = color; ctx.fill();
  pieceStroke();
}

function drawCity(px, py, color) {
  const s = (scale / 50) * 0.7;   // 0.7x: keep the city compact next to a settlement
  const w = 18 * s;        // half width of the base rectangle (full width = 2w)
  const bh = w;            // base rectangle height: 1:2 against the full width
  const peak = 10 * s;     // the pentagon's point (same feel as a settlement)
  const notch = 4 * s;     // how much the left half's top edge is lowered
  const baseY = py + (bh + peak) * 0.5;   // bottom edge
  const shoulderY = baseY - bh;           // top edge of the RIGHT half (pentagon base)
  const leftTopY = shoulderY + notch;     // lower top edge of the LEFT half
  const topY = shoulderY - peak;          // top of the pentagon point
  const apexX = px + w * 0.5;             // centre of the RIGHT half
  // A deformed heptagon: the left half is a bar whose top edge sits a little
  // LOWER than the pentagon's shoulders, so the piece reads as a raised keep.
  //
  //                 ___
  //                /   \
  //          ______     |
  //               |     |
  //               |_____|
  //
  polyPath([
    [apexX, topY],                       // 1 apex of the pentagon
    [px + w, shoulderY],                 // 2 right shoulder
    [px + w, baseY],                     // 3 bottom right
    [px - w, baseY],                     // 4 bottom left
    [px - w, leftTopY],                  // 5 top-left of the lowered left bar
    [px, leftTopY],                      // 6 top-right of the lowered left bar
    [px, shoulderY],                     // 7 pentagon's left base (step up)
  ]);
  ctx.fillStyle = color; ctx.fill();
  pieceStroke();
}

// The robber: a small dark figure (head + shoulders + a cloak), like the
// first-edition wooden piece seen from behind. Drawn as one flat silhouette
// with the same thin black contour as the buildings.
function drawRobber(px, py) {
  const s = (scale / 50) * 0.8 * 1.2 * 1.5;   // 1.2x then 1.5x: make the robber stand out
  const dark = '#2b2b2b';
  ctx.save();
  // cloak / body: a rounded trapezoid
  ctx.beginPath();
  ctx.moveTo(px - 8*s, py + 10*s);
  ctx.quadraticCurveTo(px - 9*s, py - 1*s, px - 3.5*s, py - 3*s);
  ctx.lineTo(px + 3.5*s, py - 3*s);
  ctx.quadraticCurveTo(px + 9*s, py - 1*s, px + 8*s, py + 10*s);
  ctx.closePath();
  ctx.fillStyle = dark; ctx.fill();
  ctx.strokeStyle = '#111'; ctx.lineWidth = pieceLineWidth();
  ctx.lineJoin = 'round'; ctx.stroke();
  // head
  ctx.beginPath();
  ctx.arc(px, py - 7*s, 4.5*s, 0, Math.PI*2);
  ctx.fillStyle = dark; ctx.fill(); ctx.stroke();
  // a pale face sliver so the figure reads at small sizes
  ctx.beginPath();
  ctx.arc(px + 0.8*s, py - 7.6*s, 2.2*s, 0, Math.PI*2);
  ctx.fillStyle = 'rgba(230,220,190,0.9)'; ctx.fill();
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Roads
//   A road does not run corner-to-corner along the whole edge: it is a short,
//   thick, round-ended bar sitting in the middle of the edge, so it reads as a
//   piece laid on the board and never collides with the settlements/cities at
//   the two vertices. Like the buildings, it gets a thin BLACK outline: the
//   bar is stroked twice - first the contour (slightly wider), then the colour.
//     inset  - how far (as a fraction of the edge) each end is pulled inward
//     width  - bar thickness in canvas pixels (the colour part)
// ---------------------------------------------------------------------------
function drawRoadBar(p0, p1, color, width, inset) {
  const dx = p1.x - p0.x, dy = p1.y - p0.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const cut = len * (inset == null ? 0.22 : inset);   // pull both ends inward
  const ax = p0.x + ux * cut, ay = p0.y + uy * cut;
  const bx = p1.x - ux * cut, by = p1.y - uy * cut;
  ctx.save();
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(ax, ay);
  ctx.lineTo(bx, by);
  // 1) black contour (a hair wider so it shows as a rim on both sides)
  ctx.strokeStyle = '#111';
  ctx.lineWidth = width + Math.max(1.6, pieceLineWidth() * 2);
  ctx.stroke();
  // 2) the road colour on top
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
  ctx.restore();
}
// ---------------------------------------------------------------------------
// Port / resource marks (vector, no images)
//   Deliberately small and text-free: a ship means 3:1, a resource means 2:1.
//   Keeping the ratio as an icon (not a label box) is what stops the rim of the
//   board from turning into a wall of text.
// ---------------------------------------------------------------------------
function _markShadow() {
  // a soft dark halo keeps a light icon readable on the sea texture
  ctx.shadowColor = 'rgba(0,0,0,0.75)';
  ctx.shadowBlur = Math.max(2, scale * 0.05);
}

function drawShipIcon(x, y, s, flat) {
  ctx.save();
  ctx.translate(x, y);
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  if (flat) { ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; } else _markShadow();
  const lw = Math.max(1, s * 0.14);
  // hull
  ctx.beginPath();
  ctx.moveTo(-s, s * 0.12);
  ctx.lineTo(s, s * 0.12);
  ctx.lineTo(s * 0.6, s * 0.66);
  ctx.lineTo(-s * 0.6, s * 0.66);
  ctx.closePath();
  ctx.fillStyle = '#a1887f';
  ctx.fill();
  ctx.shadowColor = 'transparent';
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = lw;
  ctx.stroke();
  // mast (grey: white vanished against the white port token)
  ctx.strokeStyle = '#9e9e9e';
  ctx.beginPath();
  ctx.moveTo(0, s * 0.12);
  ctx.lineTo(0, -s * 1.0);
  ctx.stroke();
  // sail
  ctx.beginPath();
  ctx.moveTo(s * 0.1, -s * 0.95);
  ctx.lineTo(s * 0.1, -s * 0.12);
  ctx.lineTo(s * 0.9, -s * 0.5);
  ctx.closePath();
  ctx.fillStyle = '#fffdf5';
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.stroke();
  ctx.restore();
}

// kind: wood / brick / sheep / wheat / ore
function drawResourceIcon(kind, x, y, s, flat) {
  ctx.save();
  ctx.translate(x, y);
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  if (flat) { ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; } else _markShadow();
  const lw = Math.max(1, s * 0.12);
  if (kind === 'wood') {
    // two logs lying side by side (pale cut faces to the left): a single log
    // looked like a random bar, a pair reads as timber at a glance
    const log = (dy, rot) => {
      ctx.save();
      ctx.translate(0, dy);
      ctx.rotate(rot);
      ctx.beginPath();
      _roundRect(ctx, -s * 0.92, -s * 0.23, s * 1.84, s * 0.46, s * 0.23);
      ctx.fillStyle = '#a1724a';
      ctx.fill();
      ctx.shadowColor = 'transparent';
      ctx.strokeStyle = 'rgba(0,0,0,0.55)';
      ctx.lineWidth = Math.max(1, s * 0.1);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(-s * 0.62, 0, s * 0.21, 0, Math.PI * 2);
      ctx.fillStyle = '#e6cfa8';
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    };
    log(-s * 0.25, -Math.PI / 18);
    log(s * 0.25, -Math.PI / 18);
  } else if (kind === 'brick') {
    ctx.beginPath();
    _roundRect(ctx, -s * 0.95, -s * 0.58, s * 1.9, s * 1.16, s * 0.14);
    ctx.fillStyle = '#c0562b';
    ctx.fill();
    ctx.shadowColor = 'transparent';
    ctx.strokeStyle = 'rgba(0,0,0,0.6)';
    ctx.lineWidth = lw;
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(-s * 0.95, 0); ctx.lineTo(s * 0.95, 0);
    ctx.moveTo(0, -s * 0.58); ctx.lineTo(0, 0);
    ctx.stroke();
  } else if (kind === 'sheep') {
    // A ball of wool, NOT a sheep: the resource is 羊毛, and a sheep silhouette
    // at 30 px just read as a cloud. Wound strands + a loose end say "wool".
    const R = s * 0.86;
    ctx.shadowColor = 'transparent';
    ctx.beginPath();
    ctx.arc(0, -s * 0.05, R, 0, Math.PI * 2);
    ctx.fillStyle = '#f4ecd8';
    ctx.fill();
    ctx.strokeStyle = '#3e2723';
    ctx.lineWidth = Math.max(1.2, s * 0.13);
    ctx.stroke();
    // wound yarn, clipped to the ball
    ctx.save();
    ctx.beginPath();
    ctx.arc(0, -s * 0.05, R, 0, Math.PI * 2);
    ctx.clip();
    ctx.strokeStyle = '#c3ad84';
    ctx.lineWidth = Math.max(1, s * 0.11);
    for (const k of [-0.5, 0, 0.5]) {
      ctx.beginPath();
      ctx.ellipse(k * R * 0.75, -s * 0.05, R * 0.62, R * 1.05, 0.55, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();
    // the loose end trailing out of the ball
    ctx.strokeStyle = '#c3ad84';
    ctx.lineWidth = Math.max(1, s * 0.12);
    ctx.beginPath();
    ctx.moveTo(R * 0.6, -s * 0.05 + R * 0.6);
    ctx.quadraticCurveTo(R * 1.05, R * 0.95, R * 1.4, R * 0.7);
    ctx.stroke();
  } else if (kind === 'wheat') {
    ctx.strokeStyle = '#d9a300';
    ctx.lineWidth = Math.max(1, s * 0.16);
    ctx.beginPath();
    ctx.moveTo(0, s * 0.98);
    ctx.lineTo(0, -s * 0.75);
    ctx.stroke();
    ctx.shadowColor = 'transparent';
    ctx.fillStyle = '#f6c445';
    for (let i = 0; i < 3; i++) {
      const yy = -s * 0.62 + i * s * 0.34;
      for (const side of [-1, 1]) {
        ctx.beginPath();
        ctx.ellipse(side * s * 0.24, yy, s * 0.17, s * 0.3, side * 0.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  } else if (kind === 'ore') {
    // Two iron ingots (a single one read as a bar, not as metal): trapezoid
    // body + bright top face each, the front one overlapping the back one.
    const bar = (cx, cy, w, h) => {
      ctx.beginPath();
      ctx.moveTo(cx - w * 0.62, cy - h);
      ctx.lineTo(cx + w * 0.62, cy - h);
      ctx.lineTo(cx + w, cy);
      ctx.lineTo(cx - w, cy);
      ctx.closePath();
      ctx.fillStyle = '#7c8b95';
      ctx.fill();
      ctx.shadowColor = 'transparent';
      ctx.strokeStyle = 'rgba(0,0,0,0.6)';
      ctx.lineWidth = lw;
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(cx - w * 0.62, cy - h);
      ctx.lineTo(cx + w * 0.62, cy - h);
      ctx.lineTo(cx + w * 0.8, cy - h * 0.42);
      ctx.lineTo(cx - w * 0.8, cy - h * 0.42);
      ctx.closePath();
      ctx.fillStyle = '#d5dee2';
      ctx.fill();
      ctx.strokeStyle = 'rgba(0,0,0,0.35)';
      ctx.lineWidth = Math.max(1, lw * 0.6);
      ctx.stroke();
    };
    // identical bars (a smaller back one looked like forced perspective)
    bar(s * 0.2, s * 0.02, s * 0.66, s * 0.42);     // back bar (upper right)
    bar(-s * 0.2, s * 0.42, s * 0.66, s * 0.42);    // front bar (lower left)
  }
  ctx.restore();
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

// World-space half-size of the water square (covers the island AND the port
// labels/text, but not the whole canvas).
const SEA_HALF = 5.6;

function drawSea() {
  const half = SEA_HALF * scale;
  const cx = canvas.width / 2, cy = canvas.height / 2;
  const x0 = cx - half, y0 = cy - half, side = half * 2;
  const tile = Math.max(64, Math.round(scale * 4));
  const tex = seaTexture(tile);
  const r = scale * 0.6;                 // softly rounded corners
  ctx.save();
  // clip to a rounded square so the water reads as a "physical" sea tile
  ctx.beginPath();
  ctx.moveTo(x0 + r, y0);
  ctx.arcTo(x0 + side, y0, x0 + side, y0 + side, r);
  ctx.arcTo(x0 + side, y0 + side, x0, y0 + side, r);
  ctx.arcTo(x0, y0 + side, x0, y0, r);
  ctx.arcTo(x0, y0, x0 + side, y0, r);
  ctx.closePath();
  ctx.clip();
  for (let y = y0; y < y0 + side; y += tile) {
    for (let x = x0; x < x0 + side; x += tile) {
      ctx.drawImage(tex, x, y);
    }
  }
  // soft edge so it blends into the dark background
  ctx.lineWidth = 3;
  ctx.strokeStyle = 'rgba(255,255,255,0.18)';
  ctx.beginPath();
  ctx.moveTo(x0 + r, y0);
  ctx.arcTo(x0 + side, y0, x0 + side, y0 + side, r);
  ctx.arcTo(x0 + side, y0 + side, x0, y0 + side, r);
  ctx.arcTo(x0, y0 + side, x0, y0, r);
  ctx.arcTo(x0, y0, x0 + side, y0, r);
  ctx.closePath();
  ctx.stroke();
  ctx.restore();
}

function render() {
  if (!ctx) return;
  ctx.fillStyle = '#1a1a1a';
  ctx.fillRect(0,0,canvas.width,canvas.height);
  if (!state || !state.board) return;
  ctx.save();
  drawSea();
  ctx.restore();
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
      // Beige token, closer to the original cardboard chip (it used to be a
      // white disc, which read as "screen" rather than "piece").
      // Sized from `scale` so it stays proportional on a phone (it used to be
      // a fixed 19 px, which read too small next to the hexes).
      const chipR = Math.max(20, Math.round(scale * 0.34));
      // Solid deeper beige (no lighter inner disc): at phone size the two-tone
      // fill washed out and read almost white.
      ctx.fillStyle = '#d6c08c';
      ctx.beginPath(); ctx.arc(cc.x, cc.y - 2, chipR, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle = (h.number===6||h.number===8) ? '#c00' : '#5b4a2a';
      ctx.lineWidth = Math.max(3, chipR * 0.14);
      ctx.beginPath(); ctx.arc(cc.x, cc.y - 2, chipR, 0, Math.PI*2); ctx.stroke();
      ctx.fillStyle = (h.number===6||h.number===8) ? '#c00' : '#000';
      ctx.font = `bold ${Math.max(17, Math.round(scale * 0.3))}px sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(h.number, cc.x, cc.y - 2);
    }
    // While the victim is still being chosen the robber already stands on the
    // tapped hex (display only; the server moves it on 奪う, cancel puts it back).
    const robberHere = pendingRobberHex !== null
      ? (h.q === pendingRobberHex[0] && h.r === pendingRobberHex[1])
      : h.robber;
    if (robberHere) {
      // drawn on top of the number chip: the robber is allowed to cover it
      drawRobber(cc.x, cc.y - 2);
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
    if (e.road_owner === null) {
      // faint hint of an empty edge (kept very subtle)
      ctx.strokeStyle = 'rgba(255,255,255,0.12)';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(p0.x,p0.y); ctx.lineTo(p1.x,p1.y); ctx.stroke();
    } else {
      // a short, thick, round-ended bar in the middle of the edge
      drawRoadBar(p0, p1, playerColor(e.road_owner), 8, 0.24);
    }
  }
  const showRoads = (mode==='road' || state.phase==='setup') && isMyTurn();
  if (showRoads) {
    for (const ei of (state.valid.roads||[])) {
      const e = b.edges[ei];
      const p0 = toCanvas({x:e.points[0][0], y:e.points[0][1]});
      const p1 = toCanvas({x:e.points[1][0], y:e.points[1][1]});
      // yellow preview bars, same shape as a placed road but slightly thinner
      drawRoadBar(p0, p1, 'rgba(255,255,0,0.85)', 6, 0.24);
    }
  }
  for (const v of b.vertices) {
    const p = toCanvas({x:v.x, y:v.y});
    if (v.building) {
      if (v.building === 'city') drawCity(p.x, p.y, playerColor(v.owner));
      else drawSettlement(p.x, p.y, playerColor(v.owner));
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
  drawDice();         // the current roll, always visible bottom-right
}

// Two thin lines from the ends of the port edge out to sea. No line along the
// coast itself: that is what keeps a port visually separate from a road.
function drawPorts(b) {
  ctx.save();
  ctx.strokeStyle = 'rgba(150,120,105,0.9)';
  ctx.lineWidth = Math.max(2.5, scale * 0.055);
  ctx.lineCap = 'round';
  for (const pe of (b.port_edges || [])) {
    const g = _portGeom(pe);
    // Two pier lines that leave the two ends of the coast edge perpendicular to
    // the shore, then bend inwards and meet at the port token (they end at its
    // centre, and the token is painted on top). The old straight pair read as a
    // ladder lying in the sea; the curve makes the pier point at the harbour.
    const d = Math.hypot(g.tip.x - g.mid.x, g.tip.y - g.mid.y);
    const c1 = d * 0.45;             // leave the shore square-on
    const c2 = d - c1;               // arrive along the port's axis
    for (const p of [g.p1, g.p2]) {
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.bezierCurveTo(
        p.x + g.nx * c1, p.y + g.ny * c1,
        g.mid.x + g.nx * c2, g.mid.y + g.ny * c2,
        g.tip.x, g.tip.y);
      ctx.stroke();
    }
  }
  ctx.restore();
}

// The printed port disc: white token + symbol, ratio written underneath
// (like the board game's harbour tokens).
function drawPortToken(type, x, y, r) {
  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = '#f7f3e6';
  ctx.fill();
  ctx.strokeStyle = '#5d4037';
  ctx.lineWidth = Math.max(1.5, r * 0.1);
  ctx.stroke();
  ctx.restore();
  if (type === 'generic') drawShipIcon(x, y, r * 0.62, true);
  else drawResourceIcon(type, x, y, r * 0.58, true);
}

function drawPortRatio(type, x, top, fs) {
  const txt = type === 'generic' ? '3:1' : '2:1';
  ctx.save();
  ctx.font = `bold ${fs}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.lineJoin = 'round';
  ctx.lineWidth = Math.max(2.5, fs * 0.34);
  ctx.strokeStyle = 'rgba(0,0,0,0.75)';
  ctx.strokeText(txt, x, top);
  ctx.fillStyle = '#fff';
  ctx.fillText(txt, x, top);
  ctx.restore();
}

// Drawn last (on top of roads/buildings) so a port token is never hidden.
function drawPortLabels(b) {
  for (const pe of (b.port_edges || [])) {
    const g = _portGeom(pe);
    drawPortToken(pe.type, g.tip.x, g.tip.y, g.r);
    drawPortRatio(pe.type, g.tip.x, g.textTop, g.fs);
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
  const cur = playerAt(state.current);
  const curName = cur ? (cur.name || '—') : '—';
  const curId = cur ? cur.id : '?';
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
  if (hasPendingDiscards()) {
    const waiting = Object.keys(state.pending_discards).map(k => playerName(Number(k))).join('、');
    const iMust = VIEW === 'client' && state.pending_discards[String(state.you)] !== undefined;
    extra = iMust
      ? '<br><b style="color:#ff8">7: あなたはカードを捨ててください</b>'
      : `<br><b style="color:#ff8">7: 捨て札待ち（${waiting}）。終わると盗賊を動かせます</b>`;
  }
  else if (state.robber_pending) extra = '<br><b style="color:#ff8">7: 盗賊を移動（ヘックスをクリック）</b>';
  if (state.rerolled) extra += '<br><span style="color:#8cf">7は振り直し（第1巡目）</span>';
  let mine = '';
  if (VIEW === 'client') {
    mine = playerAt(state.you)
      ? `<br><span style="color:#8cf">あなた: <b>${playerName(state.you)}</b> (P${state.you})</span>`
      : `<br><span style="color:#f88">このゲームに参加していません（観戦モード）</span>`;
  }
  status.innerHTML = `フェーズ: <b>${phaseJa[state.phase]||state.phase}</b> | ターン ${state.turn_number||0}<br>手番: <b>${curName}</b> (P${curId})${hint}${extra}${mine}<br>勝者: ${state.winner!==null && state.winner!==undefined?playerName(state.winner):'-'}`;

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
  const rd = document.getElementById('resources');   // monitor only
  if (rd) {
    rd.innerHTML = '';
    if (me && me.resources) {
      for (const k of RES) {
        const row = document.createElement('div'); row.className='resource';
        row.innerHTML = `<span>${resName(k)}</span><span>${me.resources[k]||0}</span>`;
        rd.appendChild(row);
      }
    }
  }
  renderHand(me);
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
  // a victory point card is never "played" - it is only a score
  const usable = (me && me.dev_cards) ? me.dev_cards.filter(c => c !== 'victory_point') : [];
  if (usable.length) {
    const ph = document.createElement('option');
    ph.value = ''; ph.textContent = '-- 選んでください --';
    devSel.appendChild(ph);
    for (const c of usable) {
      const opt = document.createElement('option');
      opt.value = c; opt.textContent = devName(c);
      devSel.appendChild(opt);
    }
  }
  // Keep the player's own choice while that card is still in hand (polls
  // rebuild this list); otherwise fall back to the placeholder.
  devSel.value = (prevVal && usable.includes(prevVal)) ? prevVal : '';
  updateDevParams();
  devSel.onchange = () => { updateDevParams(); updateActionAvailability(); };
  document.getElementById('devcards').textContent =
    (me && me.dev_cards ? me.dev_cards.map(devName).join(', ') : '') +
    (me && me.new_dev_cards && me.new_dev_cards.length ? ' (新規: '+me.new_dev_cards.map(devName).join(',')+')' : '');

  updateTradeUI(me);
  updatePlayerTradeUI(me);
  updateActionAvailability();
}

// The player's own hand as one row of five coloured chips ("木 3"). Colours are
// the board's terrain colours, but the kanji + count carry the meaning too, so
// the row never relies on colour alone. Shown only to a seated player: the
// monitor and spectators have no hand of their own.
const HAND_TERRAIN = {wood:'forest', brick:'hills', sheep:'pasture', wheat:'fields', ore:'mountains'};
const HAND_TEXT = {wood:'#fff', brick:'#1b1208', sheep:'#14230a', wheat:'#2a2300', ore:'#161616'};

function renderHand(me) {
  const el = document.getElementById('hand');
  if (!el) return;
  const seated = VIEW === 'client' && state && state.you !== null && state.you !== undefined
    && me && me.resources;
  if (!seated) { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.style.display = 'flex';
  el.innerHTML = RES.map(k => {
    const n = me.resources[k] || 0;
    return `<span class="hand-chip${n ? '' : ' zero'}" style="background:${TERRAIN_COLOR[HAND_TERRAIN[k]]};color:${HAND_TEXT[k]};">${resName(k)} ${n}</span>`;
  }).join('');
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
    note.innerHTML = `※ ${escHtml(playerName(offer.from))} さんが取引を提案中です（終わるまで新しい提案はできません）`;
    builder.style.display = 'block';
    buildPtBuilder(me);
    return;
  }
  note.style.display = 'none';
  if (offer) {
    active.style.display = 'block';
    builder.style.display = 'none';
    const fromP = playerAt(offer.from);
    let html = `<div style="font-size:12px;"><b>${fromP ? escHtml(fromP.name) : '—'}</b> の提案: <b>${resStr(offer.give)}</b> を渡す／<b>${resStr(offer.want)}</b> がほしい</div>`;
    const amTarget = myId !== null && offer.targets.includes(myId) && !(offer.declined||[]).includes(myId);
    if (VIEW === 'monitor') {
      // let the monitor act on behalf of any responder / proposer
      const responders = offer.targets.filter(t => !(offer.declined || []).includes(t));
      if (responders.length === 0) {
        html += `<div style="font-size:12px;color:#f88;margin-top:4px;">応答できる相手がいません。</div>`;
      } else {
        for (const t of responders) {
          html += `<div style="margin-top:4px;font-size:12px;">${playerName(t)}
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
function devCardChosen() {
  const sel = document.getElementById('dev-select');
  return !!(sel && sel.value);
}

// After a card is used the list is shown again from the placeholder.
function resetDevSelect() {
  const sel = document.getElementById('dev-select');
  if (!sel) return;
  sel.value = '';
  updateDevParams();
  updateActionAvailability();
}

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
  for (const id of ['btn-roll','btn-end','btn-buydev','btn-trade','btn-pt-propose']) {
    const el = document.getElementById(id);
    if (el) el.disabled = !!blocked;
  }
  const pd = document.getElementById('btn-playdev');
  if (pd) pd.disabled = !!blocked || !devCardChosen();
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

function setBar(open, manual) {
  document.body.classList.toggle('bar-open', !!open);
  const b = document.getElementById('btn-togglebar');
  if (b) b.textContent = open ? '▼ 盤面を広く見る' : '▲ 操作パネルを開く';
  if (manual) {
    // The player tapped the toggle: a manual close sticks for the situation
    // that is currently on screen, so the next poll does not pop it back open.
    if (!open && barAutoReason) barSuppressed = barAutoReason;
    if (open) barSuppressed = null;
  }
  if (isPhone()) {
    // make sure the board is laid out against the new pane height
    requestAnimationFrame(() => { resize(); updateMobileToggle(); });
    setTimeout(() => { resize(); updateMobileToggle(); }, 80);
  }
}

// Open the action sheet when the player has to act (discard / robber / setup).
// While the player is actively placing something the sheet stays open, so the
// turn does not flap between "open" and "closed" on every poll.
//
// If the player closes the sheet BY HAND we must not immediately re-open it on
// the next poll (that made the "盤面を広く見る" button feel broken). We remember
// the reason we auto-opened for; a manual close suppresses that SAME reason
// until a new one appears (e.g. the next discard / robber / setup step).
let barHeld = false;
let barAutoReason = null;     // signature of the must-act situation that opened it
let barSuppressed = null;     // signature the player dismissed by hand

function _barReason() {
  if (!state) return null;
  if (state.phase === 'setup' && isMyTurn()) return 'setup';
  if (hasPendingDiscards()) return 'discard:' + state.turn_number;
  // Choosing the victim is a separate step from tapping the hex: the sheet may
  // have been closed by hand to reach the board, and the victim panel lives in
  // it, so this step must open it again (also for a Knight, where
  // robber_pending is not set yet).
  if (pendingRobberHex !== null && isMyTurn()) return 'robber-victim:' + state.turn_number;
  if (state.robber_pending && isMyTurn()) return 'robber:' + state.turn_number;
  return null;
}

function autoOpenBar() {
  if (!isPhone()) return;
  const reason = _barReason();
  if (reason) {
    barHeld = true;
    barAutoReason = reason;
    // respect a manual close for this same situation
    if (reason !== barSuppressed && !barOpened()) setBar(true);
    return;
  }
  const stillActing = isMyTurn() && (mode === 'road' || mode === 'settle' || mode === 'city' || mode === 'robber');
  if (barHeld && stillActing) return;      // keep it open during the placement
  barHeld = false;
  barAutoReason = null;
  barSuppressed = null;                    // new turn/situation: clear the memory
}

// Tell the closed bar what is going on, so the player knows why it opened.
function updateMobileToggle() {
  const obs = document.getElementById('m-observe');
  if (obs) obs.textContent = '監視モード（閲覧のみ）。操作はプレイヤー画面から行います。';
  const el = document.getElementById('m-bar-status');
  const bar = document.getElementById('m-bar');
  if (!el || !bar || !state || !state.players) return;
  const cur = playerAt(state.current);
  const parts = [];
  if (READONLY) {
    parts.push('閲覧のみ');
    if (cur) parts.push(`手番: ${cur.name}`);
    el.textContent = parts.join('　');
    return;
  }
  parts.push(`ターン${state.turn_number || 0}`);
  parts.push(isMyTurn() ? 'あなたの手番' : `手番: ${cur ? (cur.name || '—') : '—'}`);
  if (state.phase === 'setup') parts.push(isMyTurn() ? (state.setup_settlement_required ? '開拓地を配置' : '街道を配置') : '');
  else if (state.phase === 'roll') parts.push(isMyTurn() ? 'サイコロを振る' : '');
  if (hasPendingDiscards()) parts.push('カードを捨てる');
  else if (state.robber_pending) parts.push('盗賊を移動');
  el.textContent = parts.filter(Boolean).join('　');
}

// Should the action sheet open on its own? (discard / robber / setup placement)
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
    const p = playerAt(discardPid);
    dp.style.display = 'block';
    document.getElementById('discard-info').innerHTML =
      `<b>${p ? escHtml(p.name) : '—'}</b> は <b>${need}</b> 枚捨てる必要があります。捨てるカードを選んでください。`;
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
    if (rp.style.display !== 'block') {
      const sb = document.getElementById('sidebar');
      if (sb) sb.scrollTop = 0;     // the victim panel is the first thing in the sheet
    }
    rp.style.display = 'block';
    const key = pendingRobberHex[0] + ',' + pendingRobberHex[1];
    const victims = (state.robber_victims && state.robber_victims[key]) || [];
    document.getElementById('robber-info').textContent = `盗賊: (${key})。奪う相手を選んでください。`;
    const sel = document.getElementById('robber-victim');
    sel.innerHTML = '';
    for (const vid of victims) {
      const vp = playerAt(vid);
      if (!vp) continue;
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
  const wasKnight = pendingKnight;
  if (pendingKnight) r = await post('play_dev', {card:'knight', hex, victim});
  else r = await post('move_robber', {hex, victim});
  if (wasKnight && r && r.ok) resetDevSelect();
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
    <!-- must-answer panels first: on a phone the sheet is short, and these used to sit below the status and buttons, out of sight -->
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
    <div id="exit-panel" style="display:none;margin:4px 0;">
      <button class="btn" id="btn-exit">退出する</button>
      <button class="btn" id="btn-backlobby" style="display:none;">ロビーに戻る</button>
      <div id="exit-note" style="display:none;font-size:11px;color:#aaa;margin-top:2px;">誰かが押すと、全員ロビーに戻ります</div>
    </div>
    <div id="status">読み込み中...</div>
    <div id="hand" class="hand-row" style="display:none;"></div>
    <div>
      <button class="btn" id="btn-roll">サイコロを振る</button>
      <button class="btn" id="btn-end">ターン終了</button>
      ${monitorBtns}
    </div>
    <div class="m-only" style="margin:2px 0 6px;">
      <button id="toggle-all">▽ 交易・発展カードなども表示</button>
    </div>
    <div class="m-fold" id="fold-dev">
      <select id="dev-select" style="width:100%;margin:4px 0;padding:4px;"></select>
      <div id="dev-params" style="display:none;margin:4px 0;"></div>
      <button class="btn" id="btn-playdev">選んだカードを使う</button>
    </div>
    <div class="m-fold" id="fold-build">
      <button class="btn" id="mode-road">街道を建てる</button>
      <button class="btn" id="mode-settle">開拓地を建てる</button>
      <button class="btn" id="mode-city">都市を建てる</button>
      <button class="btn" id="btn-buydev">発展カードを購入</button>
      <button class="btn" id="mode-none">キャンセル</button>

    </div>
    <h2>プレイヤー</h2>
    <div id="players"></div>
    ${VIEW === 'monitor' ? '<h2>資源（現在の手番）</h2><div id="resources"></div>' : ''}
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
    <h2>ログ</h2>
    <div id="event-log"></div>
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
  document.getElementById('btn-exit').onclick = async () => { await sendExit('exit_request'); };
  const backBtn = document.getElementById('btn-backlobby');
  backBtn.onclick = async () => {
    // One press takes everybody back, so ask first (a stray tap would end the
    // others' look at the result).
    if (!confirm('全員がロビーに戻ります。よろしいですか？')) return;
    backBtn.disabled = true;
    let r = null;
    try {
      // Not post(): it refreshes the state afterwards, and the page reload that
      // can trigger would race with forgetting the token below.
      r = await fetch('/action', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({action:'leave', token: TOKEN})}).then(x => x.json());
    } catch (e) { r = null; }
    // "not joined": somebody else pressed a moment earlier and the room is
    // already reset, so this seat is gone as well - same result as success.
    if (!r || !(r.ok || r.error === 'not joined')) {
      backBtn.disabled = false;
      showToast((r && r.error) || '退出できませんでした', 'info');
      return;
    }
    forgetSeatLocally();
    location.reload();
  };
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
    else resetDevSelect();
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
  const mrobBtn = document.getElementById('mode-robber');
  if (mrobBtn) mrobBtn.onclick = () => { pendingKnight=false; setMode('robber'); };
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
    tb.onclick = () => setBar(!barOpened(), true);
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
  setInterval(renderExitBanner, 1000);     // the countdown in the exit banner
}

// Show a message parked by flashAfterReload() (also on the lobby page, which
// loads this script but may never boot the game).
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showFlash);
else showFlash();

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
  terrainTexture, seaTexture, diceTexture,
  // test hooks: draw a single piece / road so the shapes can be inspected
  _debugDrawPiece: (kind, px, py, color) => {
    if (kind === 'city') drawCity(px, py, color); else drawSettlement(px, py, color);
  },
  _debugDrawRoad: (p0, p1, color) => drawRoadBar(p0, p1, color, 8, 0.24),
  _debugDrawRobber: (px, py) => drawRobber(px, py),
  // test hooks: a single die face and the whole 2d6 group
  _debugDrawDie: (px, py, side, value) => drawDie(px, py, side, value),
  _debugDrawDice: () => drawDice(),
  // test hooks: one port mark (ship for "generic", else a resource)
  _debugDrawPortIcon: (type, px, py, r) => {
    const fs = Math.max(10, Math.round(scale * 0.22));
    drawPortToken(type, px, py, r);
    drawPortRatio(type, px, py + r + Math.max(2, scale * 0.05), fs);
  },
  // test hooks: geometry used to keep the dice clear of the ports
  _debugPortMarkBoxes: () => _portMarkBoxes(state.board || {}),
  _debugDicePlacement: () => dicePlacement(),
  // test hooks: the mobile action sheet
  _debugBarOpened: () => barOpened(),
  _debugSetBar: (open, manual) => setBar(open, manual),
  _debugAutoOpenBar: () => autoOpenBar(),
  _debugBarState: () => ({ opened: barOpened(), reason: barAutoReason, suppressed: barSuppressed, held: barHeld }),
};
})();
