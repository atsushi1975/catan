// app.js
const canvas = document.getElementById('board');
const ctx = canvas.getContext('2d');

let state = null;
let mode = 'none'; // none | road | settle | city
let scale = 50;

function resize() {
  canvas.width = canvas.clientWidth || 800;
  canvas.height = canvas.clientHeight || 600;
  // fit board (width ~7, height ~6 world units) into canvas
  scale = Math.min(canvas.width/7, canvas.height/6);
  render();
}
window.addEventListener('resize', resize);

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}
async function getState() { state = await api('/state'); if (state && state.phase === 'setup' && (mode === 'none' || mode === 'robber')) mode = 'settle'; render(); updateSidebar(); }
async function post(action, extra={}) {
  const r = await api('/action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action, ...extra})});
  await getState();
  // Auto-guide during setup: after placing settlement, switch to road mode; after road, back to settle
  if (state && state.phase === 'setup') {
    if (action === 'build_settlement' && r.ok) { mode = 'road'; }
    else if (action === 'build_road' && r.ok) { mode = 'settle'; }
    else if (mode === 'none') { mode = 'settle'; }
  } else if (state && state.phase !== 'setup' && mode !== 'none' && mode !== 'robber') {
    // keep user mode in main phase
  }
  updateModeButtons();
  render();
  return r;
}

// axial -> pixel
function hexCenter(q, r) {
  const x = scale * (Math.sqrt(3)*q + Math.sqrt(3)/2*r);
  const y = scale * (3/2*r);
  return {x, y};
}
function hexCorners(cx, cy) {
  const pts = [];
  for (let i=0;i<6;i++){ const a=Math.PI/180*(30+60*i); pts.push({x:cx+scale*Math.cos(a), y:cy+scale*Math.sin(a)}); }
  return pts;
}

const TERRAIN_COLOR = {
  forest:'#2d8a4e', hills:'#c4956a', pasture:'#8bc34a',
  fields:'#f9d71c', mountains:'#9e9e9e', desert:'#e8c98a'
};
const TERRAIN_LABEL = {
  forest:'Wood', hills:'Brick', pasture:'Sheep', fields:'Wheat',
  mountains:'Ore', desert:'Desert'
};

function toCanvas(p) { // world -> canvas coords (centered)
  if (!state) return p;
  const cx = canvas.width/2, cy = canvas.height/2;
  return {x: cx + p.x * scale, y: cy + p.y * scale};
}

function render() {
  if (!state) return;
  ctx.fillStyle = '#2a2a2a';
  ctx.fillRect(0,0,canvas.width,canvas.height);
  const b = state.board;
  // hexes
  for (const h of b.hexes) {
    const c = hexCenter(h.q, h.r);
    const cc = toCanvas(c);
    const corners = hexCorners(cc.x, cc.y);
    ctx.beginPath();
    ctx.moveTo(corners[0].x, corners[0].y);
    for (let i=1;i<6;i++) ctx.lineTo(corners[i].x, corners[i].y);
    ctx.closePath();
    ctx.fillStyle = TERRAIN_COLOR[h.terrain] || '#555';
    ctx.fill();
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 2;
    ctx.stroke();
    // number token (white circle like real Catan)
    if (h.number) {
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      ctx.arc(cc.x, cc.y - 2, 13, 0, Math.PI*2);
      ctx.fill();
      ctx.strokeStyle = (h.number===6||h.number===8) ? '#c00' : '#333';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cc.x, cc.y - 2, 13, 0, Math.PI*2);
      ctx.stroke();
      ctx.fillStyle = (h.number===6||h.number===8) ? '#c00' : '#000';
      ctx.font = 'bold 16px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(h.number, cc.x, cc.y - 2);
    }
    // resource label with background pill (larger, more visible)
    const lbl = TERRAIN_LABEL[h.terrain] || '';
    ctx.font = 'bold 13px sans-serif';
    const tw = ctx.measureText(lbl).width + 12;
    ctx.fillStyle = 'rgba(0,0,0,0.8)';
    ctx.fillRect(cc.x - tw/2, cc.y + 12, tw, 18);
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1;
    ctx.strokeRect(cc.x - tw/2, cc.y + 12, tw, 18);
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(lbl, cc.x, cc.y + 21);
    if (h.robber) {
      ctx.fillStyle='rgba(0,0,0,0.6)';
      ctx.beginPath(); ctx.arc(cc.x, cc.y+14, 8,0,Math.PI*2); ctx.fill();
    }
  }
  // edges (roads)
  for (const e of b.edges) {
    const p0 = toCanvas({x:e.points[0][0], y:e.points[0][1]});
    const p1 = toCanvas({x:e.points[1][0], y:e.points[1][1]});
    ctx.strokeStyle = e.road_owner===null ? 'rgba(255,255,255,0.15)' : playerColor(e.road_owner);
    ctx.lineWidth = e.road_owner===null ? 2 : 5;
    ctx.beginPath(); ctx.moveTo(p0.x,p0.y); ctx.lineTo(p1.x,p1.y); ctx.stroke();
  }
  // highlight valid roads
  const showRoads = mode==='road' || state.phase==='setup';
  if (showRoads) {
    for (const ei of state.valid.roads) {
      const e = b.edges[ei];
      const p0 = toCanvas({x:e.points[0][0], y:e.points[0][1]});
      const p1 = toCanvas({x:e.points[1][0], y:e.points[1][1]});
      ctx.strokeStyle = '#ff0'; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(p0.x,p0.y); ctx.lineTo(p1.x,p1.y); ctx.stroke();
    }
  }
  // vertices (settlements/cities)
  for (const v of b.vertices) {
    const p = toCanvas({x:v.x, y:v.y});
    if (v.building) {
      ctx.fillStyle = playerColor(v.owner);
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 2;
      if (v.building === 'city') {
        ctx.fillRect(p.x-10, p.y-10, 20, 20);
        ctx.strokeRect(p.x-10, p.y-10, 20, 20);
      } else {
        ctx.beginPath(); ctx.arc(p.x, p.y, 10, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(p.x, p.y, 10, 0, Math.PI*2); ctx.stroke();
      }
    } else if ((mode==='settle' || state.phase==='setup') && state.valid.settlements.includes(v.i)) {
      ctx.fillStyle='rgba(255,255,0,0.5)';
      ctx.beginPath(); ctx.arc(p.x, p.y, 9, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle='#ff0'; ctx.lineWidth=2;
      ctx.beginPath(); ctx.arc(p.x, p.y, 9, 0, Math.PI*2); ctx.stroke();
    } else if (mode==='city' && state.valid.cities.includes(v.i)) {
      ctx.strokeStyle='#ff0'; ctx.lineWidth=2;
      ctx.strokeRect(p.x-8, p.y-8, 16, 16);
    }
  }
  // ports (drawn as small labels on coast vertices)
  for (const [viStr, pt] of Object.entries(b.ports || {})) {
    const vi = parseInt(viStr);
    const v = b.vertices[vi];
    if (!v) continue;
    const p = toCanvas({x:v.x, y:v.y});
    const label = (typeof pt === 'string') ? pt : (pt === 'generic' ? '3:1' : (pt + ':2:1?'));
    // simpler label
    let txt;
    if (pt === 'generic') txt = '3:1';
    else txt = '2:1 ' + pt;
    ctx.fillStyle = 'rgba(255,255,255,0.95)';
    ctx.font = 'bold 9px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    // draw background
    const tw = ctx.measureText(txt).width + 4;
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(p.x - tw/2, p.y - 26, tw, 12);
    ctx.fillStyle = '#fff';
    ctx.fillText(txt, p.x, p.y - 20);
  }
}

function playerColor(id) {
  const colors = ['#e53935','#1e88e5','#f5f5f5','#fb8c00'];
  return colors[id] || '#888';
}

function updateSidebar() {
  if (!state) return;
  const status = document.getElementById('status');
  const cur = state.players[state.current];
  let hint = '';
  if (state.phase === 'setup') hint = ` → ${cur.name}: place a SETTLEMENT`;
  else if (state.phase === 'roll') hint = ` → ${cur.name}: roll dice`;
  else if (state.phase === 'main') hint = ` → ${cur.name}: build/trade`;
  status.innerHTML = `Phase: <b>${state.phase}</b> | Turn ${state.turn_number||0}<br>Current: <b>${cur.name}</b> (P${cur.id})${hint}<br>Dice: ${state.dice.join('+')||'-'} | Winner: ${state.winner!==null?state.winner:'-'}`;
  // players
  const pd = document.getElementById('players');
  pd.innerHTML = '';
  for (const p of state.players) {
    const div = document.createElement('div');
    div.className = 'player' + (p.id===state.current?' current':'');
    div.innerHTML = `<b>${p.name}</b> (P${p.id}) VP:${p.total_vp} R:${p.roads_left} S:${p.settlements_left} C:${p.cities_left}${p.longest_road?' [LR]':''}${p.largest_army?' [LA]':''}`;
    pd.appendChild(div);
  }
  // resources for current player
  const rd = document.getElementById('resources');
  rd.innerHTML = '';
  for (const [k,v] of Object.entries(cur.resources)) {
    const row = document.createElement('div'); row.className='resource';
    row.innerHTML = `<span>${k}</span><span>${v}</span>`;
    rd.appendChild(row);
  }
  // dev cards
  const devSel = document.getElementById('dev-select');
  const prevVal = devSel.value;
  devSel.innerHTML = '';
  for (const c of (cur.dev_cards||[])) {
    const opt = document.createElement('option');
    opt.value = c; opt.textContent = c;
    devSel.appendChild(opt);
  }
  if (prevVal && [...devSel.options].some(o=>o.value===prevVal)) devSel.value = prevVal;
  document.getElementById('devcards').textContent = (cur.dev_cards||[]).join(', ') + (cur.new_dev_cards.length? ' (new: '+cur.new_dev_cards.join(',')+')':'');
}

// click handling
canvas.addEventListener('click', async (ev) => {
  if (!state) return;

  const rect = canvas.getBoundingClientRect();
  const cx = ev.clientX - rect.left, cy = ev.clientY - rect.top;
  // convert to world coords
  const wx = (cx - canvas.width/2) / scale, wy = (cy - canvas.height/2) / scale;
  if (mode === 'robber') {
    // find nearest hex
    let best = null, bestd = 1e9;
    for (const h of state.board.hexes) {
      const c = hexCenter(h.q, h.r);
      const d = Math.hypot(wx - c.x, wy - c.y);
      if (d < bestd) { bestd = d; best = h; }
    }
    if (best && bestd < scale) {
      // find victim
      // victims are players with buildings on that hex (excluding current)
      const victims = [];
      // we'll let server validate; pass victim from a prompt
      let victim = null;
      // try to find adjacent owners
      // simpler: prompt
      const v = prompt('Victim player id (or empty for none):');
      if (v !== null && v !== '') victim = parseInt(v);
      post('move_robber', {hex: [best.q, best.r], victim: victim});
      setMode('none');
    }
    return;
  }
  if (mode === 'road') {
    // find nearest among VALID roads only
    let best = null, bestd = 1e9;
    for (const ei of state.valid.roads) {
      const e = state.board.edges[ei];
      const p0 = {x:e.points[0][0], y:e.points[0][1]};
      const p1 = {x:e.points[1][0], y:e.points[1][1]};
      const d = pointToSegDist(wx,wy,p0,p1);
      if (d < bestd) { bestd = d; best = ei; }
    }
    if (best !== null && bestd < 12) {
      const r = await post('build_road', {edge: best});
      if (!r.ok) console.error('road fail', r);
      if (!(state && state.phase === 'setup')) { mode = 'none'; }
      updateModeButtons();
    }
  } else if (mode === 'settle') {
    let best = null, bestd = 1e9;
    for (const vi of state.valid.settlements) {
      const v = state.board.vertices[vi];
      const d = Math.hypot(wx - v.x, wy - v.y);
      if (d < bestd) { bestd = d; best = vi; }
    }
    if (best !== null && bestd < 14) {
      const r = await post('build_settlement', {vertex: best});
      if (!r.ok) console.log('settle fail', r);
      if (!(state && state.phase === 'setup')) { mode = 'none'; }
      updateModeButtons();
    }
  } else if (mode === 'city') {
    let best = null, bestd = 1e9;
    for (const v of state.board.vertices) {
      const d = Math.hypot(wx - v.x, wy - v.y);
      if (d < bestd) { bestd = d; best = v.i; }
    }
    if (best !== null && bestd < 14 && state.valid.cities.includes(best)) {
      const r = await post('build_city', {vertex: best});
      if (!r.ok) console.log('city fail', r);
      mode = 'none'; updateModeButtons();
    }
  }
});

function pointToSegDist(px,py,a,b) {
  const dx=b.x-a.x, dy=b.y-a.y;
  const t = Math.max(0, Math.min(1, ((px-a.x)*dx+(py-a.y)*dy)/(dx*dx+dy*dy||1)));
  const cx = a.x + t*dx, cy = a.y + t*dy;
  return Math.hypot(px-cx, py-cy);
}

// buttons
document.getElementById('btn-roll').onclick = async () => { await post('roll'); };
document.getElementById('btn-end').onclick = async () => { await post('end_turn'); };
document.getElementById('btn-new').onclick = async () => { await fetch('/new'); await getState(); };
document.getElementById('btn-auto').onclick = async () => { await post('auto_setup'); };
document.getElementById('btn-buydev').onclick = async () => { await post('buy_dev'); };
document.getElementById('btn-playdev').onclick = async () => {
  const sel = document.getElementById('dev-select');
  const card = sel.value;
  if (!card) return;
  let params = {card};
  if (card === 'knight') {
    const h = prompt('Robber hex q,r (e.g. 0,0):');
    if (!h) return;
    const parts = h.split(',').map(s=>parseInt(s.trim()));
    params.hex = parts;
    const v = prompt('Victim player id (or empty):');
    if (v) params.victim = parseInt(v);
  } else if (card === 'year_of_plenty') {
    const r1 = prompt('Resource 1 (wood/brick/sheep/wheat/ore):');
    const r2 = prompt('Resource 2:');
    params.r1 = r1; params.r2 = r2;
  } else if (card === 'monopoly') {
    const r = prompt('Resource to monopolize (wood/brick/sheep/wheat/ore):');
    params.resource = r;
  } else if (card === 'road_building') {
    // free roads: user builds via road mode
  }
  await post('play_dev', params);
};
function setMode(m){ mode=m; updateModeButtons(); render(); }
document.getElementById('mode-road').onclick = () => setMode('road');
document.getElementById('mode-settle').onclick = () => setMode('settle');
document.getElementById('mode-city').onclick = () => setMode('city');
document.getElementById('mode-none').onclick = () => setMode('none');
document.getElementById('mode-robber').onclick = () => setMode('robber');
function updateModeButtons() {
  for (const id of ['mode-road','mode-settle','mode-city','mode-none']) {
    document.getElementById(id).classList.toggle('active', id==='mode-'+mode);
  }
}

resize();
getState();
setInterval(getState, 2000);
