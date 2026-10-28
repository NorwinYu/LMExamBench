'use strict';

/* ------------------------------------------------------------------ state */
const state = { runs: [], run: null, bank: null, config: null, profiles: null, pollTimer: null, compareIds: [], mode: 'single', subtab: 'overview' };

const NS = 'http://www.w3.org/2000/svg';
const TYPE_LABEL = { choice: '选择', multi: '多选', judge: '判断', fill: '填空', solution: '解答', interview: '面试', code: '编程' };
const DIFF_LABEL = { easy: '简单', medium: '中等', hard: '困难' };

/* ------------------------------------------------------------- dom helpers */
function el(tag, attrs, ...children) {
  const e = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'text') e.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2).toLowerCase(), v);
      else e.setAttribute(k, v);
    }
  }
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return e;
}

function svgEl(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

const fmt = n => (typeof n === 'number' && isFinite(n)) ? String(Math.round(n * 100) / 100) : '-';
const statusLabel = s => ({ running: '进行中', done: '完成', error: '出错' }[s] || s);
const stageNameMap = () => {
  const m = {};
  (state.bank && state.bank.stages || []).forEach(s => { m[s.id] = s.name; });
  if (state.run && state.run.summary) state.run.summary.stages.forEach(s => { m[s.id] = s.name; });
  return m;
};

/* ------------------------------------------------------------------- api */
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.status + ' ' + res.statusText;
    try { const j = await res.json(); if (j.error) msg = j.error; } catch (_) { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

/* ----------------------------------------------------------------- modes */
function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll('.modes button').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  ['single', 'compare', 'manage', 'settings'].forEach(m => {
    document.getElementById('view-' + m).classList.toggle('hidden', m !== mode);
  });
  document.getElementById('sidebar').classList.toggle('hidden', mode !== 'single');
  if (mode === 'single') {
    renderContextBar();
    renderOverview();
    renderDetail();
    if (state.run && state.run.status === 'running') startPolling();
  } else if (mode === 'compare') {
    renderCompare();
  } else if (mode === 'manage') {
    renderManage();
  } else if (mode === 'settings') {
    renderSettings();
  }
}

function setSubtab(sub) {
  state.subtab = sub;
  document.querySelectorAll('#subtabs button').forEach(b => b.classList.toggle('active', b.dataset.subtab === sub));
  document.getElementById('single-overview').classList.toggle('hidden', sub !== 'overview');
  document.getElementById('single-detail').classList.toggle('hidden', sub !== 'detail');
}

function renderContextBar() {
  const root = document.getElementById('single-context');
  root.textContent = '';
  const run = state.run;
  if (!run) {
    root.append(el('div', { class: 'hint' }, '请从左侧选择一次运行，或到「评测与题库」发起新评测。'));
    return;
  }
  const cfg = run.config || {};
  const prof = run.profile;
  const profText = (prof && prof.id) ? ` · 方案 ${prof.name || prof.id}/${prof.level || ''}` : '';
  root.append(el('div', {},
    el('div', { class: 'ctx-title' }, '运行 ' + run.id),
    el('div', { class: 'hint' },
      `模型 ${(cfg.model || {}).name || '-'} · ${run.created_at || ''} · ${statusLabel(run.status)}` +
      profText + (run.duration_s ? ` · 耗时 ${run.duration_s}s` : ''))
  ));
  root.append(el('div', { class: 'ctx-actions' },
    el('a', {
      href: '/api/runs/' + encodeURIComponent(run.id) + '/export',
      target: '_blank', class: 'btn ghost', style: 'text-decoration:none',
    }, '导出 HTML'),
    el('a', {
      href: '/api/runs/' + encodeURIComponent(run.id) + '/export.pdf',
      target: '_blank', class: 'btn ghost', style: 'text-decoration:none',
    }, '导出 PDF'),
    el('button', { class: 'btn ghost', onclick: () => rerunRun(run) }, '按此配置重跑'),
    el('button', { class: 'btn ghost danger', onclick: () => deleteRun(run) }, '删除'),
    el('button', { class: 'btn ghost', onclick: () => selectRun(run.id) }, '刷新')
  ));
}

async function rerunRun(run) {
  const cfg = run.config || {};
  const body = {
    base_url: (cfg.model || {}).base_url,
    model: (cfg.model || {}).name,
    preset: cfg.preset,
  };
  if (Array.isArray(run.stages) && run.stages.length) body.stages = run.stages;
  if (cfg.sample) body.sample = cfg.sample;
  if (cfg.seed != null) body.seed = cfg.seed;
  if (cfg.code_samples) body.code_samples = cfg.code_samples;
  try {
    const r = await api('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    await refreshRuns();
    await selectRun(r.id);
  } catch (e) {
    alert('重跑失败：' + e.message);
  }
}

async function deleteRun(run) {
  if (!confirm(`删除运行 ${run.id} ？`)) return;
  try {
    await api('/api/runs/' + encodeURIComponent(run.id), { method: 'DELETE' });
    state.run = null;
    await refreshRuns();
    if (state.runs.length) await selectRun(state.runs[0].id);
    else setMode('manage');
  } catch (e) {
    alert('删除失败：' + e.message);
  }
}

/* ------------------------------------------------------------------ init */
async function init() {
  document.querySelectorAll('.modes button').forEach(b => {
    b.addEventListener('click', () => setMode(b.dataset.mode));
  });
  document.querySelectorAll('#subtabs button').forEach(b => {
    b.addEventListener('click', () => setSubtab(b.dataset.subtab));
  });
  document.getElementById('refresh-runs').addEventListener('click', () => refreshRuns());
  const errors = [];
  for (const [key, path, fallback] of [
    ['bank', '/api/bank', { stages: [] }],
    ['config', '/api/config', {}],
    ['profiles', '/api/profiles', { profiles: {}, levels: ['校招', '初级', '中级', '高级', '专家'] }],
  ]) {
    try { state[key] = await api(path); }
    catch (e) { state[key] = fallback; errors.push(`${path}: ${e.message}`); }
  }
  if (errors.length) {
    document.getElementById('top-meta').textContent = '部分数据加载失败：' + errors.join('；');
  }
  await refreshRuns();
  if (state.runs.length) {
    setMode('single');
    await selectRun(state.runs[0].id);
  } else {
    setMode('manage');
  }
}

async function refreshRuns() {
  const data = await api('/api/runs');
  state.runs = data.runs || [];
  renderRunList();
}

async function selectRun(id) {
  state.run = await api('/api/runs/' + encodeURIComponent(id));
  if (state.mode !== 'single') setMode('single');
  renderTopMeta();
  renderRunList();
  renderContextBar();
  renderOverview();
  renderDetail();
  if (state.run.status === 'running') startPolling();
}

function renderTopMeta() {
  const m = document.getElementById('top-meta');
  if (!state.run) { m.textContent = ''; return; }
  const cfg = state.run.config || {};
  m.textContent = `${(cfg.model || {}).name || ''} · ${statusLabel(state.run.status)}`;
}

/* ------------------------------------------------------------- run list */
function renderRunList() {
  const ul = document.getElementById('run-list');
  ul.textContent = '';
  document.getElementById('side-title').textContent = `运行记录 (${state.runs.length})`;
  if (!state.runs.length) { ul.append(el('li', { class: 'hint' }, '暂无记录')); return; }
  for (const r of state.runs) {
    const active = state.run && state.run.id === r.id;
    const ov = r.overall || {};
    const score = (typeof ov.weighted_percent === 'number') ? `${ov.weighted_percent.toFixed(1)} 分` : '';
    const li = el('li', active ? { class: 'active' } : {},
      el('div', { class: 'rl-top' },
        el('span', {}, r.model || r.id),
        el('span', { class: 'pill ' + r.status }, statusLabel(r.status))
      ),
      el('div', { class: 'rl-sub' }, `${r.created_at || ''} ${score}`)
    );
    li.addEventListener('click', () => selectRun(r.id));
    ul.append(li);
  }
}

/* ------------------------------------------------------------- polling */
function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = setInterval(tick, 2500);
}
function stopPolling() {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
}
async function tick() {
  if (!state.run || state.run.status !== 'running') { stopPolling(); return; }
  try {
    state.run = await api('/api/runs/' + encodeURIComponent(state.run.id));
    renderTopMeta();
    renderOverview();
    renderDetail();
    if (state.run.status !== 'running') { stopPolling(); refreshRuns(); }
  } catch (_) { /* keep polling */ }
}

/* ------------------------------------------------------------- overview */
function stat(k, v) {
  return el('div', { class: 'stat' }, el('div', { class: 'k' }, k), el('div', { class: 'v' }, v));
}

function radarChart(stages) {
  const size = 300, cx = size / 2, cy = size / 2, R = size * 0.34, n = stages.length;
  const svg = svgEl('svg', { viewBox: `0 0 ${size} ${size}`, class: 'radar' });
  if (!n) return svg;
  const ang = i => -Math.PI / 2 + i * 2 * Math.PI / n;
  const pt = (i, fr) => [cx + R * fr * Math.cos(ang(i)), cy + R * fr * Math.sin(ang(i))];
  [0.25, 0.5, 0.75, 1].forEach(fr => {
    svg.append(svgEl('polygon', {
      points: stages.map((_, i) => pt(i, fr).join(',')).join(' '), class: 'ring',
    }));
  });
  stages.forEach((_, i) => {
    const [x, y] = pt(i, 1);
    svg.append(svgEl('line', { x1: cx, y1: cy, x2: x, y2: y, class: 'spoke' }));
  });
  const dataPts = stages.map((s, i) => {
    const fr = Math.max(0, Math.min(100, s.percent)) / 100;
    return pt(i, fr).join(',');
  }).join(' ');
  svg.append(svgEl('polygon', { points: dataPts, class: 'data' }));
  stages.forEach((s, i) => {
    const fr = Math.max(0.02, Math.min(100, s.percent) / 100);
    const [x, y] = pt(i, fr);
    svg.append(svgEl('circle', { cx: x, cy: y, r: 3.2, class: 'dot' }));
    const [lx, ly] = pt(i, 1.16);
    const anchor = lx > cx + 6 ? 'start' : lx < cx - 6 ? 'end' : 'middle';
    const t = svgEl('text', {
      x: lx, y: ly, class: 'label', 'text-anchor': anchor, 'dominant-baseline': 'middle',
    });
    t.textContent = `${s.name} ${s.percent.toFixed(0)}`;
    svg.append(t);
  });
  return svg;
}

function stageBars(stages) {
  const wrap = el('div', { class: 'bars' });
  for (const s of stages) {
    wrap.append(el('div', { class: 'bar-row' },
      el('div', { class: 'bar-label' }, s.name),
      el('div', { class: 'bar-track' }, el('div', {
        class: 'bar-fill', style: `width:${Math.max(0, Math.min(100, s.percent))}%`,
      })),
      el('div', { class: 'bar-val' }, `${s.percent.toFixed(1)}%`)
    ));
  }
  return wrap;
}

function typeTable(types) {
  const names = stageNameMap();
  const tb = el('tbody');
  for (const x of types) {
    tb.append(el('tr', {},
      el('td', {}, names[x.stage] || x.stage),
      el('td', {}, TYPE_LABEL[x.type] || x.type),
      el('td', {}, `${x.percent.toFixed(1)}%` + (x.low_sample ? ' ⚠' : '')),
      el('td', {}, `${fmt(x.earned)} / ${fmt(x.graded_total)}`),
      el('td', {}, String(x.graded_n))
    ));
  }
  return el('table', { class: 'grid' },
    el('thead', {}, el('tr', {},
      el('th', {}, '阶段'), el('th', {}, '题型'),
      el('th', {}, '得分率'), el('th', {}, '得分 / 满分'), el('th', {}, '题数')
    )), tb);
}

function subjectTable(subjects) {
  const names = stageNameMap();
  const tb = el('tbody');
  for (const x of subjects) {
    tb.append(el('tr', {},
      el('td', {}, names[x.stage] || x.stage),
      el('td', {}, x.subject),
      el('td', {}, `${x.percent.toFixed(1)}%` + (x.low_sample ? ' ⚠' : '')),
      el('td', {}, `${fmt(x.earned)} / ${fmt(x.graded_total)}`),
      el('td', {}, String(x.graded_n))
    ));
  }
  return el('table', { class: 'grid' },
    el('thead', {}, el('tr', {},
      el('th', {}, '阶段'), el('th', {}, '学科'),
      el('th', {}, '得分率'), el('th', {}, '得分 / 满分'), el('th', {}, '题数')
    )), tb);
}

function roundsTable(rounds) {
  const names = stageNameMap();
  const tb = el('tbody');
  for (const x of rounds) {
    tb.append(el('tr', {},
      el('td', {}, names[x.stage] || x.stage),
      el('td', {}, x.round),
      el('td', {}, `${x.percent.toFixed(1)}%` + (x.low_sample ? ' ⚠' : '')),
      el('td', {}, `${fmt(x.earned)} / ${fmt(x.graded_total)}`),
      el('td', {}, String(x.graded_n))
    ));
  }
  return el('table', { class: 'grid' },
    el('thead', {}, el('tr', {},
      el('th', {}, '阶段'), el('th', {}, '轮次'),
      el('th', {}, '得分率'), el('th', {}, '得分 / 满分'), el('th', {}, '题数')
    )), tb);
}

function roleTable(roles) {
  const names = stageNameMap();
  const tb = el('tbody');
  for (const x of roles) {
    tb.append(el('tr', {},
      el('td', {}, names[x.stage] || x.stage),
      el('td', {}, x.role),
      el('td', {}, `${x.percent.toFixed(1)}%` + (x.low_sample ? ' ⚠' : '')),
      el('td', {}, `${fmt(x.earned)} / ${fmt(x.graded_total)}`),
      el('td', {}, String(x.graded_n))
    ));
  }
  return el('table', { class: 'grid' },
    el('thead', {}, el('tr', {},
      el('th', {}, '阶段'), el('th', {}, '岗位'),
      el('th', {}, '得分率'), el('th', {}, '得分 / 满分'), el('th', {}, '题数')
    )), tb);
}

function levelTable(levels) {
  const names = stageNameMap();
  const tb = el('tbody');
  for (const x of levels) {
    tb.append(el('tr', {},
      el('td', {}, names[x.stage] || x.stage),
      el('td', {}, x.level),
      el('td', {}, `${x.percent.toFixed(1)}%` + (x.low_sample ? ' ⚠' : '')),
      el('td', {}, `${fmt(x.earned)} / ${fmt(x.graded_total)}`),
      el('td', {}, String(x.graded_n))
    ));
  }
  return el('table', { class: 'grid' },
    el('thead', {}, el('tr', {},
      el('th', {}, '阶段'), el('th', {}, '职级'),
      el('th', {}, '得分率'), el('th', {}, '得分 / 满分'), el('th', {}, '题数')
    )), tb);
}

function difficultyTable(diffs) {
  const tb = el('tbody');
  for (const x of diffs) {
    tb.append(el('tr', {},
      el('td', {}, DIFF_LABEL[x.difficulty] || x.difficulty),
      el('td', {}, `${x.percent.toFixed(1)}%` + (x.low_sample ? ' ⚠' : '')),
      el('td', {}, `${fmt(x.earned)} / ${fmt(x.graded_total)}`),
      el('td', {}, String(x.graded_n))
    ));
  }
  return el('table', { class: 'grid' },
    el('thead', {}, el('tr', {},
      el('th', {}, '难度'), el('th', {}, '得分率'),
      el('th', {}, '得分 / 满分'), el('th', {}, '题数')
    )), tb);
}

function renderOverview() {
  const root = document.getElementById('single-overview');
  root.textContent = '';
  const run = state.run;
  if (!run) {
    root.append(el('div', { class: 'empty' }, '暂无运行记录，去「运行评测」开始一次。'));
    return;
  }
  const cfg = run.config || {};
  const exportLink = el('a', {
    href: `/api/runs/${encodeURIComponent(run.id)}/export`,
    target: '_blank',
    class: 'btn ghost',
    style: 'margin-left:auto;padding:5px 12px;font-size:13px;text-decoration:none',
  }, '导出 HTML 报告');
  root.append(el('div', { class: 'card', style: 'display:flex;align-items:center;gap:20px;flex-wrap:wrap' },
    el('div', {},
      el('h2', {}, `运行 ${run.id}`),
      el('div', { class: 'hint' },
        `模型：${(cfg.model || {}).name || '-'}　裁判：${(cfg.judge || {}).enabled ? '开' : '关'}` +
        `　权重：${cfg.preset || '-'}　时间：${run.created_at || ''}` +
        (run.duration_s ? `　耗时：${run.duration_s}s` : ''))
    ),
    exportLink
  ));

  if (run.status === 'running') {
    const p = run.progress || { done: 0, total: 0 };
    const pct = p.total ? Math.round(p.done / p.total * 100) : 0;
    root.append(el('div', { class: 'card' },
      el('h2', {}, '评测进行中'),
      el('div', { class: 'progress' },
        el('div', { class: 'pg-track' }, el('div', { class: 'pg-fill', style: `width:${pct}%` })),
        el('span', {}, `${p.done} / ${p.total}`)
      ),
      el('div', { class: 'hint', style: 'margin-top:8px' }, '结果会在「逐题明细」中实时出现。')
    ));
    startPolling();
    return;
  }

  if (run.error) {
    root.append(el('div', { class: 'card' }, el('h2', {}, '运行出错'),
      el('pre', { class: 'text' }, run.error)));
    return;
  }

  const sum = run.summary;
  if (!sum) { root.append(el('div', { class: 'empty' }, '暂无结果')); return; }
  const ov = sum.overall;

  if (sum.judge && sum.judge.self_judge) {
    root.append(el('div', { class: 'card warn-card' },
      '⚠ 裁判模型与被测模型相同（self-judge），主观题分数可能偏高。建议换用独立的 judge 模型。'));
  }

  root.append(el('div', { class: 'card' },
    el('div', { class: 'hero' },
      el('div', { class: 'big' }, ov.weighted_percent.toFixed(1), el('small', {}, ' 分')),
      el('div', { class: 'stats' },
        stat('等级', el('span', { class: 'grade' }, `${ov.grade.letter} · ${ov.grade.label}`)),
        stat('原始得分率', `${ov.percent.toFixed(1)}%`),
        stat('覆盖率', `${(ov.coverage * 100).toFixed(0)}%`),
        stat('已评 / 总数', `${ov.graded_n} / ${ov.n}`)
      )
    )
  ));

  if (sum.profile) {
    const p = sum.profile;
    root.append(el('div', { class: 'card' },
      el('h2', {}, '评估方案'),
      el('div', { class: 'hint' }, `${p.name} · ${p.level}` + (p.note ? `　${p.note}` : '')),
      el('div', { class: 'stats', style: 'margin-top:10px' },
        stat('方案得分', `${p.score}%`),
        stat('阶段加权', p.stage_score != null ? `${p.stage_score}%` : '-'),
        stat('能力维度', p.capability_score != null ? `${p.capability_score}%` : '-'),
        stat('岗位维度', p.role_score != null ? `${p.role_score}%` : '-')
      )
    ));
  }

  if (run.paper && run.paper.sections && run.paper.sections.length) {
    const subjMap = {};
    (sum.subjects || []).forEach(x => { subjMap[x.stage + '|' + x.subject] = x; });
    const roleMap = {};
    (sum.roles || []).forEach(x => { roleMap[x.stage + '|' + x.role] = x; });
    const tb = el('tbody');
    for (const sec of run.paper.sections) {
      const a = sec.stage === 'interview'
        ? roleMap[sec.stage + '|' + sec.section]
        : subjMap[sec.stage + '|' + sec.section];
      tb.append(el('tr', {},
        el('td', {}, sec.stage),
        el('td', {}, sec.section),
        el('td', {}, String(sec.count)),
        el('td', {}, fmt(sec.points)),
        el('td', {}, a ? `${a.percent.toFixed(1)}%` : '-'),
        el('td', {}, a && a.low_sample ? '样本不足' : '')
      ));
    }
    root.append(el('div', { class: 'card' },
      el('h2', {}, `试卷结构（每部分最多 ${run.paper.per_section} 题）`),
      el('table', { class: 'grid' },
        el('thead', {}, el('tr', {},
          el('th', {}, '阶段'), el('th', {}, '部分'), el('th', {}, '题数'),
          el('th', {}, '满分'), el('th', {}, '得分率'), el('th', {}, '备注')
        )), tb)
    ));
  }

  root.append(el('div', { class: 'card' },
    el('h2', {}, '各阶段成绩'),
    el('div', { class: 'charts' }, radarChart(sum.stages), stageBars(sum.stages))
  ));

  root.append(el('div', { class: 'card' }, el('h2', {}, '题型细分'), typeTable(sum.types)));

  if (sum.rounds && sum.rounds.length) {
    root.append(el('div', { class: 'card' }, el('h2', {}, '面试轮次'), roundsTable(sum.rounds)));
  }

  if (sum.roles && sum.roles.length) {
    root.append(el('div', { class: 'card' }, el('h2', {}, '面试岗位'), roleTable(sum.roles)));
  }

  if (sum.levels && sum.levels.length) {
    root.append(el('div', { class: 'card' }, el('h2', {}, '面试职级'), levelTable(sum.levels)));
  }

  if (sum.capabilities && sum.capabilities.length) {
    const caps = sum.capabilities.map(c => ({ name: c.capability, percent: c.percent }));
    root.append(el('div', { class: 'card' },
      el('h2', {}, '能力画像'),
      el('div', { class: 'charts' }, radarChart(caps), stageBars(caps))
    ));
  }

  if (sum.difficulties && sum.difficulties.length) {
    root.append(el('div', { class: 'card' }, el('h2', {}, '难度分层'), difficultyTable(sum.difficulties)));
  }

  root.append(el('div', { class: 'card' }, el('h2', {}, '学科细分'), subjectTable(sum.subjects)));
}

/* --------------------------------------------------------------- detail */
function block(k, node) {
  return el('div', { class: 'q-block' }, el('div', { class: 'k' }, k), node);
}

function gradingBlock(g, r) {
  const wrap = el('div');
  const m = g.method;
  if (g.error) wrap.append(el('div', { class: 'err' }, g.error));

  if (m === 'judge') {
    const pts = g.point_scores || [];
    if (pts.length) {
      pts.forEach((p, i) => {
        const s = Number(p.score) || 0;
        wrap.append(el('div', { class: 'score-row' },
          el('div', { class: 'r' },
            el('div', {}, `${i + 1}. ${p.point || ''}`),
            p.reason ? el('div', { class: 'hint' }, p.reason) : null
          ),
          el('div', { class: 'mini-track' }, el('div', {
            class: 'mini-fill', style: `width:${Math.max(0, Math.min(100, s * 100))}%`,
          })),
          el('div', { class: 's' }, s.toFixed(2))
        ));
      });
    }
    if (g.comment) wrap.append(el('div', { class: 'hint' }, `评语：${g.comment}`));
    if (g.judge_model !== undefined || g.debias !== undefined) {
      const bits = [];
      if (g.judge_model) bits.push(`裁判：${g.judge_model}`);
      if (g.debias) {
        bits.push(g.agreement != null ? `双向判分（一致性 ${g.agreement}）` : '双向判分');
      }
      if (g.self_judge) bits.push('⚠ 裁判与被测为同一模型');
      if (bits.length) wrap.append(el('div', { class: 'hint' }, bits.join('　')));
    }
  } else if (m === 'tests') {
    if (g.samples > 1) {
      wrap.append(el('div', { class: 'hint' },
        `pass@${g.samples}：${g.pass_at_k}　通过 ${g.passed_all}/${g.samples}　` +
        `可见用例 ${g.visible_cases}　隐藏用例 ${g.hidden_cases}`));
    }
    const cases = g.cases || [];
    if (cases.length) {
      const tb = el('tbody');
      for (const c of cases) {
        tb.append(el('tr', {},
          el('td', {}, c.call || ''),
          el('td', {}, JSON.stringify(c.expected)),
          el('td', {}, c.error ? c.error : JSON.stringify(c.got)),
          el('td', {}, c.ok ? '✅' : '❌')
        ));
      }
      wrap.append(el('table', { class: 'grid' },
        el('thead', {}, el('tr', {},
          el('th', {}, '用例'), el('th', {}, '预期'), el('th', {}, '实际'), el('th', {}, '结果')
        )), tb));
    }
  } else if (g.detail) {
    const d = g.detail;
    if (d.accepted !== undefined) {
      wrap.append(el('div', { class: 'hint' },
        `可接受答案：${(d.accepted || []).join(' / ')}　实际：${String(d.got)}`));
    } else if (d.expected !== undefined) {
      wrap.append(el('div', { class: 'hint' },
        `预期：${String(d.expected)}　实际：${String(d.got)}`));
    }
  }
  return wrap;
}

function questionCard(r) {
  const g = r.grading || {};
  const max = (g.max != null) ? g.max : r.points;
  const sc = g.score;
  let cls = 'na', label = '未评';
  if (typeof sc === 'number') {
    label = `${fmt(sc)} / ${fmt(max)}`;
    cls = sc >= max - 1e-9 ? 'full' : sc <= 0 ? 'zero' : 'part';
  }
  const head = el('div', { class: 'q-head' },
    el('span', { class: 'badge ' + r.type }, TYPE_LABEL[r.type] || r.type),
    el('span', { class: 'q-id' }, r.id),
    el('span', { class: 'q-subject' }, r.subject || ''),
    el('span', { class: 'q-chips' },
      ...(r.role ? [el('span', { class: 'cap-chip' }, r.role)] : []),
      ...(r.level ? [el('span', { class: 'cap-chip' }, r.level)] : []),
      ...(r.round ? [el('span', { class: 'cap-chip' }, r.round)] : []),
      ...(r.chapter ? [el('span', { class: 'tag-chip' }, r.chapter)] : []),
      ...(r.topic ? [el('span', { class: 'tag-chip' }, r.topic)] : []),
      ...(r.capabilities || []).map(c => el('span', { class: 'cap-chip' }, c)),
      ...(r.tags || []).map(t => el('span', { class: 'tag-chip' }, t))
    ),
    el('span', { class: 'q-score ' + cls }, label),
    el('span', { class: 'chev' }, '▸')
  );
  const body = el('div', { class: 'q-body hidden' });
  body.append(block('题目', el('pre', { class: 'text' }, r.question)));
  if (r.options && r.options.length) {
    const ul = el('ul', { class: 'opts' });
    r.options.forEach(o => ul.append(el('li', {}, o)));
    body.append(block('选项', ul));
  }
  if (r.model_output) body.append(block('模型作答', el('pre', { class: 'text' }, r.model_output)));
  if (r.reasoning) body.append(block('思考过程 / reasoning', el('pre', { class: 'text reasoning' }, r.reasoning)));
  body.append(block('判分', gradingBlock(g, r)));
  if (r.reference) body.append(block('参考答案 / 解析', el('pre', { class: 'text' }, r.reference)));
  head.addEventListener('click', () => body.classList.toggle('hidden'));
  return el('div', { class: 'q-card' }, head, body);
}

function renderDetail() {
  const root = document.getElementById('single-detail');
  root.textContent = '';
  const run = state.run;
  if (!run) { root.append(el('div', { class: 'empty' }, '选择一次运行后查看逐题明细。')); return; }
  const groups = {};
  for (const r of run.results) (groups[r.stage] = groups[r.stage] || []).push(r);
  const order = [];
  (state.bank && state.bank.stages || []).forEach(s => { if (groups[s.id]) order.push(s.id); });
  for (const sid of Object.keys(groups)) if (!order.includes(sid)) order.push(sid);
  if (!order.length) {
    root.append(el('div', { class: 'empty' }, run.status === 'running' ? '评测进行中，暂无结果…' : '暂无结果'));
    return;
  }
  for (const sid of order) {
    const qs = groups[sid];
    const name = qs[0].stage_name || sid;
    const earned = qs.reduce((a, r) => a + (typeof (r.grading || {}).score === 'number' ? r.grading.score : 0), 0);
    const total = qs.reduce((a, r) => a + (typeof (r.grading || {}).score === 'number' ? r.grading.max : 0), 0);
    root.append(el('div', { class: 'stage-head' },
      el('h2', {}, name),
      el('span', { class: 'muted' }, `${qs.length} 题 · ${fmt(earned)} / ${fmt(total)} 分`)
    ));
    for (const r of qs) root.append(questionCard(r));
  }
}

/* ------------------------------------------------------------- run form */
function renderManage(preserve) {
  const root = document.getElementById('view-manage');
  root.textContent = '';
  const cfg = state.config || {};
  const bank = state.bank || { stages: [] };
  const prev = preserve && state._form ? state._form : null;

  const baseUrl = el('input', { type: 'text', value: (prev && prev.baseUrl) || ((cfg.model || {}).base_url || 'http://127.0.0.1:11434/v1') });
  const model = el('input', { type: 'text', value: (prev && prev.model) || ((cfg.model || {}).name || '') });
  const apiKey = el('input', { type: 'password', placeholder: 'Ollama 可留空' });
  const preset = el('select');
  (cfg.presets || ['balanced']).forEach(p => preset.append(el('option', { value: p }, p)));
  preset.value = (prev && prev.preset) || cfg.preset || 'balanced';
  const limit = el('input', { type: 'number', min: '0', value: (prev && prev.limit) || '', placeholder: '0 = 全部' });
  const codeSamples = el('input', {
    type: 'number', min: '1',
    value: (prev && prev.codeSamples) || String(cfg.code_samples || 1),
  });
  const sample = el('input', {
    type: 'number', min: '0', placeholder: '0 = 全部',
    value: (prev && prev.sample) || String(cfg.sample || 0),
  });
  const seed = el('input', {
    type: 'number', placeholder: '可选，固定可复现',
    value: (prev && prev.seed != null) ? String(prev.seed) : '',
  });
  const paper = el('input', {
    type: 'number', min: '0', placeholder: '0 = 关闭；如 3',
    value: (prev && prev.paper) || '',
  });
  const judge = el('input', { type: 'checkbox' });
  judge.checked = prev ? prev.judge : (cfg.judge_enabled !== false);
  const debias = el('input', { type: 'checkbox' });
  debias.checked = prev ? prev.debias : (cfg.judge_debias !== false);

  const profiles = (state.profiles && state.profiles.profiles) || {};
  const profileSel = el('select');
  profileSel.append(el('option', { value: '' }, '不指定（按阶段权重）'));
  Object.entries(profiles).forEach(([pid, p]) => {
    profileSel.append(el('option', { value: pid }, p.name));
  });
  profileSel.value = (prev && prev.profileId) || '';
  const levelSel = el('select');
  ((state.profiles && state.profiles.levels) || ['校招', '初级', '中级', '高级', '专家'])
    .forEach(l => levelSel.append(el('option', { value: l }, l)));
  levelSel.value = (prev && prev.level) || '中级';

  const form = el('div', { class: 'form-grid' },
    el('label', {}, 'API Base URL'), baseUrl,
    el('label', {}, '模型名称'), model,
    el('label', {}, 'API Key'), apiKey,
    el('label', {}, '权重预设'), preset,
    el('label', {}, '评估方案'), profileSel,
    el('label', {}, '职级'), levelSel,
    el('label', {}, '每阶段题数上限'), limit,
    el('label', {}, '代码题采样数'), codeSamples,
    el('label', {}, '随机抽样/阶段'), sample,
    el('label', {}, '随机种子'), seed,
    el('label', {}, '试卷题数/部分'), paper,
    el('label', {}, 'LLM 裁判'), el('label', {}, judge, ' 启用主观题裁判'),
    el('label', {}, '双向判分'), el('label', {}, debias, ' rubric 正反序各判一次取均值')
  );

  const stagesWrap = el('div', { class: 'stages' });
  bank.stages.forEach(s => {
    const cb = el('input', { type: 'checkbox', value: s.id });
    cb.checked = !prev || (prev.stages || []).includes(s.id);
    stagesWrap.append(el('label', {}, cb, `${s.name} (${s.count})`));
  });
  profileSel.addEventListener('change', () => {
    const p = profiles[profileSel.value];
    if (!p) return;
    const want = new Set(p.stages);
    stagesWrap.querySelectorAll('input').forEach(cb => { cb.checked = want.has(cb.value); });
  });

  const err = el('div', { class: 'err' });
  const info = el('div', { class: 'hint' });
  const btn = el('button', { class: 'btn' }, '开始评测');

  btn.addEventListener('click', async () => {
    err.textContent = ''; info.textContent = '';
    const selected = [...stagesWrap.querySelectorAll('input:checked')].map(x => x.value);
    if (!selected.length) { err.textContent = '至少选择一个阶段'; return; }
    btn.disabled = true;
    const body = {
      base_url: baseUrl.value.trim(),
      model: model.value.trim(),
      api_key: apiKey.value,
      preset: preset.value,
      limit: Number(limit.value) || 0,
      code_samples: Number(codeSamples.value) || 1,
      sample: Number(sample.value) || 0,
      paper: Number(paper.value) || 0,
      seed: seed.value === '' ? null : Number(seed.value),
      profile: profileSel.value || null,
      level: levelSel.value,
      judge_enabled: judge.checked,
      judge_debias: debias.checked,
      stages: selected,
    };
    state._form = {
      baseUrl: baseUrl.value, model: model.value, preset: preset.value,
      limit: limit.value, codeSamples: codeSamples.value,
      sample: sample.value, seed: seed.value === '' ? null : seed.value,
      paper: paper.value,
      profileId: profileSel.value, level: levelSel.value,
      judge: judge.checked, debias: debias.checked,
      stages: selected,
    };
    try {
      const r = await api('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      info.textContent = '已启动：' + r.id;
      await refreshRuns();
      await selectRun(r.id);
      setSubtab('overview');
    } catch (e) {
      err.textContent = '启动失败：' + e.message;
    } finally {
      btn.disabled = false;
    }
  });

  root.append(el('div', { class: 'card' },
    el('h2', {}, '运行新评测'),
    el('div', { class: 'hint', style: 'margin-bottom:14px' },
      '模型需暴露 OpenAI 兼容的 /v1/chat/completions 接口（Ollama / vLLM / LM Studio / llama.cpp server 均可）。'),
    form,
    block('参与阶段', stagesWrap),
    el('div', { class: 'q-block' }, btn, ' ', err),
    info
  ));

  const auditOut = el('div');
  const auditBtn = el('button', { class: 'btn ghost' }, '运行题库审计');
  auditBtn.addEventListener('click', async () => {
    auditOut.textContent = '审计中…';
    try {
      const a = await api('/api/bank/audit');
      auditOut.textContent = '';
      auditOut.append(el('div', { class: 'hint' },
        `共 ${a.total} 题，近似重复对：${a.duplicate_count}（阈值 ${a.threshold}）`));
      if (a.duplicates && a.duplicates.length) {
        const tb = el('tbody');
        a.duplicates.forEach(d => tb.append(el('tr', {},
          el('td', {}, d.a), el('td', {}, d.b), el('td', {}, String(d.similarity)))));
        auditOut.append(el('table', { class: 'grid' },
          el('thead', {}, el('tr', {}, el('th', {}, '题 A'), el('th', {}, '题 B'), el('th', {}, '相似度'))),
          tb));
      } else {
        auditOut.append(el('div', { class: 'hint' }, '未发现近似重复题。'));
      }
      const cov = el('div');
      for (const [stage, row] of Object.entries(a.coverage || {})) {
        cov.append(el('div', { class: 'hint' },
          `${stage}: ` + Object.entries(row).map(([c, n]) => `${c}×${n}`).join('  ')));
      }
      auditOut.append(el('div', { class: 'hint', style: 'margin-top:8px' }, '能力维度覆盖：'), cov);
      if (a.flows) {
        const ftb = el('tbody');
        for (const [lvl, v] of Object.entries(a.flows)) {
          ftb.append(el('tr', {},
            el('td', {}, lvl),
            el('td', {}, (v.expected || []).join(' → ')),
            el('td', {}, (v.missing || []).length ? v.missing.join('、') : '完整')
          ));
        }
        auditOut.append(el('div', { class: 'hint', style: 'margin-top:8px' }, '职级流程覆盖：'),
          el('table', { class: 'grid' },
            el('thead', {}, el('tr', {},
              el('th', {}, '职级'), el('th', {}, '应有轮次'), el('th', {}, '缺失轮次')
            )), ftb));
      }
    } catch (e) {
      auditOut.textContent = '审计失败：' + e.message;
    }
  });
  root.append(el('div', { class: 'card' },
    el('h2', {}, '题库审计'),
    el('div', { class: 'hint' }, '检测题库内近似重复题与能力维度覆盖。'),
    el('div', { class: 'q-block' }, auditBtn),
    auditOut
  ));
}

/* ------------------------------------------------------------- settings */
async function renderSettings() {
  const root = document.getElementById('view-settings');
  root.textContent = '';
  let s;
  try {
    s = await api('/api/settings');
  } catch (e) {
    root.append(el('div', { class: 'card' }, el('h2', {}, '设置'),
      el('div', { class: 'err' }, '加载失败：' + e.message)));
    return;
  }
  const model = s.model || {};
  const judge = s.judge || {};
  const runc = s.run || {};
  const weights = s.weights || {};

  const baseUrl = el('input', { type: 'text', value: model.base_url || '' });
  const name = el('input', { type: 'text', value: model.name || '' });
  const apiKey = el('input', {
    type: 'password',
    placeholder: model.api_key_set ? '已设置，留空保持不变' : '未设置',
  });
  const temperature = el('input', { type: 'number', step: '0.1', min: '0', max: '2', value: String(model.temperature != null ? model.temperature : 0.2) });
  const maxTokens = el('input', { type: 'number', min: '1', value: String(model.max_tokens != null ? model.max_tokens : 2048) });
  const timeout = el('input', { type: 'number', min: '1', value: String(model.timeout != null ? model.timeout : 180) });

  const judgeEnabled = el('input', { type: 'checkbox' });
  judgeEnabled.checked = judge.enabled !== false;
  const judgeDebias = el('input', { type: 'checkbox' });
  judgeDebias.checked = judge.debias !== false;
  const judgeModel = el('input', { type: 'text', value: judge.model || '', placeholder: '留空 = 与被测模型相同' });
  const judgeTemp = el('input', { type: 'number', step: '0.1', min: '0', max: '2', value: String(judge.temperature != null ? judge.temperature : 0) });
  const judgeBase = el('input', { type: 'text', value: judge.base_url || '', placeholder: '留空 = 与被测模型相同' });
  const judgeKey = el('input', { type: 'password', placeholder: judge.api_key_set ? '已设置，留空保持' : '未设置' });

  const concurrency = el('input', { type: 'number', min: '1', max: '32', value: String(runc.concurrency != null ? runc.concurrency : 4) });
  const codeSamples = el('input', { type: 'number', min: '1', max: '10', value: String(runc.code_samples != null ? runc.code_samples : 1) });
  const sample = el('input', { type: 'number', min: '0', value: String(runc.sample != null ? runc.sample : 0) });
  const seed = el('input', { type: 'number', placeholder: '留空 = 随机', value: runc.seed == null ? '' : String(runc.seed) });
  const allowCode = el('input', { type: 'checkbox' });
  allowCode.checked = runc.allow_code_exec !== false;

  const preset = el('select');
  Object.keys(weights.presets || {}).forEach(p => preset.append(el('option', { value: p }, p)));
  preset.value = weights.preset || 'balanced';

  const presetTables = {};
  const presetWraps = {};
  for (const [pname, table] of Object.entries(weights.presets || {})) {
    const tb = el('tbody');
    const inputs = {};
    for (const [stage, val] of Object.entries(table)) {
      const inp = el('input', { type: 'number', step: '0.1', min: '0', value: String(val) });
      inputs[stage] = inp;
      tb.append(el('tr', {}, el('td', {}, stage), el('td', {}, inp)));
    }
    presetTables[pname] = { inputs };
    presetWraps[pname] = el('div', {},
      el('div', { class: 'settings-sub' }, '预设 ' + pname),
      el('table', { class: 'grid weight-table' },
        el('thead', {}, el('tr', {}, el('th', {}, '阶段'), el('th', {}, '权重'))), tb));
  }

  const roleInputs = {};
  const roleTb = el('tbody');
  for (const [role, val] of Object.entries(weights.roles || {})) {
    const inp = el('input', { type: 'number', step: '0.1', min: '0', value: String(val) });
    roleInputs[role] = inp;
    roleTb.append(el('tr', {}, el('td', {}, role), el('td', {}, inp)));
  }
  const roleWrap = el('div', {},
    el('div', { class: 'settings-sub' }, '面试岗位权重（用于面试阶段加权）'),
    el('table', { class: 'grid weight-table' },
      el('thead', {}, el('tr', {}, el('th', {}, '岗位'), el('th', {}, '权重'))), roleTb));

  const err = el('div', { class: 'err' });
  const info = el('div', { class: 'hint' });
  const saveBtn = el('button', { class: 'btn' }, '保存设置');
  saveBtn.addEventListener('click', async () => {
    err.textContent = ''; info.textContent = '';
    const presets = {};
    for (const [pname, obj] of Object.entries(presetTables)) {
      presets[pname] = {};
      for (const [stage, inp] of Object.entries(obj.inputs)) presets[pname][stage] = Number(inp.value);
    }
    const roles = {};
    for (const [role, inp] of Object.entries(roleInputs)) roles[role] = Number(inp.value);
    const body = {
      model: {
        name: name.value.trim(), base_url: baseUrl.value.trim(), api_key: apiKey.value,
        temperature: Number(temperature.value), max_tokens: Number(maxTokens.value),
        timeout: Number(timeout.value),
      },
      judge: {
        enabled: judgeEnabled.checked, debias: judgeDebias.checked,
        model: judgeModel.value.trim(), temperature: Number(judgeTemp.value),
        base_url: judgeBase.value.trim(), api_key: judgeKey.value,
      },
      run: {
        concurrency: Number(concurrency.value), code_samples: Number(codeSamples.value),
        sample: Number(sample.value), seed: seed.value === '' ? null : Number(seed.value),
        allow_code_exec: allowCode.checked,
      },
      weights: { preset: preset.value, presets, roles },
    };
    saveBtn.disabled = true;
    try {
      await api('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      info.textContent = '已保存到 config.json';
      state.config = await api('/api/config');
    } catch (e) {
      err.textContent = '保存失败：' + e.message;
    } finally {
      saveBtn.disabled = false;
    }
  });

  const testOut = el('div', { class: 'hint' });
  const testBtn = el('button', { class: 'btn ghost' }, '测试连接');
  testBtn.addEventListener('click', async () => {
    testOut.textContent = '测试中…';
    try {
      const r = await api('/api/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: baseUrl.value.trim(), api_key: apiKey.value, model: name.value.trim(),
        }),
      });
      if (r.ok) {
        testOut.textContent = `连接成功（${r.via}）`
          + (r.models ? `：${r.count} 个模型 ${r.models.slice(0, 8).join(', ')}` : '');
      } else {
        testOut.textContent = '连接失败：' + (r.error || 'unknown');
      }
    } catch (e) {
      testOut.textContent = '测试失败：' + e.message;
    }
  });

  const judgeTestOut = el('div', { class: 'hint' });
  const judgeTestBtn = el('button', { class: 'btn ghost' }, '测试裁判');
  judgeTestBtn.addEventListener('click', async () => {
    judgeTestOut.textContent = '测试中…';
    try {
      const r = await api('/api/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: judgeBase.value.trim() || baseUrl.value.trim(),
          api_key: judgeKey.value || apiKey.value,
          model: judgeModel.value.trim() || name.value.trim(),
        }),
      });
      if (r.ok) {
        judgeTestOut.textContent = `连接成功（${r.via}）`
          + (r.models ? `：${r.count} 个模型 ${r.models.slice(0, 8).join(', ')}` : '');
      } else {
        judgeTestOut.textContent = '连接失败：' + (r.error || 'unknown');
      }
    } catch (e) {
      judgeTestOut.textContent = '测试失败：' + e.message;
    }
  });

  root.append(el('div', { class: 'card' },
    el('div', { class: 'section-head' }, el('h2', {}, '模型服务'),
      el('div', { class: 'hint' }, 'OpenAI 兼容接口（Ollama / vLLM / LM Studio / llama.cpp）')),
    el('div', { class: 'settings-grid' },
      el('label', {}, 'API Base URL'), baseUrl,
      el('label', {}, '模型名称'), name,
      el('label', {}, 'API Key'), apiKey,
      el('label', {}, 'temperature'), temperature,
      el('label', {}, 'max_tokens'), maxTokens,
      el('label', {}, 'timeout(s)'), timeout),
    el('div', { class: 'q-block' }, testBtn),
    testOut));

  root.append(el('div', { class: 'card' },
    el('div', { class: 'section-head' }, el('h2', {}, '主观题裁判'),
      el('div', { class: 'hint' }, '可单独指定 base_url / 模型 / key；留空则跟随被测模型')),
    el('div', { class: 'settings-grid' },
      el('label', {}, '启用裁判'), el('label', {}, judgeEnabled, ' 开'),
      el('label', {}, '双向判分'), el('label', {}, judgeDebias, ' rubric 正反序各判一次'),
      el('label', {}, '裁判 Base URL'), judgeBase,
      el('label', {}, '裁判 API Key'), judgeKey,
      el('label', {}, '裁判模型'), judgeModel,
      el('label', {}, '裁判 temperature'), judgeTemp),
    el('div', { class: 'q-block' }, judgeTestBtn),
    judgeTestOut));

  root.append(el('div', { class: 'card' },
    el('div', { class: 'section-head' }, el('h2', {}, '运行参数')),
    el('div', { class: 'settings-grid' },
      el('label', {}, '并发数'), concurrency,
      el('label', {}, '代码题采样数'), codeSamples,
      el('label', {}, '随机抽样/阶段'), sample,
      el('label', {}, '随机种子'), seed,
      el('label', {}, '执行模型代码'), el('label', {}, allowCode, ' 允许（仅可信环境）'))));

  const weightCard = el('div', { class: 'card' },
    el('div', { class: 'section-head' }, el('h2', {}, '权重预设')),
    el('div', { class: 'settings-grid' }, el('label', {}, '默认预设'), preset));
  for (const pname of Object.keys(presetWraps)) weightCard.append(presetWraps[pname]);
  weightCard.append(roleWrap);
  root.append(weightCard);

  root.append(el('div', { class: 'card' }, saveBtn, ' ', err, info));
}

