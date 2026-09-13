import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

from backend.emailer import daily_send_cap, email_sending_enabled
from backend.storage import connect, init_db
from backend.trading_stats import all_trader_stats


HOST = "127.0.0.1"
PORT = 8765


PAGE = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Darwin Industries Mission Control</title>
<style>
:root{
  --bg:#090d13;--panel:#111925;--line:#243247;--text:#edf5ff;--muted:#91a4bc;
  --good:#44e39b;--blue:#70b7ff;--warn:#ffd166;--danger:#ff7b7b
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 Segoe UI,Arial,sans-serif}
header{position:sticky;top:0;z-index:20;background:#0b111a;border-bottom:1px solid var(--line);padding:15px 22px;display:flex;justify-content:space-between;gap:20px}
.brand{font-size:20px;font-weight:800}.owner{color:var(--good);font-weight:800}
main{max-width:1500px;margin:auto;padding:20px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:16px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:#b9cae0}
.metrics,.agents{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.active-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.metric,.agent,.active-card{background:#0d141e;border:1px solid var(--line);border-radius:12px;padding:12px}
.metric b{display:block;font-size:22px}.metric span,.small{color:var(--muted);font-size:11px}
.name{font-weight:800}.role{color:var(--muted);font-size:11px}
.status{display:inline-block;margin:7px 0;padding:3px 7px;border-radius:20px;background:#1d2a3b;color:var(--blue);font-size:10px}
.agent{position:relative;overflow:hidden;transition:.2s transform,.2s border-color,.2s box-shadow}.agent:hover{transform:translateY(-2px)}
.agent.working{border-color:var(--good);box-shadow:0 0 0 1px rgba(68,227,155,.18),0 0 28px rgba(68,227,155,.10)}
.agent.working:before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--good)}
.agent.waiting{border-color:var(--warn)}.agent.off{opacity:.58}
.agent-avatar{width:52px;height:52px;border-radius:16px;display:grid;place-items:center;font-size:28px;background:linear-gradient(145deg,#182334,#0b111a);border:1px solid #2c4058}
.agent-top{display:flex;align-items:center;gap:12px}.agent-meta{min-width:0}
.working-badge{display:inline-flex;align-items:center;gap:6px;font-size:10px;font-weight:900;letter-spacing:.08em;color:var(--good);margin-top:7px}
.working-badge:before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 12px currentColor}
.now-label{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:#6f859f;margin-top:10px}.action{font-size:12px;margin-top:3px}
.agent-quips{color:#73869d;font-size:10px;margin-top:8px;font-style:italic}
.active-card{display:flex;gap:12px;align-items:center;border-color:#26415a}.active-card strong{display:block}.active-card .small{margin-top:3px}
.good{color:var(--good)}.warn{color:var(--warn)}.danger{color:var(--danger)}a{color:#9fd0ff}
table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:8px;border-bottom:1px solid #203047;text-align:left;vertical-align:top}th{color:var(--muted)}
.scroll{overflow:auto}
@media(max-width:1100px){.metrics,.agents{grid-template-columns:repeat(3,1fr)}}
@media(max-width:900px){.metrics,.agents,.active-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:560px){.metrics,.agents,.active-grid{grid-template-columns:1fr}header{align-items:flex-start;flex-direction:column}}
</style>
</head>
<body>
<header><div class="brand">Darwin Industries — Mission Control</div><div class="owner">OWNER ON DECK • LIVE</div></header>
<main>
<section class="panel"><h2>Company pulse</h2><div class="metrics" id="metrics"></div></section>
<section class="panel"><h2>Who's working right now</h2><div class="small">Green means actually working. Yellow means blocked/waiting. No corporate fog machine.</div><div class="active-grid" id="activeAgents" style="margin-top:10px"></div></section>
<section class="panel"><h2>Agent floor</h2><div class="agents" id="agents"></div></section>
<section class="panel"><h2>Website studio</h2><div class="small">Quote → client brief → design → UX → QA → staging → client email.</div><div id="website" style="margin-top:10px"></div></section>
<section class="panel"><h2>Trading desk — simulation</h2><div class="small">Six-hour shift • live market observations • fake fills • adaptive opportunity stress. Real-money execution disabled.</div><div class="metrics" id="shift" style="margin-top:10px"></div><div class="metrics" id="stats" style="margin-top:10px"></div><div id="trades"></div><div id="signals"></div></section>
<section class="panel"><h2>Sales pipeline</h2><div class="scroll" id="pipeline"></div></section>
</main>
<script>
function esc(v){v=(v==null?'':String(v));return v.replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]})}
function metric(k,v){return '<div class="metric"><span>'+esc(k)+'</span><b>'+esc(v)+'</b></div>'}
const persona={
 Atlas:['🧠','Turns existential dread into capital allocation.'],
 Mercury:['🦊','Would sell umbrellas during a meteor strike.'],
 Forge:['🔧','Breaks things professionally, then invoices the fix.'],
 Freya:['🤝','Networking, but with fewer conference sandwiches.'],
 Nova:['🚀','Growth charts or emotional damage. Sometimes both.'],
 Satoshi:['🤖','Automates the boring bits before they unionize.'],
 Midas:['✨','Makes pixels expensive-looking on purpose.'],
 Oracle:['🔮','Reads the internet so you do not have to.'],
 Ledger:['💀','Keeps bankruptcy in the simulation layer.'],
 Sentinel:['🛡️','Professional killer of bad ideas.'],
 Raptor:['🦖','Stares at candles until one confesses.'],
 Apex:['🦈','Stock-market shark. Currently wearing paper teeth.'],
 Circuit:['⚡','Says “no” so the others can survive saying “yes”.']
};
function stateClass(status){
 const x=String(status||'').toUpperCase();
 if(x.includes('WORKING')||x.includes('ON_SHIFT')) return 'working';
 if(x.includes('WAITING')||x.includes('NEEDED')||x.includes('BLOCKED')) return 'waiting';
 if(x.includes('OFF')||x.includes('STOPPED')) return 'off';
 return 'ready';
}
function agentCard(a){
 const p=persona[a.agent]||['👤','Still awaiting a sufficiently dramatic backstory.'];
 const cls=stateClass(a.status);
 const badge=cls==='working'?'<span class="working-badge">WORKING</span>':'<span class="status">'+esc(a.status)+'</span>';
 return '<div class="agent '+cls+'"><div class="agent-top"><div class="agent-avatar">'+p[0]+'</div><div class="agent-meta"><div class="name">'+esc(a.agent)+'</div><div class="role">'+esc(a.title)+'</div>'+badge+'</div></div><div class="now-label">Now</div><div class="action">'+esc(a.last_action||'Nothing assigned')+'</div><div class="agent-quips">'+esc(p[1])+'</div><div class="small">confidence '+esc(a.confidence)+' • stress '+esc(a.stress)+' • motivation '+esc(a.motivation)+'</div></div>';
}
async function refresh(){
 try{
  const r=await fetch('/api/state',{cache:'no-store'});
  const d=await r.json();
  const m=d.metrics;
  document.getElementById('metrics').innerHTML=
    metric('Workday',m.workday_status||'IDLE')+
    metric('Prospects',m.total_prospects)+
    metric('Outreach',m.outreach_sent)+
    metric('Paper P&L USD',Number(m.paper_pnl||0).toFixed(2))+
    metric('Open paper trades',m.open_paper_trades||0);

  const working=d.agents.filter(function(a){const c=stateClass(a.status);return c==='working'||c==='waiting'});
  document.getElementById('activeAgents').innerHTML=working.length?
    working.map(function(a){
      const p=persona[a.agent]||['👤',''];
      return '<div class="active-card"><div class="agent-avatar">'+p[0]+'</div><div><strong>'+esc(a.agent)+' · '+esc(a.status)+'</strong><div class="small">'+esc(a.last_action||'Nothing assigned')+'</div></div></div>';
    }).join(''):
    '<div class="small">Nobody is actively working right now. Either the company is sleeping or something has gone suspiciously well.</div>';

  document.getElementById('agents').innerHTML=d.agents.map(agentCard).join('');

  const wp=d.website_project;
  if(wp){
    const ev=d.website_events.map(function(e){return '<tr><td>'+esc(e.agent)+'</td><td>'+esc(e.stage)+'</td><td>'+esc(e.detail)+'</td></tr>'}).join('');
    const wl=d.website_leads.map(function(x){return '<tr><td>'+esc(x.name)+'</td><td>'+esc(x.email)+'</td><td>'+esc(x.interest)+'</td><td>'+esc(x.status)+'</td></tr>'}).join('');
    const cq=d.website_client_questions.map(function(q){return '<tr><td>'+esc(q.required_for)+'</td><td>'+esc(q.question)+'</td><td>'+esc(q.status)+'</td><td>'+esc(q.answer||'-')+'</td></tr>'}).join('');
    const preview=wp.preview_url?'<a href="'+esc(wp.preview_url)+'" target="_blank" rel="noopener">Open staging preview ↗</a>':'Preview not started';
    document.getElementById('website').innerHTML=
      '<div class="metric"><span>'+esc(wp.business_name)+' • '+esc(wp.mode)+'</span><b>'+esc(wp.status)+'</b>'+
      '<div class="small">Build $'+Number(wp.quoted_price||0).toFixed(0)+' • care $'+Number(wp.monthly_price||0).toFixed(0)+'/mo • revisions '+esc(wp.revision_rounds_used||0)+'/2 • approval '+esc(wp.customer_approval_status||'PENDING')+' • client images '+esc(d.website_asset_count||0)+' • delivery email '+esc(wp.delivery_email_status||'NOT SENT')+' • '+preview+' • leads '+esc(d.website_lead_count||0)+'</div></div>'+
      '<h2 style="margin-top:18px">Client brief / clarifications</h2><div class="scroll"><table><thead><tr><th>Gate</th><th>Question</th><th>Status</th><th>Answer</th></tr></thead><tbody>'+cq+'</tbody></table></div>'+
      '<h2 style="margin-top:18px">Project events</h2><div class="scroll"><table><thead><tr><th>Agent</th><th>Stage</th><th>Detail</th></tr></thead><tbody>'+ev+'</tbody></table></div>'+
      '<h2 style="margin-top:18px">Staging enquiries</h2><div class="scroll"><table><thead><tr><th>Name</th><th>Email</th><th>Interest</th><th>Status</th></tr></thead><tbody>'+wl+'</tbody></table></div>';
  }else{
    document.getElementById('website').innerHTML='<div class="small">No website project yet.</div>';
  }

  const ts=d.trading_session||{};
  document.getElementById('shift').innerHTML=
    metric('Shift',ts.status||'IDLE')+
    metric('Stress',ts.stress_level==null?'-':String(ts.stress_level)+'/4')+
    metric('Defensive',Number(ts.defensive_mode||0)?'YES':'NO')+
    metric('Cycles',ts.cycles_completed||0)+
    metric('Model calls',ts.model_calls_used||0);

  document.getElementById('stats').innerHTML=d.trader_stats.map(function(x){
    const pf=x.profit_factor==null?'∞':Number(x.profit_factor).toFixed(2);
    return '<div class="metric"><span>'+esc(x.agent)+' '+esc(x.asset_class)+'</span><b>$'+Number(x.net_pnl||0).toFixed(2)+'</b><div class="small">closed '+esc(x.closed_trades)+' • win '+Number(x.win_rate||0).toFixed(1)+'% • PF '+esc(pf)+' • expectancy '+Number(x.expectancy_r||0).toFixed(2)+'R • drawdown $'+Number(x.max_drawdown||0).toFixed(2)+' • '+esc(x.paper_verdict)+'</div></div>';
  }).join('');

  const tr=d.trades.map(function(t){
    const r=(Number(t.initial_risk_usd||0)>0&&t.status!=='OPEN')?(Number(t.pnl_usd||0)/Number(t.initial_risk_usd)).toFixed(2)+'R':'-';
    return '<tr><td>'+esc(t.asset_class)+'</td><td>'+esc(t.symbol)+'</td><td>'+esc(t.trade_mode||'-')+'</td><td>'+esc(t.setup_score==null?'-':t.setup_score)+'</td><td>'+esc(t.status)+'</td><td>$'+Number(t.notional_usd||0).toFixed(2)+'</td><td>'+r+'</td><td>$'+Number(t.pnl_usd||0).toFixed(2)+'</td></tr>';
  }).join('');
  document.getElementById('trades').innerHTML='<h2 style="margin-top:18px">Paper trades</h2><div class="scroll"><table><thead><tr><th>Class</th><th>Symbol</th><th>Mode</th><th>Score</th><th>Status</th><th>Notional</th><th>R</th><th>Net P&L</th></tr></thead><tbody>'+tr+'</tbody></table></div>';

  const sg=d.trade_signals.map(function(x){
    return '<tr><td>'+esc(x.agent)+'</td><td>'+esc(x.symbol)+'</td><td>'+esc(x.action)+'</td><td>'+esc(x.trade_mode||'-')+'</td><td>'+esc(x.setup_score==null?'-':x.setup_score)+'</td><td>'+esc(x.stress_level==null?'-':x.stress_level)+'/4</td><td>'+Number(x.expected_round_trip_cost_pct||0).toFixed(2)+'%</td><td>'+Number(x.expected_first_move_pct||0).toFixed(2)+'%</td><td>'+esc(x.thesis||'')+'</td></tr>';
  }).join('');
  document.getElementById('signals').innerHTML='<h2 style="margin-top:18px">Latest signals</h2><div class="scroll"><table><thead><tr><th>Agent</th><th>Symbol</th><th>Action</th><th>Mode</th><th>Score</th><th>Stress</th><th>Cost</th><th>Move</th><th>Why</th></tr></thead><tbody>'+sg+'</tbody></table></div>';

  const pr=d.prospects.map(function(p){return '<tr><td>'+esc(p.business_name)+'</td><td>'+esc(p.city)+'</td><td>'+esc(p.category)+'</td><td>'+esc(p.sales_score==null?'-':p.sales_score)+'</td><td>'+esc(p.status)+'</td></tr>'}).join('');
  document.getElementById('pipeline').innerHTML='<table><thead><tr><th>Business</th><th>Market</th><th>Category</th><th>Score</th><th>Status</th></tr></thead><tbody>'+pr+'</tbody></table>';
 }catch(e){
  document.getElementById('metrics').innerHTML='<div class="small">Refresh error: '+esc(e)+'</div>';
 }
}
refresh();
setInterval(refresh,2000);
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
    trading_session_row = conn.execute(
        "SELECT * FROM trading_sessions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    trading_session = dict(trading_session_row) if trading_session_row else None
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
    website_events = []
    website_leads = []
    website_client_questions = []
    website_lead_count = 0
    website_asset_count = 0

    if website_project:
        pid = website_project["id"]
        website_events = [
            dict(r)
            for r in conn.execute(
                """SELECT agent,stage,detail,created_at
                FROM website_project_events
                WHERE project_id=? ORDER BY id DESC LIMIT 14""",
                (pid,),
            ).fetchall()
        ]
        website_leads = [
            dict(r)
            for r in conn.execute(
                """SELECT name,email,interest,status,created_at
                FROM website_leads
                WHERE project_id=? ORDER BY id DESC LIMIT 10""",
                (pid,),
            ).fetchall()
        ]
        website_client_questions = [
            dict(r)
            for r in conn.execute(
                """SELECT question,required_for,answer,status,answered_at
                FROM website_client_questions
                WHERE project_id=? ORDER BY id""",
                (pid,),
            ).fetchall()
        ]
        website_lead_count = int(
            conn.execute(
                "SELECT COUNT(*) n FROM website_leads WHERE project_id=?",
                (pid,),
            ).fetchone()["n"]
        )
        website_asset_count = int(
            conn.execute(
                "SELECT COUNT(*) n FROM website_client_assets WHERE project_id=?",
                (pid,),
            ).fetchone()["n"]
        )

    payload = {
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
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/api/state"):
            body = json.dumps(state_payload(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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

    print("\n=== DARWIN MISSION CONTROL ===")
    print(f"Live monitor: http://{HOST}:{PORT}")
    print("Auto-refresh: every 2 seconds")
    print("No model calls are used by the dashboard.")
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
