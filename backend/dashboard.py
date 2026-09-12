import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

from backend.emailer import daily_send_cap, email_sending_enabled
from backend.storage import connect, init_db
from backend.trading_stats import all_trader_stats

HOST = "127.0.0.1"
PORT = 8765

PAGE = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Darwin Industries Mission Control</title>
<style>
:root{--bg:#090d13;--panel:#111925;--line:#243247;--text:#edf5ff;--muted:#91a4bc;--good:#44e39b;--blue:#70b7ff}
*{box-sizing:border-box}body{margin:0;background:#090d13;color:var(--text);font:14px/1.45 Segoe UI,Arial,sans-serif}header{position:sticky;top:0;background:#0b111a;border-bottom:1px solid var(--line);padding:15px 22px;display:flex;justify-content:space-between}.brand{font-size:20px;font-weight:800}.owner{color:var(--good);font-weight:700}main{max-width:1500px;margin:auto;padding:20px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:16px}h2{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:#b9cae0}.metrics,.agents{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.metric,.agent{background:#0d141e;border:1px solid var(--line);border-radius:10px;padding:12px}.metric b{display:block;font-size:22px}.metric span,.small{color:var(--muted);font-size:11px}.name{font-weight:800}.role{color:var(--muted);font-size:11px}.status{display:inline-block;margin:7px 0;padding:3px 7px;border-radius:20px;background:#1d2a3b;color:var(--blue);font-size:10px}.action{font-size:12px}table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:8px;border-bottom:1px solid #203047;text-align:left}th{color:var(--muted)}.good{color:var(--good)}@media(max-width:900px){.metrics,.agents{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<header><div class="brand">Darwin Industries — Mission Control</div><div class="owner">OWNER ON DECK • LIVE</div></header>
<main>
<section class="panel"><h2>Company pulse</h2><div class="metrics" id="metrics"></div></section>
<section class="panel"><h2>Agent floor</h2><div class="agents" id="agents"></div></section>
<section class="panel"><h2>Trading desk — simulation</h2><div class="small">Live market observations, fake fills, estimated slippage/fees. Real-money execution disabled.</div><div class="metrics" id="stats" style="margin-top:10px"></div><div id="trades"></div><div id="signals"></div></section>
<section class="panel"><h2>Sales pipeline</h2><div id="pipeline"></div></section>
</main>
<script>
function esc(v){v=(v==null?'':String(v));return v.replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]})}
function metric(k,v){return '<div class="metric"><span>'+esc(k)+'</span><b>'+esc(v)+'</b></div>'}
async function refresh(){
 try{
  const r=await fetch('/api/state',{cache:'no-store'}); const d=await r.json(); const m=d.metrics;
  document.getElementById('metrics').innerHTML=metric('Workday',m.workday_status||'IDLE')+metric('Prospects',m.total_prospects)+metric('Outreach',m.outreach_sent)+metric('Paper P&L USD',Number(m.paper_pnl||0).toFixed(2))+metric('Open paper trades',m.open_paper_trades||0);
  document.getElementById('agents').innerHTML=d.agents.map(a=>'<div class="agent"><div class="name">'+esc(a.agent)+'</div><div class="role">'+esc(a.title)+'</div><div class="status">'+esc(a.status)+'</div><div class="action">'+esc(a.last_action||'')+'</div><div class="small">conf '+esc(a.confidence)+' • stress '+esc(a.stress)+' • mot '+esc(a.motivation)+'</div></div>').join('');
  document.getElementById('stats').innerHTML=d.trader_stats.map(x=>{const pf=x.profit_factor==null?'∞':Number(x.profit_factor).toFixed(2);return '<div class="metric"><span>'+esc(x.agent)+' '+esc(x.asset_class)+'</span><b>$'+Number(x.net_pnl||0).toFixed(2)+'</b><div class="small">closed '+esc(x.closed_trades)+' • win '+Number(x.win_rate||0).toFixed(1)+'% • PF '+esc(pf)+' • drawdown $'+Number(x.max_drawdown||0).toFixed(2)+' • '+esc(x.paper_verdict)+'</div></div>'}).join('');
  const tr=d.trades.map(t=>'<tr><td>'+esc(t.asset_class)+'</td><td>'+esc(t.symbol)+'</td><td>'+esc(t.status)+'</td><td>$'+Number(t.notional_usd||0).toFixed(2)+'</td><td>'+Number(t.entry_price||0).toFixed(6)+'</td><td>'+(t.exit_price==null?'-':Number(t.exit_price).toFixed(6))+'</td><td>$'+Number(t.fees_usd||0).toFixed(2)+'</td><td>$'+Number(t.pnl_usd||0).toFixed(2)+'</td></tr>').join('');
  document.getElementById('trades').innerHTML='<h2 style="margin-top:18px">Paper trades</h2><table><thead><tr><th>Class</th><th>Symbol</th><th>Status</th><th>Notional</th><th>Entry</th><th>Exit</th><th>Fees</th><th>Net P&L</th></tr></thead><tbody>'+tr+'</tbody></table>';
  const sg=d.trade_signals.map(x=>'<tr><td>'+esc(x.agent)+'</td><td>'+esc(x.asset_class)+'</td><td>'+esc(x.symbol)+'</td><td>'+esc(x.action)+'</td><td>'+esc(x.confidence)+'</td><td>'+esc((x.created_at||'').replace('T',' ').slice(0,19))+'</td></tr>').join('');
  document.getElementById('signals').innerHTML='<h2 style="margin-top:18px">Latest signals</h2><table><thead><tr><th>Agent</th><th>Class</th><th>Symbol</th><th>Action</th><th>Confidence</th><th>Time</th></tr></thead><tbody>'+sg+'</tbody></table>';
  const pr=d.prospects.map(p=>'<tr><td>'+esc(p.business_name)+'</td><td>'+esc(p.city)+'</td><td>'+esc(p.category)+'</td><td>'+esc(p.sales_score==null?'-':p.sales_score)+'</td><td>'+esc(p.status)+'</td></tr>').join('');
  document.getElementById('pipeline').innerHTML='<table><thead><tr><th>Business</th><th>Market</th><th>Category</th><th>Score</th><th>Status</th></tr></thead><tbody>'+pr+'</tbody></table>';
 }catch(e){document.getElementById('metrics').innerHTML='<div class="small">Refresh error: '+esc(e)+'</div>'}
}
refresh(); setInterval(refresh,2000);
</script></body></html>'''


def state_payload():
    conn = connect(); init_db(conn)
    agents = [dict(r) for r in conn.execute("""SELECT agent,title,status,last_action,confidence,stress,motivation,job_security,updated_at FROM agent_state ORDER BY CASE agent WHEN 'Atlas' THEN 1 WHEN 'Mercury' THEN 2 WHEN 'Forge' THEN 3 WHEN 'Freya' THEN 4 WHEN 'Nova' THEN 5 WHEN 'Satoshi' THEN 6 WHEN 'Midas' THEN 7 WHEN 'Oracle' THEN 8 WHEN 'Ledger' THEN 9 WHEN 'Sentinel' THEN 10 WHEN 'Raptor' THEN 11 WHEN 'Apex' THEN 12 WHEN 'Circuit' THEN 13 ELSE 99 END""").fetchall()]
    pipeline = conn.execute("""SELECT COUNT(*) total,SUM(CASE WHEN status='DRAFT_READY' THEN 1 ELSE 0 END) draft_ready,SUM(CASE WHEN status='CONTACT_READY' THEN 1 ELSE 0 END) contact_ready,SUM(CASE WHEN status='OUTREACH_SENT' THEN 1 ELSE 0 END) outreach_sent FROM prospects""").fetchone()
    session = conn.execute("SELECT * FROM work_sessions ORDER BY id DESC LIMIT 1").fetchone()
    summary = conn.execute("""SELECT SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) open_count,COALESCE(SUM(CASE WHEN status!='OPEN' THEN pnl_usd ELSE 0 END),0) realized_pnl FROM paper_trades""").fetchone()
    trades=[dict(r) for r in conn.execute("SELECT asset_class,symbol,status,notional_usd,entry_price,exit_price,fees_usd,pnl_usd,opened_at,closed_at FROM paper_trades ORDER BY id DESC LIMIT 20").fetchall()]
    signals=[dict(r) for r in conn.execute("SELECT agent,asset_class,symbol,action,confidence,created_at FROM trade_signals ORDER BY id DESC LIMIT 20").fetchall()]
    prospects=[dict(r) for r in conn.execute("SELECT business_name,city,category,sales_score,status,contact_email FROM prospects ORDER BY id DESC LIMIT 20").fetchall()]
    payload={'metrics':{'workday_status':session['status'] if session else 'IDLE','total_prospects':int(pipeline['total'] or 0),'draft_ready':int(pipeline['draft_ready'] or 0),'contact_ready':int(pipeline['contact_ready'] or 0),'outreach_sent':int(pipeline['outreach_sent'] or 0),'paper_pnl':float(summary['realized_pnl'] or 0),'open_paper_trades':int(summary['open_count'] or 0),'email_enabled':email_sending_enabled(),'daily_cap':daily_send_cap()},'agents':agents,'prospects':prospects,'trades':trades,'trade_signals':signals,'trader_stats':all_trader_stats(conn)}
    conn.close(); return payload


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path.startswith('/index'):
            body=PAGE.encode('utf-8'); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path.startswith('/api/state'):
            body=json.dumps(state_payload(),ensure_ascii=False).encode('utf-8'); self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        self.send_response(404); self.end_headers()
    def log_message(self, format, *args): return


def main():
    load_dotenv(); conn=connect(); init_db(conn); conn.close()
    print('\n=== DARWIN MISSION CONTROL ==='); print(f'Live monitor: http://{HOST}:{PORT}'); print('Auto-refresh: every 2 seconds'); print('No model calls are used by the dashboard.'); print('Press Ctrl+C to stop the monitor.\n')
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nMission Control stopped.')
    finally: server.server_close()


if __name__ == '__main__': main()