/* ------------------------------------------------------------- compare */
function pct(v) {
  return (typeof v === 'number') ? `${v.toFixed(1)}%` : '-';
}

function compareMatrix(rows, labelKey, headerLabel, runs) {
  const head = el('tr', {}, el('th', {}, headerLabel),
    ...runs.map(r => el('th', {}, r.model || r.id)));
  const tb = el('tbody');
  for (const row of rows) {
    tb.append(el('tr', {},
      el('td', {}, row[labelKey]),
      ...runs.map(r => el('td', {}, pct(row.values[r.id])))
    ));
  }
  return el('table', { class: 'grid' }, el('thead', {}, head), tb);
}

function compareOverallTable(runs) {
  const tb = el('tbody');
  for (const r of runs) {
    tb.append(el('tr', {},
      el('td', {}, r.id),
      el('td', {}, r.model || '-'),
      el('td', {}, pct(r.weighted_percent)),
      el('td', {}, pct(r.percent)),
      el('td', {}, r.grade ? `${r.grade.letter} · ${r.grade.label}` : '-'),
      el('td', {}, r.coverage == null ? '-' : `${Math.round(r.coverage * 100)}%`)
    ));
  }
  return el('table', { class: 'grid' },
    el('thead', {}, el('tr', {},
      el('th', {}, '运行'), el('th', {}, '模型'), el('th', {}, '加权分'),
      el('th', {}, '原始得分率'), el('th', {}, '等级'), el('th', {}, '覆盖率')
    )), tb);
}

