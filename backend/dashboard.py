import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

from backend.agent_art import (
    ACTIVE_SPRITE_B64,
    IDLE_SPRITE_B64,
    SPRITE_NAMES,
)
from backend.branding import CLIENT_NAME, INTERNAL_NAME
from backend.company_day import start_company_day_background, workday_state
from backend.emailer import daily_send_cap, email_sending_enabled
from backend.storage import connect, init_db
from backend.trading_stats import all_trader_stats


HOST = "127.0.0.1"
PORT = 8765
IDLE_SPRITE = base64.b64decode(IDLE_SPRITE_B64)
ACTIVE_SPRITE = base64.b64decode(ACTIVE_SPRITE_B64)


PAGE = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hosko's Shady Shenanigans — Mission Control</title>
<style>
:root{
  --bg:#07050b;--bg2:#0d0912;--panel:#120d19;--panel2:#171020;
  --line:#2d2038;--line2:#473052;--text:#f7f1e8;--muted:#9e91a9;
  --orange:#ff6a00;--acid:#b7ff4a;--cyan:#54d6ff;--pink:#ff4fa3;
  --warn:#ffd166;--danger:#ff5d5d;--good:#7dff87;
  --display:"Arial Black","Segoe UI Black",Impact,sans-serif;
  --mono:"Cascadia Code","SFMono-Regular",Consolas,"Liberation Mono",monospace;
  --body:"Segoe UI Variable","Segoe UI",Inter,system-ui,sans-serif;
}
*{box-sizing:border-box}
body{
  margin:0;color:var(--text);font:14px/1.48 var(--body);
  background:
    radial-gradient(circle at 15% -10%,rgba(255,106,0,.12),transparent 26rem),
    radial-gradient(circle at 88% 0%,rgba(84,214,255,.08),transparent 24rem),
    linear-gradient(180deg,#07050b,#0a0710 45%,#050408);
}
body:before{
  content:"";position:fixed;inset:0;pointer-events:none;opacity:.16;
  background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(255,255,255,.025) 4px);
}
header{
  position:sticky;top:0;z-index:20;display:flex;align-items:center;justify-content:space-between;
  gap:18px;padding:14px 22px;background:rgba(8,6,12,.93);backdrop-filter:blur(16px);
  border-bottom:1px solid var(--line2);box-shadow:0 14px 34px rgba(0,0,0,.3)
}
.brand-wrap{display:flex;align-items:center;gap:13px;min-width:0}
.hss-mark{
  width:47px;height:47px;border-radius:13px;display:grid;place-items:center;
  font:900 16px/1 var(--mono);letter-spacing:-.08em;color:var(--text);
  background:linear-gradient(145deg,#1a111f,#09070d);
  border:1px solid var(--orange);box-shadow:0 0 30px rgba(255,106,0,.17),inset 0 0 18px rgba(255,106,0,.08)
}
.hss-mark span{color:var(--acid)}
.brand-title{font:900 clamp(17px,2.1vw,25px)/1 var(--display);letter-spacing:.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.brand-sub{margin-top:4px;color:var(--muted);font:10px/1.2 var(--mono);letter-spacing:.11em;text-transform:uppercase}
.header-actions{display:flex;align-items:center;gap:10px}
.front-badge{font:700 10px/1 var(--mono);color:var(--cyan);border:1px solid #204857;background:#0a171b;padding:9px 11px;border-radius:10px;white-space:nowrap}
.run{
  min-width:96px;border:1px solid #ff8b36;border-radius:11px;padding:11px 18px;
  background:linear-gradient(180deg,#ff7b19,#e65300);color:#100805;
  font:1000 14px/1 var(--mono);letter-spacing:.18em;cursor:pointer;
  box-shadow:0 0 28px rgba(255,106,0,.2)
}
.run:hover:not(:disabled){filter:brightness(1.14);transform:translateY(-1px)}
.run:disabled{cursor:not-allowed;color:#13220c;background:linear-gradient(180deg,#b7ff4a,#70c92f);border-color:#b7ff4a}
main{max-width:1540px;margin:auto;padding:20px}
.panel{
  background:linear-gradient(180deg,rgba(21,14,28,.95),rgba(14,10,19,.95));
  border:1px solid var(--line);border-radius:18px;padding:17px;margin-bottom:16px;
  box-shadow:0 16px 46px rgba(0,0,0,.18)
}
.panel-head{display:flex;justify-content:space-between;align-items:flex-end;gap:14px;margin-bottom:12px}
h2{margin:0;font:900 12px/1 var(--mono);text-transform:uppercase;letter-spacing:.15em;color:#d7cce0}
.kicker{color:var(--muted);font-size:11px;margin-top:5px}
.metrics,.agents{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.active-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.metric,.agent,.active-card{
  background:linear-gradient(145deg,#100b16,#0c0910);border:1px solid var(--line);
  border-radius:14px;padding:12px
}
.metric b{display:block;font:900 22px/1.2 var(--mono);margin-top:5px;color:#fff}
.metric span,.small{color:var(--muted);font-size:11px}
.name{font:900 14px/1 var(--mono);letter-spacing:.05em}
.role{color:var(--muted);font-size:10px;margin-top:4px}
.status{
  display:inline-block;margin-top:7px;padding:4px 7px;border-radius:999px;
  background:#1c1424;color:var(--cyan);font:800 9px/1 var(--mono);letter-spacing:.08em
}
.agent{position:relative;overflow:hidden;transition:.18s transform,.18s border-color,.18s box-shadow}
.agent:hover{transform:translateY(-2px);border-color:#50375d}
.agent.working{border-color:#6bcf62;box-shadow:0 0 0 1px rgba(183,255,74,.11),0 0 32px rgba(183,255,74,.08)}
.agent.working:before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--acid)}
.agent.waiting{border-color:#8d6c25}.agent.off{opacity:.58}
.agent-top{display:flex;align-items:center;gap:12px}.agent-meta{min-width:0}
.agent-sprite{
  flex:0 0 72px;width:72px;height:72px;border-radius:13px;position:relative;overflow:hidden;
  background-image:url('/assets/agents-idle.webp');background-repeat:no-repeat;
  background-size:936px 72px;background-position:var(--sprite-x) 0;
  image-rendering:auto;border:1px solid #3b2a46;background-color:#08060b;
  box-shadow:inset 0 0 16px rgba(0,0,0,.45)
}
.agent-sprite:after{
  content:"";position:absolute;inset:0;background-image:url('/assets/agents-active.webp');
  background-repeat:no-repeat;background-size:936px 72px;background-position:var(--sprite-x) 0;
  opacity:0
}
.agent.working .agent-sprite:after,.active-card .agent-sprite:after{animation:workFrame .78s steps(1,end) infinite}
@keyframes workFrame{0%,48%{opacity:0}49%,100%{opacity:1}}
.working-badge{
  display:inline-flex;align-items:center;gap:6px;margin-top:8px;color:var(--acid);
  font:900 9px/1 var(--mono);letter-spacing:.12em
}
.working-badge:before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 13px currentColor}
.now-label{font:800 9px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:#745f7e;margin-top:11px}
.action{font-size:12px;margin-top:4px;min-height:36px}
.agent-quips{color:#816f8b;font-size:10px;margin-top:8px;font-style:italic}
.active-card{display:flex;gap:10px;align-items:center;border-color:#3d5232}
.active-card .agent-sprite{width:58px;height:58px;flex-basis:58px;background-size:754px 58px}
.active-card .agent-sprite:after{background-size:754px 58px}
.active-card strong{display:block;font:800 11px/1.2 var(--mono)}
.good{color:var(--good)}.warn{color:var(--warn)}.danger{color:var(--danger)}a{color:var(--cyan)}
table{width:100%;border-collapse:collapse;font-size:12px}
td,th{padding:8px;border-bottom:1px solid #24192d;text-align:left;vertical-align:top}
th{color:#8f8099;font:800 10px/1.2 var(--mono);letter-spacing:.05em}
.scroll{overflow:auto}
.notice{padding:10px 12px;border:1px solid #3b2b46;border-radius:11px;background:#0d0912;color:#b3a7bd;font-size:11px}
#runResult{min-height:15px;color:var(--muted);font:10px/1.2 var(--mono)}
@media(max-width:1120px){.metrics,.agents{grid-template-columns:repeat(3,1fr)}.front-badge{display:none}}
@media(max-width:900px){.metrics,.agents,.active-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:620px){.metrics,.agents,.active-grid{grid-template-columns:1fr}.brand-sub{display:none}.brand-title{white-space:normal}.header-actions{align-self:stretch;justify-content:flex-end}header{align-items:flex-start}.agent-sprite{width:64px;height:64px;flex-basis:64px;background-size:832px 64px}.agent-sprite:after{background-size:832px 64px}}
</style>
</head>
<body>
<header>
  <div class="brand-wrap">
    <div class="hss-mark">H<span>SS</span></div>
    <div>
      <div class="brand-title">Hosko’s Shady Shenanigans</div>
      <div class="brand-sub">Mission Control · questionable name · deterministic guardrails</div>
    </div>
  </div>
  <div class="header-actions">
    <div class="front-badge">CLIENT FRONT // SHENANIGAN SYSTEMS</div>
    <div><button class="run" id="runButton" onclick="runDay()">RUN</button><div id="runResult"></div></div>
  </div>
</header>
<main>
<section class="panel">
  <div class="panel-head"><div><h2>Company pulse</h2><div class="kicker">One button wakes the whole circus for six hours.</div></div></div>
  <div class="metrics" id="metrics"></div>
</section>
<section class="panel">
  <div class="panel-head"><div><h2>Who's actually doing something</h2><div class="kicker">Green = working. Amber = waiting/blocking. Grey = pretending this is a normal company.</div></div></div>
  <div class="active-grid" id="activeAgents"></div>
</section>
<section class="panel">
  <div class="panel-head"><div><h2>Agent floor</h2><div class="kicker">Your characters. Idle frame when resting; the two supplied frames alternate while working.</div></div></div>
  <div class="agents" id="agents"></div>
</section>
<section class="panel">
  <div class="panel-head"><div><h2>Website studio</h2><div class="kicker">Client-facing brand: Shenanigan Systems. Sentinel flags trigger safe-mode repair, not a dead project.</div></div></div>
  <div id="website"></div>
</section>
<section class="panel">
  <div class="panel-head"><div><h2>Trading desk — paper only</h2><div class="kicker">Six-hour shift · live market observations · fake fills · real-money execution disabled.</div></div></div>
  <div class="metrics" id="shift"></div><div class="metrics" id="stats" style="margin-top:10px"></div><div id="trades"></div><div id="signals"></div>
</section>
<section class="panel">
  <div class="panel-head"><div><h2>Sales pipeline</h2><div class="kicker">Mercury's food supply.</div></div></div>
  <div class="scroll" id="pipeline"></div>
</section>
</main>
<script>
function esc(v){v=(v==null?'':String(v));return v.replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]})}
function metric(k,v){return '<div class="metric"><span>'+esc(k)+'</span><b>'+esc(v)+'</b></div>'}
const spriteIndex={Atlas:0,Mercury:1,Forge:2,Freya:3,Nova:4,Satoshi:5,Midas:6,Oracle:7,Ledger:8,Sentinel:9,Raptor:10,Apex:11,Circuit:12};
const quips={
 Atlas:'Capital allocator. Allergic to vibes without margin.',
 Mercury:'Sales fox. Would monetize the apocalypse, politely.',
 Forge:'Builds it. Breaks it. Builds it again with better spacing.',
 Freya:'Partnerships, cash, and absolutely no networking breakfast.',
 Nova:'Conversion rocket. May improve funnel and self-esteem.',
 Satoshi:'Automates repetitive work before it becomes sentient enough to complain.',
 Midas:'Makes pixels look expensive while Ledger screams quietly.',
 Oracle:'Reads the internet so the rest can form opinions irresponsibly.',
 Ledger:'Keeps bankruptcy hypothetical and receipts annoyingly real.',
 Sentinel:'Kills bad ideas. The good ones merely leave wounded.',
 Raptor:'Stares at meme candles until probability blinks first.',
 Apex:'Stock shark with paper teeth until qualification says otherwise.',
 Circuit:'Risk is not optional. The sign is lying.'
};
function stateClass(status){
 const x=String(status||'').toUpperCase();
 if(x.includes('WORKING')||x.includes('ON_SHIFT')||x.includes('RUNNING')) return 'working';
 if(x.includes('WAITING')||x.includes('NEEDED')||x.includes('BLOCKED')) return 'waiting';
 if(x.includes('OFF')||x.includes('STOPPED')) return 'off';
 return 'ready';
}
function sprite(agent,size){
 const idx=spriteIndex[agent]??0;
 const tile=size||72;
 return '<div class="agent-sprite" style="--sprite-x:-'+(idx*tile)+'px"></div>';
}
function agentCard(a){
 const cls=stateClass(a.status);
 const badge=cls==='working'?'<span class="working-badge">WORKING</span>':'<span class="status">'+esc(a.status)+'</span>';
 return '<div class="agent '+cls+'"><div class="agent-top">'+sprite(a.agent,72)+'<div class="agent-meta"><div class="name">'+esc(a.agent)+'</div><div class="role">'+esc(a.title)+'</div>'+badge+'</div></div><div class="now-label">Current assignment</div><div class="action">'+esc(a.last_action||'Nothing assigned')+'</div><div class="agent-quips">'+esc(quips[a.agent]||'Still waiting for a sufficiently cursed backstory.')+'</div><div class="small">confidence '+esc(a.confidence)+' · stress '+esc(a.stress)+' · motivation '+esc(a.motivation)+'</div></div>';
}
async function runDay(){
 const button=document.getElementById('runButton'), msg=document.getElementById('runResult');
 button.disabled=true;button.textContent='STARTING';msg.textContent='Waking the gremlins…';
 try{
   const r=await fetch('/api/run',{method:'POST'});
   const d=await r.json();
   msg.textContent=d.started?'6-hour workday started.':(d.reason||'Already running.');
 }catch(e){msg.textContent='Start failed: '+e;button.disabled=false;button.textContent='RUN'}
 setTimeout(refresh,800);
}
async function refresh(){
 try{
  const r=await fetch('/api/state',{cache:'no-store'}), d=await r.json(), m=d.metrics, company=d.company_day||{};
  const button=document.getElementById('runButton');
  button.disabled=!!company.active;button.textContent=company.active?'RUNNING':'RUN';
  document.getElementById('metrics').innerHTML=
    metric('Company day',company.active?'RUNNING':'IDLE')+
    metric('Prospects',m.total_prospects)+
    metric('Outreach',m.outreach_sent)+
    metric('Paper P&L USD',Number(m.paper_pnl||0).toFixed(2))+
    metric('Open paper trades',m.open_paper_trades||0);

  const working=d.agents.filter(function(a){const c=stateClass(a.status);return c==='working'||c==='waiting'});
  document.getElementById('activeAgents').innerHTML=working.length?working.map(function(a){
    return '<div class="active-card '+stateClass(a.status)+'">'+sprite(a.agent,58)+'<div><strong>'+esc(a.agent)+' · '+esc(a.status)+'</strong><div class="small">'+esc(a.last_action||'Nothing assigned')+'</div></div></div>';
  }).join(''):'<div class="notice">Nobody is actively working. Either the shift is over or Atlas found a tax-deductible nap.</div>';
  document.getElementById('agents').innerHTML=d.agents.map(agentCard).join('');

  const wp=d.website_project;
  if(wp){
    const ev=d.website_events.map(e=>'<tr><td>'+esc(e.agent)+'</td><td>'+esc(e.stage)+'</td><td>'+esc(e.detail)+'</td></tr>').join('');
    const wl=d.website_leads.map(x=>'<tr><td>'+esc(x.name)+'</td><td>'+esc(x.email)+'</td><td>'+esc(x.interest)+'</td><td>'+esc(x.status)+'</td></tr>').join('');
    const cq=d.website_client_questions.map(q=>'<tr><td>'+esc(q.required_for)+'</td><td>'+esc(q.question)+'</td><td>'+esc(q.status)+'</td><td>'+esc(q.answer||'-')+'</td></tr>').join('');
    const preview=wp.preview_url?'<a href="'+esc(wp.preview_url)+'" target="_blank" rel="noopener">Open staging preview ↗</a>':'Preview not started';
    document.getElementById('website').innerHTML=
      '<div class="metric"><span>'+esc(wp.business_name)+' · '+esc(wp.mode)+'</span><b>'+esc(wp.status)+'</b>'+
      '<div class="small">Build $'+Number(wp.quoted_price||0).toFixed(0)+' · care $'+Number(wp.monthly_price||0).toFixed(0)+'/mo · revisions '+esc(wp.revision_rounds_used||0)+'/2 · approval '+esc(wp.customer_approval_status||'PENDING')+' · client images '+esc(d.website_asset_count||0)+' · delivery '+esc(wp.delivery_email_status||'NOT SENT')+' · '+preview+'</div></div>'+
      '<h2 style="margin-top:18px">Client brief / launch gates</h2><div class="scroll"><table><thead><tr><th>Gate</th><th>Question</th><th>Status</th><th>Answer</th></tr></thead><tbody>'+cq+'</tbody></table></div>'+
      '<h2 style="margin-top:18px">Project events</h2><div class="scroll"><table><thead><tr><th>Agent</th><th>Stage</th><th>Detail</th></tr></thead><tbody>'+ev+'</tbody></table></div>'+
      '<h2 style="margin-top:18px">Staging enquiries</h2><div class="scroll"><table><thead><tr><th>Name</th><th>Email</th><th>Interest</th><th>Status</th></tr></thead><tbody>'+wl+'</tbody></table></div>';
  }else document.getElementById('website').innerHTML='<div class="notice">No website project yet. Suspiciously peaceful.</div>';

  const ts=d.trading_session||{};
  document.getElementById('shift').innerHTML=metric('Shift',ts.status||'IDLE')+metric('Stress',ts.stress_level==null?'-':String(ts.stress_level)+'/4')+metric('Defensive',Number(ts.defensive_mode||0)?'YES':'NO')+metric('Cycles',ts.cycles_completed||0)+metric('Model calls',ts.model_calls_used||0);
  document.getElementById('stats').innerHTML=d.trader_stats.map(function(x){
    const pf=x.profit_factor==null?'∞':Number(x.profit_factor).toFixed(2);
    return '<div class="metric"><span>'+esc(x.agent)+' '+esc(x.asset_class)+'</span><b>$'+Number(x.net_pnl||0).toFixed(2)+'</b><div class="small">closed '+esc(x.closed_trades)+' · win '+Number(x.win_rate||0).toFixed(1)+'% · PF '+esc(pf)+' · expectancy '+Number(x.expectancy_r||0).toFixed(2)+'R · '+esc(x.paper_verdict)+'</div></div>';
  }).join('');
  const tr=d.trades.map(function(t){const rr=(Number(t.initial_risk_usd||0)>0&&t.status!=='OPEN')?(Number(t.pnl_usd||0)/Number(t.initial_risk_usd)).toFixed(2)+'R':'-';return '<tr><td>'+esc(t.asset_class)+'</td><td>'+esc(t.symbol)+'</td><td>'+esc(t.trade_mode||'-')+'</td><td>'+esc(t.setup_score==null?'-':t.setup_score)+'</td><td>'+esc(t.status)+'</td><td>$'+Number(t.notional_usd||0).toFixed(2)+'</td><td>'+rr+'</td><td>$'+Number(t.pnl_usd||0).toFixed(2)+'</td></tr>'}).join('');
  document.getElementById('trades').innerHTML='<h2 style="margin-top:18px">Paper trades</h2><div class="scroll"><table><thead><tr><th>Class</th><th>Symbol</th><th>Mode</th><th>Score</th><th>Status</th><th>Notional</th><th>R</th><th>Net P&L</th></tr></thead><tbody>'+tr+'</tbody></table></div>';
  const sg=d.trade_signals.map(x=>'<tr><td>'+esc(x.agent)+'</td><td>'+esc(x.symbol)+'</td><td>'+esc(x.action)+'</td><td>'+esc(x.trade_mode||'-')+'</td><td>'+esc(x.setup_score==null?'-':x.setup_score)+'</td><td>'+esc(x.stress_level==null?'-':x.stress_level)+'/4</td><td>'+Number(x.expected_round_trip_cost_pct||0).toFixed(2)+'%</td><td>'+esc(x.thesis||'')+'</td></tr>').join('');
  document.getElementById('signals').innerHTML='<h2 style="margin-top:18px">Latest signals</h2><div class="scroll"><table><thead><tr><th>Agent</th><th>Symbol</th><th>Action</th><th>Mode</th><th>Score</th><th>Stress</th><th>Cost</th><th>Why</th></tr></thead><tbody>'+sg+'</tbody></table></div>';
  const pr=d.prospects.map(p=>'<tr><td>'+esc(p.business_name)+'</td><td>'+esc(p.city)+'</td><td>'+esc(p.category)+'</td><td>'+esc(p.sales_score==null?'-':p.sales_score)+'</td><td>'+esc(p.status)+'</td></tr>').join('');
  document.getElementById('pipeline').innerHTML='<table><thead><tr><th>Business</th><th>Market</th><th>Category</th><th>Score</th><th>Status</th></tr></thead><tbody>'+pr+'</tbody></table>';
 }catch(e){document.getElementById('runResult').textContent='Refresh error: '+e}
}
refresh();setInterval(refresh,2000);
</script>
</body>
</html>'''


def state_payload():
    conn = connect()
    init_db(conn)
    agents = [
        dict(r)
        for r in conn.execute(
            """SELECT agent,title,status,last_action,confidence,stress,motivation,job_security,updated_at
            FROM agent_state
            ORDER BY CASE agent
            WHEN 'Atlas' THEN 1 WHEN 'Mercury' THEN 2 WHEN 'Forge' THEN 3
            WHEN 'Freya' THEN 4 WHEN 'Nova' THEN 5 WHEN 'Satoshi' THEN 6
            WHEN 'Midas' THEN 7 WHEN 'Oracle' THEN 8 WHEN 'Ledger' THEN 9
            WHEN 'Sentinel' THEN 10 WHEN 'Raptor' THEN 11 WHEN 'Apex' THEN 12
            WHEN 'Circuit' THEN 13 ELSE 99 END"""
        ).fetchall()
    ]
    pipeline = conn.execute(
        """SELECT COUNT(*) total,
        SUM(CASE WHEN status='DRAFT_READY' THEN 1 ELSE 0 END) draft_ready,
        SUM(CASE WHEN status='CONTACT_READY' THEN 1 ELSE 0 END) contact_ready,
        SUM(CASE WHEN status='OUTREACH_SENT' THEN 1 ELSE 0 END) outreach_sent
        FROM prospects"""
    ).fetchone()
    session = conn.execute("SELECT * FROM work_sessions ORDER BY id DESC LIMIT 1").fetchone()
    trading_row = conn.execute("SELECT * FROM trading_sessions ORDER BY id DESC LIMIT 1").fetchone()
    trading_session = dict(trading_row) if trading_row else None
    summary = conn.execute(
        """SELECT SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) open_count,
        COALESCE(SUM(CASE WHEN status!='OPEN' THEN pnl_usd ELSE 0 END),0) realized_pnl
        FROM paper_trades"""
    ).fetchone()
    trades = [
        dict(r)
        for r in conn.execute(
            """SELECT asset_class,symbol,status,notional_usd,entry_price,exit_price,fees_usd,pnl_usd,
            opened_at,closed_at,trade_mode,setup_score,stress_level,initial_risk_usd
            FROM paper_trades ORDER BY id DESC LIMIT 20"""
        ).fetchall()
    ]
    signals = [
        dict(r)
        for r in conn.execute(
            """SELECT agent,asset_class,symbol,action,confidence,thesis,risk_decision,created_at,
            trade_mode,setup_score,stress_level,signals_json,expected_round_trip_cost_pct,
            expected_first_move_pct,market_source
            FROM trade_signals ORDER BY id DESC LIMIT 20"""
        ).fetchall()
    ]
    prospects = [
        dict(r)
        for r in conn.execute(
            """SELECT business_name,city,category,sales_score,status,contact_email
            FROM prospects ORDER BY id DESC LIMIT 20"""
        ).fetchall()
    ]

    website_row = conn.execute("SELECT * FROM website_projects ORDER BY id DESC LIMIT 1").fetchone()
    website_project = dict(website_row) if website_row else None
    website_events, website_leads, website_client_questions = [], [], []
    website_lead_count = website_asset_count = 0
    if website_project:
        pid = website_project["id"]
        website_events = [dict(r) for r in conn.execute(
            """SELECT agent,stage,detail,created_at FROM website_project_events
            WHERE project_id=? ORDER BY id DESC LIMIT 16""",(pid,)
        ).fetchall()]
        website_leads = [dict(r) for r in conn.execute(
            """SELECT name,email,interest,status,created_at FROM website_leads
            WHERE project_id=? ORDER BY id DESC LIMIT 10""",(pid,)
        ).fetchall()]
        website_client_questions = [dict(r) for r in conn.execute(
            """SELECT question,required_for,answer,status,answered_at FROM website_client_questions
            WHERE project_id=? ORDER BY id""",(pid,)
        ).fetchall()]
        website_lead_count = int(conn.execute("SELECT COUNT(*) n FROM website_leads WHERE project_id=?",(pid,)).fetchone()["n"])
        website_asset_count = int(conn.execute("SELECT COUNT(*) n FROM website_client_assets WHERE project_id=?",(pid,)).fetchone()["n"])

    payload = {
        "brand": {"internal": INTERNAL_NAME, "client": CLIENT_NAME},
        "company_day": workday_state(),
        "metrics": {
            "workday_status": session["status"] if session else "IDLE",
            "total_prospects": int(pipeline["total"] or 0),
            "draft_ready": int(pipeline["draft_ready"] or 0),
            "contact_ready": int(pipeline["contact_ready"] or 0),
            "outreach_sent": int(pipeline["outreach_sent"] or 0),
            "paper_pnl": float(summary["realized_pnl"] or 0),
            "open_paper_trades": int(summary["open_count"] or 0),
            "email_enabled": email_sending_enabled(),
            "daily_cap": daily_send_cap(),
        },
        "agents": agents,
        "prospects": prospects,
        "trades": trades,
        "trade_signals": signals,
        "trader_stats": all_trader_stats(conn),
        "trading_session": trading_session,
        "website_project": website_project,
        "website_events": website_events,
        "website_leads": website_leads,
        "website_lead_count": website_lead_count,
        "website_client_questions": website_client_questions,
        "website_asset_count": website_asset_count,
    }
    conn.close()
    return payload


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _asset(self, payload: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "image/webp")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/assets/agents-idle.webp":
            self._asset(IDLE_SPRITE)
            return
        if self.path == "/assets/agents-active.webp":
            self._asset(ACTIVE_SPRITE)
            return
        if self.path.startswith("/api/state"):
            self._json(200, state_payload())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/run":
            try:
                result = start_company_day_background(6.0)
                self._json(202 if result.get("started") else 409, result)
            except Exception as exc:
                self._json(500, {"started": False, "reason": str(exc)})
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def main():
    load_dotenv()
    conn = connect()
    init_db(conn)
    conn.close()
    print(f"\n=== {INTERNAL_NAME.upper()} — MISSION CONTROL ===")
    print(f"Client-facing brand: {CLIENT_NAME}")
    print(f"Live monitor: http://{HOST}:{PORT}")
    print("RUN button starts worker agents + paper trading desk for six hours.")
    print("No model calls are used by the dashboard itself.")
    print("Press Ctrl+C to stop the monitor.\n")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMission Control stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
