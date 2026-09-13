import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

from backend.agent_art import ACTIVE_SPRITE_B64, IDLE_SPRITE_B64, SPRITE_NAMES
from backend.branding import INTERNAL_NAME
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
<title>Hosko's Shady Shenanigans</title>
<style>
:root{
  --bg:#08060c;--bg2:#0e0a14;--panel:#15101d;--panel2:#1b1425;
  --line:#332541;--text:#f6f0e8;--muted:#a79bb4;--lime:#b7ff4a;
  --orange:#ff6a00;--pink:#ff4fa3;--cyan:#5ce1e6;--red:#ff4d57;
}
*{box-sizing:border-box}
body{margin:0;background:
 radial-gradient(circle at 12% 0%,rgba(255,106,0,.09),transparent 30%),
 radial-gradient(circle at 88% 4%,rgba(183,255,74,.06),transparent 28%),
 linear-gradient(180deg,var(--bg),#050407 72%);color:var(--text);
 font:14px/1.5 "Segoe UI Variable","Segoe UI",system-ui,sans-serif;min-height:100vh}
header{position:sticky;top:0;z-index:30;background:rgba(8,6,12,.94);backdrop-filter:blur(14px);
 border-bottom:1px solid var(--line);padding:14px 22px;display:flex;align-items:center;justify-content:space-between;gap:18px}
.brand-wrap{display:flex;align-items:center;gap:13px}.hss-mark{width:48px;height:48px;border:1px solid var(--orange);
 border-radius:14px;display:grid;place-items:center;background:linear-gradient(145deg,#201329,#0b0910);
 box-shadow:0 0 28px rgba(255,106,0,.18);font:1000 17px/1 ui-monospace,Consolas,monospace}
.hss-mark b{color:var(--lime)}.brand{font:900 19px/1.08 "Segoe UI Variable Display","Arial Black",sans-serif;letter-spacing:.025em}
.subtitle{color:var(--muted);font:700 10px/1.3 ui-monospace,Consolas,monospace;letter-spacing:.13em;text-transform:uppercase;margin-top:5px}
.run-wrap{display:flex;align-items:center;gap:12px}.run-state{color:var(--muted);font:700 11px ui-monospace,Consolas,monospace}
.run-btn{appearance:none;border:0;border-radius:13px;padding:13px 25px;background:var(--lime);color:#111;
 font:1000 15px ui-monospace,Consolas,monospace;letter-spacing:.1em;cursor:pointer;box-shadow:0 0 24px rgba(183,255,74,.18)}
.run-btn:hover{transform:translateY(-1px);box-shadow:0 0 34px rgba(183,255,74,.28)}
.run-btn:disabled{background:#332e38;color:#817886;box-shadow:none;cursor:not-allowed;transform:none}
main{max-width:1560px;margin:auto;padding:20px}.panel{background:linear-gradient(145deg,rgba(24,17,32,.94),rgba(15,11,21,.94));
 border:1px solid var(--line);border-radius:18px;padding:17px;margin-bottom:16px;box-shadow:0 18px 55px rgba(0,0,0,.22)}
.panel h2{margin:0 0 12px;font:900 12px ui-monospace,Consolas,monospace;letter-spacing:.15em;text-transform:uppercase;color:#d5cadd}
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.metric{background:#0f0b15;border:1px solid #2a2035;border-radius:13px;padding:13px}
.metric b{display:block;font:900 22px "Segoe UI Variable Display","Arial Black",sans-serif}.metric span,.small{color:var(--muted);font-size:11px}
.agents{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.agent{position:relative;overflow:hidden;background:#0e0a14;border:1px solid #2d2239;border-radius:16px;padding:12px;min-height:186px}
.agent.working{border-color:var(--lime);box-shadow:0 0 0 1px rgba(183,255,74,.13),0 0 32px rgba(183,255,74,.08)}
.agent.waiting{border-color:var(--orange)}.agent.off{opacity:.6}.agent.working:after{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--lime)}
.agent-top{display:flex;align-items:center;gap:12px}.portrait{width:92px;height:92px;flex:0 0 92px;background-image:url('/assets/agents-idle.webp');
 background-size:1196px 92px;background-position:var(--x) 0;background-repeat:no-repeat;image-rendering:pixelated;filter:drop-shadow(0 8px 14px rgba(0,0,0,.45))}
.agent.working .portrait{animation:characterWork 1.05s steps(1,end) infinite}
@keyframes characterWork{0%,49%{background-image:url('/assets/agents-idle.webp')}50%,100%{background-image:url('/assets/agents-active.webp')}}
.name{font:1000 16px "Segoe UI Variable Display","Arial Black",sans-serif}.role{color:var(--muted);font-size:10px;margin-top:2px}.status{display:inline-block;margin-top:7px;padding:4px 8px;border-radius:999px;background:#21182c;color:var(--cyan);font:800 9px ui-monospace,Consolas,monospace;letter-spacing:.08em}
.working-badge{display:inline-flex;align-items:center;gap:6px;color:var(--lime);font:900 9px ui-monospace,Consolas,monospace;letter-spacing:.1em;margin-top:7px}
.working-badge:before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 12px currentColor}
.now-label{margin-top:10px;color:#766b82;font:800 9px ui-monospace,Consolas,monospace;letter-spacing:.12em;text-transform:uppercase}.action{font-size:12px;margin-top:3px;min-height:34px}
.quip{color:#756a80;font-size:10px;font-style:italic;margin-top:6px}.active-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.active-card{display:flex;align-items:center;gap:10px;background:#0d0a12;border:1px solid #2d2239;border-radius:14px;padding:10px}.active-card .portrait{width:64px;height:64px;flex-basis:64px;background-size:832px 64px}
.active-card.working .portrait{animation:characterWorkSmall 1.05s steps(1,end) infinite}
@keyframes characterWorkSmall{0%,49%{background-image:url('/assets/agents-idle.webp')}50%,100%{background-image:url('/assets/agents-active.webp')}}
a{color:var(--lime)}table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:8px;border-bottom:1px solid #2b2136;text-align:left;vertical-align:top}th{color:var(--muted);font:800 10px ui-monospace,Consolas,monospace;text-transform:uppercase;letter-spacing:.08em}.scroll{overflow:auto}
.note{color:#8d8198;font-size:11px}.website-head{display:grid;grid-template-columns:1.3fr .7fr;gap:10px}
.pill{display:inline-block;padding:4px 8px;border:1px solid #3a2a48;border-radius:999px;color:#cabed5;font:700 10px ui-monospace,Consolas,monospace}
@media(max-width:1150px){.agents{grid-template-columns:repeat(3,1fr)}.metrics{grid-template-columns:repeat(3,1fr)}}
@media(max-width:850px){.agents,.active-grid{grid-template-columns:repeat(2,1fr)}.website-head{grid-template-columns:1fr}}
@media(max-width:560px){header{align-items:flex-start;flex-direction:column}.run-wrap{width:100%;justify-content:space-between}.agents,.active-grid,.metrics{grid-template-columns:1fr}.portrait{width:80px;height:80px;flex-basis:80px;background-size:1040px 80px}}
</style>
</head>
<body>
<header>
 <div class="brand-wrap"><div class="hss-mark">H<b>SS</b></div><div><div class="brand">Hosko’s Shady Shenanigans</div><div class="subtitle">Internal mission control · clients see Shenanigan Systems</div></div></div>
 <div class="run-wrap"><span class="run-state" id="runState">checking the basement...</span><button class="run-btn" id="runBtn" onclick="startDay()">RUN</button></div>
</header>
<main>
<section class="panel"><h2>Company pulse</h2><div class="metrics" id="metrics"></div></section>
<section class="panel"><h2>Currently committing shenanigans</h2><div class="note">Green = actually working. Orange = waiting/blocked. Animated character = alive and doing something questionable.</div><div class="active-grid" id="activeAgents" style="margin-top:11px"></div></section>
<section class="panel"><h2>Agent floor</h2><div class="agents" id="agents"></div></section>
<section class="panel"><h2>Website studio</h2><div class="note">Quote → brief → Forge → Nova → Sentinel → automatic repair/quarantine → staging → Shenanigan Systems email.</div><div id="website" style="margin-top:11px"></div></section>
<section class="panel"><h2>Trading desk · paper simulation</h2><div class="note">Six-hour shift. Live observations, fake fills, adaptive opportunity stress. Real-money execution remains disabled.</div><div class="metrics" id="shift" style="margin-top:11px"></div><div class="metrics" id="stats" style="margin-top:10px"></div><div id="trades"></div><div id="signals"></div></section>
<section class="panel"><h2>Sales pipeline</h2><div class="scroll" id="pipeline"></div></section>
</main>
<script>
const spriteOrder=['Atlas','Mercury','Forge','Freya','Nova','Satoshi','Midas','Oracle','Ledger','Sentinel','Raptor','Apex','Circuit'];
const quips={
 Atlas:'Capital allocation, now with 14% more existential dread.',
 Mercury:'Would sell umbrellas during a meteor strike.',
 Forge:'If it can be fixed with a hammer, it is now architecture.',
 Freya:'Partnerships, cash, and plausible deniability.',
 Nova:'Growth charts or emotional damage. Sometimes both.',
 Satoshi:'Run it again. Surely the bug learned its lesson.',
 Midas:'Turns questionable inputs into expensive-looking pixels.',
 Oracle:'Trust the data. Fear the spreadsheet.',
 Ledger:'Keeps bankruptcy in the simulation layer.',
 Sentinel:'Finds the bad idea, then buries it somewhere safe.',
 Raptor:'Stares at candles until one confesses.',
 Apex:'Paper teeth. Real shark energy.',
 Circuit:'Risk is not optional. Fun apparently is.'
};
function esc(v){v=(v==null?'':String(v));return v.replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
function metric(k,v){return '<div class="metric"><span>'+esc(k)+'</span><b>'+esc(v)+'</b></div>'}
function stateClass(status){const x=String(status||'').toUpperCase();if(x.includes('WORKING')||x.includes('ON_SHIFT'))return'working';if(x.includes('WAITING')||x.includes('NEEDED')||x.includes('BLOCKED'))return'waiting';if(x.includes('OFF')||x.includes('STOPPED'))return'off';return'ready'}
function portrait(name,small=false){const i=Math.max(0,spriteOrder.indexOf(name));const tile=small?64:92;return '<div class="portrait" style="--x:-'+(i*tile)+'px"></div>'}
function card(a){const cls=stateClass(a.status);const badge=cls==='working'?'<span class="working-badge">WORKING</span>':'<span class="status">'+esc(a.status)+'</span>';return '<div class="agent '+cls+'"><div class="agent-top">'+portrait(a.agent)+'<div><div class="name">'+esc(a.agent)+'</div><div class="role">'+esc(a.title)+'</div>'+badge+'</div></div><div class="now-label">Now doing</div><div class="action">'+esc(a.last_action||'Nothing assigned')+'</div><div class="quip">'+esc(quips[a.agent]||'Still awaiting a sufficiently dramatic backstory.')+'</div><div class="small">confidence '+esc(a.confidence)+' · stress '+esc(a.stress)+' · motivation '+esc(a.motivation)+'</div></div>'}
async function startDay(){
 const b=document.getElementById('runBtn');const s=document.getElementById('runState');b.disabled=true;s.textContent='waking the creatures...';
 try{const r=await fetch('/api/run',{method:'POST',headers:{'X-Shenanigan-Action':'run'}});const d=await r.json();s.textContent=d.started?'6-hour workday started':(d.reason||'already running');}
 catch(e){s.textContent='RUN failed: '+e}finally{setTimeout(refresh,700);setTimeout(()=>{b.disabled=false},1800)}
}
async function refresh(){
 try{
  const r=await fetch('/api/state',{cache:'no-store'});const d=await r.json();const m=d.metrics;const cd=d.company_day||{};
  const rb=document.getElementById('runBtn');rb.disabled=!!cd.active;rb.textContent=cd.active?'RUNNING':'RUN';document.getElementById('runState').textContent=cd.active?'company day active · '+(cd.hours||6)+'h':'idle · press RUN for a fresh 6-hour day';
  document.getElementById('metrics').innerHTML=metric('Company day',cd.active?'ACTIVE':'IDLE')+metric('Prospects',m.total_prospects)+metric('Outreach',m.outreach_sent)+metric('Paper P&L USD',Number(m.paper_pnl||0).toFixed(2))+metric('Open paper trades',m.open_paper_trades||0);
  const working=d.agents.filter(a=>['working','waiting'].includes(stateClass(a.status)));
  document.getElementById('activeAgents').innerHTML=working.length?working.map(a=>'<div class="active-card '+stateClass(a.status)+'">'+portrait(a.agent,true)+'<div><b>'+esc(a.agent)+' · '+esc(a.status)+'</b><div class="small">'+esc(a.last_action||'Nothing assigned')+'</div></div></div>').join(''):'<div class="note">Nobody is working. Either the shift ended or the agents have successfully automated themselves out of a job.</div>';
  document.getElementById('agents').innerHTML=d.agents.map(card).join('');
  const wp=d.website_project;
  if(wp){
   const ev=d.website_events.map(e=>'<tr><td>'+esc(e.agent)+'</td><td>'+esc(e.stage)+'</td><td>'+esc(e.detail)+'</td></tr>').join('');
   const wl=d.website_leads.map(x=>'<tr><td>'+esc(x.name)+'</td><td>'+esc(x.email)+'</td><td>'+esc(x.interest)+'</td><td>'+esc(x.status)+'</td></tr>').join('');
   const preview=wp.preview_url?'<a href="'+esc(wp.preview_url)+'" target="_blank" rel="noopener">open staging ↗</a>':'preview not started';
   document.getElementById('website').innerHTML='<div class="website-head"><div class="metric"><span>'+esc(wp.business_name)+' · '+esc(wp.mode)+'</span><b>'+esc(wp.status)+'</b><div class="small">Build $'+Number(wp.quoted_price||0).toFixed(0)+' · care $'+Number(wp.monthly_price||0).toFixed(0)+'/mo · images '+esc(d.website_asset_count||0)+' · delivery '+esc(wp.delivery_email_status||'NOT SENT')+' · '+preview+'</div></div><div class="metric"><span>Automation rule</span><b>AUTO-REPAIR</b><div class="small">Sentinel findings quarantine unsafe pieces; they do not kill staging.</div></div></div><h2 style="margin-top:18px">Project events</h2><div class="scroll"><table><thead><tr><th>Agent</th><th>Stage</th><th>Detail</th></tr></thead><tbody>'+ev+'</tbody></table></div><h2 style="margin-top:18px">Staging enquiries</h2><div class="scroll"><table><thead><tr><th>Name</th><th>Email</th><th>Interest</th><th>Status</th></tr></thead><tbody>'+wl+'</tbody></table></div>';
  }else document.getElementById('website').innerHTML='<div class="note">No website project currently in the furnace.</div>';
  const ts=d.trading_session||{};document.getElementById('shift').innerHTML=metric('Shift',ts.status||'IDLE')+metric('Stress',ts.stress_level==null?'-':String(ts.stress_level)+'/4')+metric('Defensive',Number(ts.defensive_mode||0)?'YES':'NO')+metric('Cycles',ts.cycles_completed||0)+metric('Model calls',ts.model_calls_used||0);
  document.getElementById('stats').innerHTML=d.trader_stats.map(x=>{const pf=x.profit_factor==null?'∞':Number(x.profit_factor).toFixed(2);return '<div class="metric"><span>'+esc(x.agent)+' '+esc(x.asset_class)+'</span><b>$'+Number(x.net_pnl||0).toFixed(2)+'</b><div class="small">closed '+esc(x.closed_trades)+' · win '+Number(x.win_rate||0).toFixed(1)+'% · PF '+esc(pf)+' · expectancy '+Number(x.expectancy_r||0).toFixed(2)+'R · '+esc(x.paper_verdict)+'</div></div>'}).join('');
  const tr=d.trades.map(t=>{const rr=(Number(t.initial_risk_usd||0)>0&&t.status!=='OPEN')?(Number(t.pnl_usd||0)/Number(t.initial_risk_usd)).toFixed(2)+'R':'-';return '<tr><td>'+esc(t.asset_class)+'</td><td>'+esc(t.symbol)+'</td><td>'+esc(t.trade_mode||'-')+'</td><td>'+esc(t.setup_score==null?'-':t.setup_score)+'</td><td>'+esc(t.status)+'</td><td>$'+Number(t.notional_usd||0).toFixed(2)+'</td><td>'+rr+'</td><td>$'+Number(t.pnl_usd||0).toFixed(2)+'</td></tr>'}).join('');
  document.getElementById('trades').innerHTML='<h2 style="margin-top:18px">Paper trades</h2><div class="scroll"><table><thead><tr><th>Class</th><th>Symbol</th><th>Mode</th><th>Score</th><th>Status</th><th>Notional</th><th>R</th><th>P&L</th></tr></thead><tbody>'+tr+'</tbody></table></div>';
  const sg=d.trade_signals.map(x=>'<tr><td>'+esc(x.agent)+'</td><td>'+esc(x.symbol)+'</td><td>'+esc(x.action)+'</td><td>'+esc(x.trade_mode||'-')+'</td><td>'+esc(x.setup_score==null?'-':x.setup_score)+'</td><td>'+esc(x.stress_level==null?'-':x.stress_level)+'/4</td><td>'+Number(x.expected_round_trip_cost_pct||0).toFixed(2)+'%</td><td>'+Number(x.expected_first_move_pct||0).toFixed(2)+'%</td><td>'+esc(x.thesis||'')+'</td></tr>').join('');
  document.getElementById('signals').innerHTML='<h2 style="margin-top:18px">Latest signals</h2><div class="scroll"><table><thead><tr><th>Agent</th><th>Symbol</th><th>Action</th><th>Mode</th><th>Score</th><th>Stress</th><th>Cost</th><th>Move</th><th>Why</th></tr></thead><tbody>'+sg+'</tbody></table></div>';
  const pr=d.prospects.map(p=>'<tr><td>'+esc(p.business_name)+'</td><td>'+esc(p.city)+'</td><td>'+esc(p.category)+'</td><td>'+esc(p.sales_score==null?'-':p.sales_score)+'</td><td>'+esc(p.status)+'</td></tr>').join('');
  document.getElementById('pipeline').innerHTML='<table><thead><tr><th>Business</th><th>Market</th><th>Category</th><th>Score</th><th>Status</th></tr></thead><tbody>'+pr+'</tbody></table>';
 }catch(e){document.getElementById('runState').textContent='dashboard refresh error';}
}
refresh();setInterval(refresh,2000);
</script></body></html>'''


def state_payload():
    conn = connect(); init_db(conn)
    agents=[dict(r) for r in conn.execute("""SELECT agent,title,status,last_action,confidence,stress,motivation,job_security,updated_at FROM agent_state ORDER BY CASE agent WHEN 'Atlas' THEN 1 WHEN 'Mercury' THEN 2 WHEN 'Forge' THEN 3 WHEN 'Freya' THEN 4 WHEN 'Nova' THEN 5 WHEN 'Satoshi' THEN 6 WHEN 'Midas' THEN 7 WHEN 'Oracle' THEN 8 WHEN 'Ledger' THEN 9 WHEN 'Sentinel' THEN 10 WHEN 'Raptor' THEN 11 WHEN 'Apex' THEN 12 WHEN 'Circuit' THEN 13 ELSE 99 END""").fetchall()]
    pipeline=conn.execute("""SELECT COUNT(*) total,SUM(CASE WHEN status='DRAFT_READY' THEN 1 ELSE 0 END) draft_ready,SUM(CASE WHEN status='CONTACT_READY' THEN 1 ELSE 0 END) contact_ready,SUM(CASE WHEN status='OUTREACH_SENT' THEN 1 ELSE 0 END) outreach_sent FROM prospects""").fetchone()
    session=conn.execute("SELECT * FROM work_sessions ORDER BY id DESC LIMIT 1").fetchone()
    tsr=conn.execute("SELECT * FROM trading_sessions ORDER BY id DESC LIMIT 1").fetchone(); trading_session=dict(tsr) if tsr else None
    summary=conn.execute("""SELECT SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) open_count,COALESCE(SUM(CASE WHEN status!='OPEN' THEN pnl_usd ELSE 0 END),0) realized_pnl FROM paper_trades""").fetchone()
    trades=[dict(r) for r in conn.execute("""SELECT asset_class,symbol,status,notional_usd,entry_price,exit_price,fees_usd,pnl_usd,opened_at,closed_at,trade_mode,setup_score,stress_level,initial_risk_usd FROM paper_trades ORDER BY id DESC LIMIT 20""").fetchall()]
    signals=[dict(r) for r in conn.execute("""SELECT agent,asset_class,symbol,action,confidence,thesis,risk_decision,created_at,trade_mode,setup_score,stress_level,signals_json,expected_round_trip_cost_pct,expected_first_move_pct,market_source FROM trade_signals ORDER BY id DESC LIMIT 20""").fetchall()]
    prospects=[dict(r) for r in conn.execute("""SELECT business_name,city,category,sales_score,status,contact_email FROM prospects ORDER BY id DESC LIMIT 20""").fetchall()]
    wr=conn.execute("SELECT * FROM website_projects ORDER BY id DESC LIMIT 1").fetchone(); website_project=dict(wr) if wr else None
    website_events=[];website_leads=[];website_lead_count=0;website_asset_count=0
    if website_project:
        pid=website_project["id"]
        website_events=[dict(r) for r in conn.execute("""SELECT agent,stage,detail,created_at FROM website_project_events WHERE project_id=? ORDER BY id DESC LIMIT 18""",(pid,)).fetchall()]
        website_leads=[dict(r) for r in conn.execute("""SELECT name,email,interest,status,created_at FROM website_leads WHERE project_id=? ORDER BY id DESC LIMIT 10""",(pid,)).fetchall()]
        website_lead_count=int(conn.execute("SELECT COUNT(*) n FROM website_leads WHERE project_id=?",(pid,)).fetchone()["n"])
        website_asset_count=int(conn.execute("SELECT COUNT(*) n FROM website_client_assets WHERE project_id=?",(pid,)).fetchone()["n"])
    payload={
      "metrics":{"workday_status":session["status"] if session else "IDLE","total_prospects":int(pipeline["total"] or 0),"draft_ready":int(pipeline["draft_ready"] or 0),"contact_ready":int(pipeline["contact_ready"] or 0),"outreach_sent":int(pipeline["outreach_sent"] or 0),"paper_pnl":float(summary["realized_pnl"] or 0),"open_paper_trades":int(summary["open_count"] or 0),"email_enabled":email_sending_enabled(),"daily_cap":daily_send_cap()},
      "company_day":workday_state(),"agents":agents,"prospects":prospects,"trades":trades,"trade_signals":signals,"trader_stats":all_trader_stats(conn),"trading_session":trading_session,
      "website_project":website_project,"website_events":website_events,"website_leads":website_leads,"website_lead_count":website_lead_count,"website_asset_count":website_asset_count,
    }
    conn.close();return payload


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status);self.send_header("Content-Type",content_type);self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)

    def do_GET(self):
        if self.path=="/" or self.path.startswith("/index"):
            return self._send(PAGE.encode("utf-8"),"text/html; charset=utf-8")
        if self.path.startswith("/api/state"):
            return self._send(json.dumps(state_payload(),ensure_ascii=False).encode("utf-8"),"application/json; charset=utf-8")
        if self.path=="/assets/agents-idle.webp":
            return self._send(IDLE_SPRITE,"image/webp")
        if self.path=="/assets/agents-active.webp":
            return self._send(ACTIVE_SPRITE,"image/webp")
        self.send_response(404);self.end_headers()

    def do_POST(self):
        if self.path!="/api/run":
            self.send_response(404);self.end_headers();return
        if self.headers.get("X-Shenanigan-Action")!="run":
            return self._send(b'{"error":"forbidden"}',"application/json",403)
        try:
            result=start_company_day_background(6.0)
            return self._send(json.dumps(result).encode("utf-8"),"application/json")
        except Exception as exc:
            return self._send(json.dumps({"started":False,"reason":str(exc)[:500]}).encode("utf-8"),"application/json",500)

    def log_message(self, format, *args):
        return


def main():
    load_dotenv();conn=connect();init_db(conn);conn.close()
    print(f"\n=== {INTERNAL_NAME.upper()} — MISSION CONTROL ===")
    print(f"Dashboard: http://{HOST}:{PORT}")
    print("RUN starts worker agents + paper trading together for a six-hour company day.")
    print("No model calls are used by the dashboard itself.\n")
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nMission Control stopped.")
    finally: server.server_close()


if __name__=="__main__":
    main()