function itemStatsTable(stats) {
  const tb = el('tbody');
  for (const it of stats.items) {
    tb.append(el('tr', {},
      el('td', {}, it.id),
      el('td', {}, it.stage || ''),
      el('td', {}, it.p_value == null ? '-' : it.p_value.toFixed(3)),
      el('td', {}, it.discrimination == null ? '-' : it.discrimination.toFixed(3)),
      el('td', {}, String(it.n_runs)),
      el('td', {}, (it.flags || []).join('、'))
    ));
  }
  return el('table', { class: 'grid' },
    el('thead', {}, el('tr', {},
      el('th', {}, '题目'), el('th', {}, '阶段'), el('th', {}, '难度 p（越高越易）'),
      el('th', {}, '区分度'), el('th', {}, '运行数'), el('th', {}, '标记')
    )), tb);
}

function calibrationTable(cal) {
  const tb = el('tbody');
  for (const [d, v] of Object.entries(cal || {})) {
    tb.append(el('tr', {},
      el('td', {}, DIFF_LABEL[d] || d),
      el('td', {}, String(v.n)),
      el('td', {}, v.mean_p == null ? '-' : v.mean_p.toFixed(3))
    ));
  }
  return el('table', { class: 'grid' },
    el('thead', {}, el('tr', {},
      el('th', {}, '标注难度'), el('th', {}, '题数'), el('th', {}, '平均 p 值')
    )), tb);
}

