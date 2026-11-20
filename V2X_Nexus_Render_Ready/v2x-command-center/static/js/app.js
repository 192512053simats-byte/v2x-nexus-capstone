/* V2X Nexus — offline-friendly research dashboard, no frontend dependencies. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = { experiment: null, scheduler: 'ai', frame: 0, playing: false, timer: null, speed: 1 };
  const colors = { cyan: '#35d6f5', purple: '#9679ff', green: '#35df9b', amber: '#ffbd6f', red: '#ff6b87', bg: '#0b1527' };
  const metrics = [
    ['Average message latency', 'latency_ms', 'ms', 'low'],
    ['Safety message latency', 'safety_latency_ms', 'ms', 'low'],
    ['Packet delivery ratio', 'pdr_pct', '%', 'high'],
    ['Safety packet delivery', 'safety_pdr_pct', '%', 'high'],
    ['Cooperative hazard awareness', 'awareness_pct', '%', 'high'],
    ['Blind-spot reduction', 'blindspot_reduction_pct', '%', 'high'],
    ['Timely hazard detection', 'timely_hazards_pct', '%', 'high'],
    ['Channel data transmitted', 'traffic_kb', 'KB', 'low'],
  ];
  function toast(message, error = false) {
    const el = $('toast'); el.textContent = message; el.classList.toggle('error', error); el.classList.add('visible');
    clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove('visible'), 4200);
  }
  function scrollToSection(section) {
    const dest = $(section); if (dest) dest.scrollIntoView({ behavior: 'smooth', block: 'start' });
    document.querySelectorAll('[data-nav]').forEach(n => n.classList.toggle('active', n.dataset.nav === section));
    $('sidebar').classList.remove('open');
  }
  function bindControls() {
    document.querySelectorAll('[data-nav]').forEach(el => el.addEventListener('click', () => scrollToSection(el.dataset.nav)));
    document.querySelectorAll('[data-jump]').forEach(el => el.addEventListener('click', () => scrollToSection(el.dataset.jump)));
    $('mobileMenu').addEventListener('click', () => $('sidebar').classList.toggle('open'));
    [['vehicles','vehicleNumber',v => v], ['load','loadNumber',v => `${v}%`], ['capacity','capacityNumber',v => `${v} packets/tick`]].forEach(([id, display, format]) => {
      $(id).addEventListener('input', () => $(display).textContent = format($(id).value));
    });
    $('source').addEventListener('change', () => {
      $('sourceHint').textContent = $('source').value === 'trace'
        ? 'Requires data/sumo_trace.json (see README and SUMO exporter).'
        : 'Ready to run; no SUMO installation needed.';
    });
    document.querySelectorAll('[data-scheduler]').forEach(el => el.addEventListener('click', () => {
      state.scheduler = el.dataset.scheduler;
      document.querySelectorAll('[data-scheduler]').forEach(b => b.classList.toggle('active', b.dataset.scheduler === state.scheduler));
      if (state.experiment) { renderAll(); }
    }));
    ['runTop', 'heroRun', 'runPrimary'].forEach(id => $(id).addEventListener('click', runExperiment));
    $('playPause').addEventListener('click', () => { if (state.playing) pause(); else play(); });
    $('stepBack').addEventListener('click', () => { pause(); setFrame(state.frame - 1); });
    $('stepForward').addEventListener('click', () => { pause(); setFrame(state.frame + 1); });
    $('timeline').addEventListener('input', () => { pause(); setFrame(Number($('timeline').value)); });
    $('playSpeed').addEventListener('change', () => { state.speed = Number($('playSpeed').value); if (state.playing) { pause(); play(); } });
    $('exportJsonTop').addEventListener('click', exportJSON);
    $('exportCsv').addEventListener('click', exportCSV);
    window.addEventListener('resize', () => drawLatencyChart());
  }
  function getConfig() {
    return { scenario: $('scenario').value, source: $('source').value,
      vehicles: Number($('vehicles').value), load: Number($('load').value) / 100,
      capacity: Number($('capacity').value), duration: Number($('duration').value),
      seed: Number($('seed').value) };
  }
  async function runExperiment() {
    pause();
    const buttons = ['runTop', 'heroRun', 'runPrimary'].map($);
    buttons.forEach(b => b.disabled = true);
    $('simBadge').textContent = 'COMPUTING EXPERIMENT';
    try {
      const response = await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(getConfig()) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Experiment failed');
      state.experiment = data; state.frame = 0;
      $('timeline').max = String(Math.max(0, data.config.duration - 1));
      $('mapMode').textContent = data.config.scenario.toUpperCase();
      $('simBadge').textContent = 'SIMULATION LOADED';
      $('statVehicles').textContent = String(data.config.vehicles);
      renderAll(); scrollToSection('simulation'); play();
      toast(`${data.hazard_count} hazard events · paired comparison ready`);
    } catch (err) {
      $('simBadge').textContent = 'SIMULATION READY'; toast(err.message || 'Could not run experiment', true);
    } finally { buttons.forEach(b => b.disabled = false); }
  }
  function currentResult() { return state.experiment?.results?.[state.scheduler] || null; }
  function metricNum(n, digits = 1) { return Number.isFinite(n) ? Number(n).toFixed(digits) : '—'; }
  function setDelta(id, aiValue, fifoValue, mode) {
    const el = $(id), diff = aiValue - fifoValue;
    const good = mode === 'low' ? diff < -0.005 : diff > 0.005;
    const bad = mode === 'low' ? diff > 0.005 : diff < -0.005;
    el.classList.remove('neutral', 'good', 'bad');
    el.classList.add(good ? 'good' : bad ? 'bad' : 'neutral');
    el.textContent = `${diff > 0 ? '+' : ''}${diff.toFixed(1)}${id === 'latencyDiff' ? ' ms' : ' pp'}`;
  }
  function renderKPIs() {
    const { fifo, ai } = state.experiment.results; const a = ai.metrics, f = fifo.metrics;
    $('kpiLatency').textContent = metricNum(a.latency_ms);
    $('kpiAwareness').textContent = metricNum(a.awareness_pct);
    $('kpiPdr').textContent = metricNum(a.safety_pdr_pct);
    $('kpiBytes').textContent = metricNum(a.traffic_kb);
    $('kpiMessages').textContent = `${a.sent.toLocaleString()} packets transmitted`;
    setDelta('latencyDiff', a.latency_ms, f.latency_ms, 'low');
    setDelta('awarenessDiff', a.awareness_pct, f.awareness_pct, 'high');
    setDelta('pdrDiff', a.safety_pdr_pct, f.safety_pdr_pct, 'high');
  }
  function renderComparison() {
    const { fifo, ai } = state.experiment.results;
    $('comparisonRows').innerHTML = metrics.map(([label, key, unit, best]) => {
      const f = fifo.metrics[key], a = ai.metrics[key], d = a - f;
      const classification = Math.abs(d) < .05 ? 'neutral' : ((best === 'low' ? d < 0 : d > 0) ? 'good' : 'bad');
      const diff = `${d > 0 ? '+' : ''}${d.toFixed(1)} ${unit === '%' ? 'pp' : unit}`;
      return `<tr><td>${label}</td><td>${metricNum(f)} ${unit}</td><td>${metricNum(a)} ${unit}</td><td class="${classification}">${diff}</td></tr>`;
    }).join('');
    const gain = ai.metrics.awareness_pct - fifo.metrics.awareness_pct;
    const ms = fifo.metrics.safety_latency_ms - ai.metrics.safety_latency_ms;
    const isBetter = gain > .05 || ms > .05;
    $('summaryTitle').textContent = isBetter ? 'Safety prioritisation changed the simulated outcome' : 'Compare trade-offs across configurations';
    $('summaryText').textContent = `Under seed ${state.experiment.config.seed}, awareness changed by ${gain.toFixed(1)} percentage points and safety-message latency changed by ${(ai.metrics.safety_latency_ms - fifo.metrics.safety_latency_ms).toFixed(1)} ms. Results are from a simplified synthetic model; repeat across seeds before drawing conclusions.`;
  }
  function renderEvents() {
    const result = currentResult();
    const events = result.logs.filter(e => e.tick <= state.frame).slice(-6).reverse();
    $('eventCount').textContent = `${result.logs.length} EVENTS LOGGED`;
    if (!events.length) { $('eventFeed').innerHTML = '<div class="empty-feed">No events recorded yet.</div>'; return; }
    $('eventFeed').innerHTML = events.map(e => {
      const safe = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      return `<div class="event-row"><div class="event-ico ${e.type}">${e.type === 'warning' ? '!' : e.type === 'success' ? '✓' : '⌁'}</div><div class="event-row-text"><strong>${safe(e.label)}</strong><p>${safe(e.message)}</p></div><span class="event-time">${(e.tick*.1).toFixed(1)}s</span></div>`;
    }).join('');
  }
  function renderAll() { if (!state.experiment) return; renderKPIs(); renderComparison(); drawLatencyChart(); setFrame(state.frame); }
  function setFrame(index) {
    if (!state.experiment) return;
    const series = currentResult().snapshots;
    state.frame = Math.max(0, Math.min(series.length - 1, index));
    const f = series[state.frame];
    $('timeline').value = String(state.frame);
    $('timeDisplay').textContent = `T + ${f.time.toFixed(1)}s`;
    $('playbackTime').textContent = `${f.time.toFixed(1)} / ${(series.length * .1 - .1).toFixed(1)}s`;
    $('statVehicles').textContent = f.vehicles.length;
    $('statHazards').textContent = f.hazards.length;
    $('statQueue').textContent = f.queue;
    $('statDelivered').textContent = f.delivered;
    $('statCapacity').innerHTML = `${f.channel}<span class="muted-unit"> / tick</span>`;
    renderEvents(); drawRoad(f, state.experiment.config.scenario);
  }
  function play() {
    if (!state.experiment || state.playing) return;
    if (state.frame >= currentResult().snapshots.length - 1) setFrame(0);
    state.playing = true; $('playPause').textContent = 'Ⅱ'; $('simBadge').textContent = 'REPLAY IN PROGRESS';
    state.timer = setInterval(() => { if (state.frame >= currentResult().snapshots.length - 1) { pause(); return; } setFrame(state.frame + 1); }, 160 / state.speed);
  }
  function pause() {
    clearInterval(state.timer); state.timer = null; state.playing = false;
    $('playPause').textContent = '▶';
    $('simBadge').textContent = state.experiment ? 'SIMULATION LOADED' : 'SIMULATION READY';
  }
  function roadPaths(ctx, scenario) {
    const road = '#24354b', edge = '#3a4e68', dash = '#71839e';
    ctx.fillStyle = '#101e2e'; ctx.fillRect(0,0,960,540);
    // Map grid, skyline structures and blocks, all intentionally schematic.
    ctx.lineWidth = 1; ctx.strokeStyle = 'rgba(82,123,157,.10)';
    for (let x = 0; x < 960; x += 36) {ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,540);ctx.stroke();}
    for (let y = 0; y < 540; y += 36) {ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(960,y);ctx.stroke();}
    const hRoad = (cy, width) => {ctx.fillStyle = road;ctx.fillRect(0,cy-width/2,960,width);ctx.strokeStyle=edge;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,cy-width/2);ctx.lineTo(960,cy-width/2);ctx.moveTo(0,cy+width/2);ctx.lineTo(960,cy+width/2);ctx.stroke();ctx.setLineDash([20,17]);ctx.strokeStyle=dash;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(0,cy);ctx.lineTo(960,cy);ctx.stroke();ctx.setLineDash([]);};
    const vRoad = (cx, width) => {ctx.fillStyle = road;ctx.fillRect(cx-width/2,0,width,540);ctx.strokeStyle=edge;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(cx-width/2,0);ctx.lineTo(cx-width/2,540);ctx.moveTo(cx+width/2,0);ctx.lineTo(cx+width/2,540);ctx.stroke();ctx.setLineDash([20,17]);ctx.strokeStyle=dash;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(cx,0);ctx.lineTo(cx,540);ctx.stroke();ctx.setLineDash([]);};
    if (scenario === 'intersection') {hRoad(270, 110);vRoad(480, 100);}
    else if (scenario === 'highway') {hRoad(270, 370);[164,218,270,322,376].forEach(y => {ctx.strokeStyle='rgba(165,185,206,.33)';ctx.setLineDash([26,18]);ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(960,y);ctx.stroke();ctx.setLineDash([]);});}
    else {hRoad(152,100);hRoad(392,100);vRoad(316,78);vRoad(652,78);}
    ctx.fillStyle='rgba(29,58,70,.45)';
    if(scenario!=='highway'){
      for(let x=35;x<960;x+=98){for(let y=35;y<540;y+=93){
        if((scenario==='intersection' && (Math.abs(x-480)<115 || Math.abs(y-270)<100)) || (scenario==='urban' && (Math.abs(x-316)<87 || Math.abs(x-652)<87 || Math.abs(y-152)<85 || Math.abs(y-392)<85)))continue;
        ctx.fillRect(x,y,65,48);ctx.strokeStyle='#2d5165';ctx.strokeRect(x,y,65,48);
      }}
    }
    ctx.font='bold 11px system-ui';ctx.fillStyle='#52748c';ctx.fillText('CONNECTED ROAD TESTBED',20,27);
  }
  function drawRoad(frame, scenario) {
    const canvas=$('roadCanvas'),ctx=canvas.getContext('2d');if(!ctx)return;
    ctx.clearRect(0,0,960,540);roadPaths(ctx,scenario);
    const vehicles = Object.fromEntries(frame.vehicles.map(v => [v.id, v]));
    frame.transmissions.forEach(tx => {
      const a=vehicles[tx.from],b=vehicles[tx.to];if(!a||!b||tx.status==='lost')return;
      ctx.strokeStyle=tx.kind==='hazard'?'rgba(255,188,95,.55)':'rgba(53,214,245,.14)';ctx.lineWidth=tx.kind==='hazard'?2:1;
      ctx.setLineDash([4,6]);ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();ctx.setLineDash([]);
    });
    frame.hazards.forEach(h => {
      const {x,y}=h;
      for(let radius=17;radius<=45;radius+=14){ctx.beginPath();ctx.arc(x,y,radius,0,Math.PI*2);ctx.strokeStyle=`rgba(255,117,91,${.33-(radius-17)*.007})`;ctx.lineWidth=1.4;ctx.stroke();}
      ctx.beginPath();ctx.arc(x,y,10,0,Math.PI*2);ctx.fillStyle='#ff7c72';ctx.fill();
      ctx.fillStyle='#22182a';ctx.font='bold 12px system-ui';ctx.textAlign='center';ctx.fillText('!',x,y+4);
      ctx.fillStyle='#ffd0b6';ctx.font='bold 10px system-ui';ctx.fillText(h.label.toUpperCase(),x,y-51);ctx.textAlign='left';
    });
    frame.vehicles.forEach((v,i) => {
      if(v.x < -18 || v.x > 980 || v.y < -18 || v.y > 560) return;
      ctx.save();ctx.translate(v.x,v.y);ctx.rotate(v.angle*Math.PI/180);
      const primary=i % 6===0;
      ctx.fillStyle=primary?'#65dcfb':i%4===0?'#b3a6ff':'#90adc7';ctx.shadowColor=primary?'rgba(53,214,245,.5)':'transparent';ctx.shadowBlur=primary?14:0;
      ctx.beginPath();ctx.roundRect(-11,-6,22,12,3);ctx.fill();ctx.shadowBlur=0;
      ctx.fillStyle='#213247';ctx.fillRect(-2,-4,7,8);
      ctx.fillStyle='#f4e9ab';ctx.fillRect(9,-4,2,2);ctx.fillRect(9,2,2,2);
      ctx.restore();
      if(primary){ctx.font='9px system-ui';ctx.fillStyle='#b0e7f3';ctx.fillText(v.id,v.x-10,v.y-12);}
    });
  }
  function chartCanvas() {
    const canvas=$('latencyChart'),rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);
    const w=Math.max(320,Math.round(rect.width)),h=Math.max(190,Math.round(rect.height));
    if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)) {canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
    const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);return {ctx,w,h};
  }
  function drawLatencyChart() {
    if(!state.experiment)return;
    const {ctx,w,h}=chartCanvas(), l=45,r=14,t=14,b=30;
    const {fifo,ai}=state.experiment.results;
    const values=[...fifo.series.latency,...ai.series.latency].filter(v=>Number.isFinite(v));
    const max=Math.max(100,Math.ceil(Math.max(...values,100)/100)*100);
    ctx.font='10px system-ui';ctx.lineWidth=1;
    for(let i=0;i<=4;i++) {
      const y=t+(h-t-b)*i/4;ctx.strokeStyle='#26394f';ctx.beginPath();ctx.moveTo(l,y);ctx.lineTo(w-r,y);ctx.stroke();
      ctx.fillStyle='#8499af';ctx.textAlign='right';ctx.fillText(String(Math.round(max*(1-i/4))),l-9,y+4);
    }
    const count=ai.series.tick.length;
    for(let i=0;i<=4;i++){const x=l+(w-l-r)*i/4;ctx.fillStyle='#8499af';ctx.textAlign='center';ctx.fillText(`${((count-1)*i*.1/4).toFixed(1)}s`,x,h-9);}
    const seriesDraw=(data,color)=>{
      ctx.strokeStyle=color;ctx.lineWidth=2.3;ctx.beginPath();let on=false;
      data.forEach((v,i)=>{if(!Number.isFinite(v)){on=false;return;}
        const x=l+(w-r-l)*i/Math.max(1,count-1),y=t+(h-b-t)*(1-v/max);
        if(!on){ctx.moveTo(x,y);on=true;}else ctx.lineTo(x,y);
      });ctx.stroke();
    };
    seriesDraw(fifo.series.latency,colors.purple);seriesDraw(ai.series.latency,colors.cyan);
    ctx.textAlign='left';
  }
  function fileDownload(name,content,mime) {
    const blob=new Blob([content],{type:mime}),url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function exportJSON() {
    if(!state.experiment){toast('Run an experiment before exporting data.',true);return;}
    fileDownload(`v2x-experiment-seed-${state.experiment.config.seed}.json`,JSON.stringify(state.experiment,null,2),'application/json');
  }
  function exportCSV() {
    if(!state.experiment){toast('Run an experiment before exporting metrics.',true);return;}
    const data=state.experiment;let rows=['scheduler,metric,value,unit,scenario,vehicles,load,capacity,seed'];
    ['fifo','ai'].forEach(algorithm=>{metrics.forEach(([,key,unit])=>{
      rows.push([algorithm,key,data.results[algorithm].metrics[key],unit,data.config.scenario,data.config.vehicles,data.config.load,data.config.capacity,data.config.seed].join(','));
    });});
    fileDownload(`v2x-comparison-seed-${data.config.seed}.csv`,rows.join('\r\n'),'text/csv');
  }
  async function init() {
    bindControls();
    try {
      const response=await fetch('/api/health');if(!response.ok)return;
      const data=await response.json();
      $('modelMini').textContent=data.ai.kind==='heuristic'?'HEURISTIC':'ML READY';
      $('trafficStatusMini').textContent=data.sumo_trace_available?'SUMO READY':'READY';
    }catch(_){/* Connection errors are surfaced when running experiments. */}
    // Draw a useful static starter scene rather than an empty black canvas.
    drawRoad({vehicles:[{id:'V01',x:240,y:252,angle:0},{id:'V02',x:670,y:286,angle:180},{id:'V03',x:461,y:170,angle:90},{id:'V04',x:500,y:420,angle:-90}],hazards:[],transmissions:[]},'intersection');
  }
  document.addEventListener('DOMContentLoaded', init);
})();