function renderCompare() {
  const root = document.getElementById('view-compare');
  root.textContent = '';
  const doneRuns = (state.runs || []).filter(r => r.status === 'done');
  if (doneRuns.length < 2) {
    root.append(el('div', { class: 'empty' }, '至少需要 2 次已完成的运行才能对比。'));
    return;
  }
  const pick = el('div', { class: 'compare-pick' });
  doneRuns.forEach(r => {
    const cb = el('input', { type: 'checkbox', value: r.id });
    cb.checked = state.compareIds.length ? state.compareIds.includes(r.id) : true;
    pick.append(el('label', {}, cb, ` ${r.model || r.id} · ${r.id}`));
  });
  const out = el('div');
  const btn = el('button', { class: 'btn' }, '对比所选');
  btn.addEventListener('click', async () => {
    const ids = [...pick.querySelectorAll('input:checked')].map(x => x.value);
    if (ids.length < 2) { out.textContent = '至少选择 2 个运行'; return; }
    state.compareIds = ids;
    out.textContent = '对比中…';
    try {
      const res = await api('/api/compare?ids=' + encodeURIComponent(ids.join(',')));
      out.textContent = '';
      out.append(el('div', { class: 'card' }, el('h2', {}, '总览'), compareOverallTable(res.runs)));
      out.append(el('div', { class: 'card' }, el('h2', {}, '阶段对比'),
        compareMatrix(res.stages, 'name', '阶段', res.runs)));
      out.append(el('div', { class: 'card' }, el('h2', {}, '能力对比'),
        compareMatrix(res.capabilities, 'capability', '能力', res.runs)));
      const st = res.stats;
      out.append(el('div', { class: 'card' },
        el('h2', {}, '题目统计（跨模型）'),
        el('div', { class: 'hint' },
          `区分度需 ≥ ${st.min_runs_for_discrimination} 次运行；共 ${st.items.length} 题，` +
          `低区分度 ${st.low_discrimination.length} 题，难度极端 ${st.extreme_difficulty.length} 题。`),
        itemStatsTable(st)));
      out.append(el('div', { class: 'card' }, el('h2', {}, '难度校准（标注 vs 实测）'),
        calibrationTable(st.calibration)));
    } catch (e) {
      out.textContent = '对比失败：' + e.message;
    }
  });
  root.append(el('div', { class: 'card' },
    el('h2', {}, '多模型对比'),
    el('div', { class: 'hint' }, '选择 ≥2 次运行，比较阶段/能力分数，并计算跨模型题目区分度与难度。'),
    pick,
    el('div', { class: 'q-block' }, btn),
    out
  ));
}

/* ------------------------------------------------------------------ go */
init();
