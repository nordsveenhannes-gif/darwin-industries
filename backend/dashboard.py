import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

from backend.emailer import daily_send_cap, email_sending_enabled
from backend.storage import connect, init_db


HOST = "127.0.0.1"
PORT = 8765


PAGE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Darwin Industries Mission Control</title>
<style>
:root {
  --bg:#090d13; --panel:#111925; --line:#243247; --text:#edf5ff;
  --muted:#91a4bc; --good:#44e39b; --warn:#ffd166; --bad:#ff6b7a;
  --blue:#70b7ff; --purple:#b89cff;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 20% 0,#152033 0,#090d13 45%);color:var(--text);font:14px/1.45 Segoe UI,Arial,sans-serif}
header{position:sticky;top:0;z-index:3;background:rgba(9,13,19,.94);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 22px;display:flex;gap:20px;align-items:center;justify-content:space-between}
.brand{font-size:20px;font-weight:800;letter-spacing:.4px}
.owner{color:var(--good);font-weight:700}
.pulse{display:inline-block;width:8px;height:8px;background:var(--good);border-radius:50%;box-shadow:0 0 12px var(--good);margin-right:7px}
main{padding:20px;max-width:1500px;margin:auto}
.grid{display:grid;grid-template-columns:1.2fr .8fr;gap:16px}.wide{grid-column:1/-1}
.panel{background:linear-gradient(180deg,rgba(21,31,46,.95),rgba(14,21,31,.96));border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 12px 30px rgba(0,0,0,.18)}
h2{font-size:14px;text-transform:uppercase;letter-spacing:1px;color:#b9cae0;margin:0 0 12px}
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.metric{background:#0d141e;border:1px solid var(--line);border-radius:10px;padding:12px}
.metric b{display:block;font-size:23px;margin-top:4px}.metric span{color:var(--muted);font-size:12px}
.agents{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.agent{background:#0d141e;border:1px solid var(--line);border-radius:12px;padding:12px;min-height:128px}
.agent .name{font-weight:800;font-size:15px}.role{color:var(--muted);font-size:11px;min-height:32px}
.status{display:inline-block;margin:8px 0;padding:3px 7px;border-radius:999px;background:#1d2a3b;color:var(--blue);font-size:10px;font-weight:800}
.action{font-size:12px;color:#d9e6f5}.bars{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:8px;color:var(--muted);font-size:10px}
.timeline{max-height:520px;overflow:auto}.event{border-left:2px solid var(--blue);padding:8px 10px;margin:0 0 10px;background:#0c131d;border-radius:0 8px 8px 0}
.event .top{display:flex;justify-content:space-between;gap:8px}.event b{color:#dcecff}.event time{color:var(--muted);font-size:10px}
.detail{white-space:pre-wrap;color:#bfcde0;font-size:12px;margin-top:4px}
.journey-title{font-size:18px;font-weight:800}.journey-sub{color:var(--muted);margin:3px 0 12px}
.steps{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:14px}.step{padding:5px 8px;border-radius:999px;background:#111a27;border:1px solid var(--line);font-size:10px}.step.on{border-color:var(--good);color:var(--good)}
.artifact{background:#0b121b;border:1px solid var(--line);border-radius:10px;padding:12px;margin-top:10px}.artifact h3{margin:0 0 8px;font-size:12px;color:var(--purple)}
pre{white-space:pre-wrap;word-break:break-word;margin:0;font:12px/1.45 Consolas,monospace;color:#dce8f6}
.small{color:var(--muted);font-size:11px}.good{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:8px;border-bottom:1px solid #203047;text-align:left}th{color:var(--muted)}
code{color:#cfe7ff}
@media(max-width:1000px){.grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.agents{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header>
  <div><span class="pulse"></span><span class="brand">Darwin Industries — Mission Control</span></div>
  <div class="owner">OWNER ON DECK <span class="small">• live local monitor • no model calls</span></div>
</header>
<main>
  <section class="panel wide">
    <h2>Company pulse</h2>
    <div class="metrics" id="metrics"></div>
  </section>
  <div class="grid" style="margin-top:16px">
    <section class="panel wide">
      <h2>Agent floor</h2>
      <div class="agents" id="agents"></div>
    </section>
    <section class="panel">
      <h2>Live customer journey</h2>
      <div id="journey"></div>
    </section>
    <section class="panel">
      <h2>Activity stream</h2>
      <div class="timeline" id="events"></div>
    </section>
    <section class="panel wide">
      <h2>Sales pipeline</h2>
      <div id="pipeline"></div>
    </section>
  </div>
</main>
<script>
function esc(s){
  s=(s===null||s===undefined)?"":String(s);
  return s.replace(/[&<>"']/g,function(m){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m];});
}
function makeMetric(label,value){
  return '<div class="metric"><span>'+esc(label)+'</span><b>'+esc(value)+'</b></div>';
}
function makeAgent(a){
  return '<div class="agent">'
    +'<div class="name">'+esc(a.agent)+'</div>'
    +'<div class="role">'+esc(a.title)+'</div>'
    +'<div class="status">'+esc(a.status)+'</div>'
    +'<div class="action">'+esc(a.last_action||"")+'</div>'
    +'<div class="bars"><span>conf '+esc(a.confidence)+'</span><span>stress '+esc(a.stress)+'</span>'
    +'<span>mot '+esc(a.motivation)+'</span><span>security '+esc(a.job_security)+'</span></div>'
    +'</div>';
}
function makeStep(label,on){
  return '<span class="step'+(on?' on':'')+'">'+esc(label)+'</span>';
}
function makeArtifact(title,body){
  return '<div class="artifact"><h3>'+esc(title)+'</h3><pre>'+esc(body)+'</pre></div>';
}
function makeEvent(e){
  var who=e.agent||e.event_type||"System";
  var stage=e.stage||e.event_type||"";
  var t=(e.created_at||"").replace("T"," ").slice(0,19);
  return '<div class="event"><div class="top"><b>'+esc(who)+' • '+esc(stage)+'</b><time>'+esc(t)+'</time></div>'
    +'<div class="detail">'+esc(e.detail||"")+'</div></div>';
}
async function refresh(){
  var r=await fetch("/api/state",{cache:"no-store"});
  var d=await r.json();
  var m=d.metrics;
  document.getElementById("metrics").innerHTML=
      makeMetric("Workday",m.workday_status||"IDLE")
    + makeMetric("Prospects",m.total_prospects)
    + makeMetric("Drafts",m.draft_ready)
    + makeMetric("Contacts",m.contact_ready)
    + makeMetric("Outreach sent",m.outreach_sent);

  document.getElementById("agents").innerHTML=d.agents.map(makeAgent).join("");

  var j=d.journey;
  if(!j){
    document.getElementById("journey").innerHTML='<div class="small">No customer demo yet. Run <code>python -m backend.demo_customer ...</code>.</div>';
  } else {
    var stages=["STARTED","DISCOVERED","AUDIT_DRAFTED","AUDIT_QA_PASS","OUTREACH_DRAFTED","OUTREACH_QA_PASS","READY_TO_SEND","EMAIL_SENT"];
    var idx=stages.indexOf(j.status);
    var html='<div class="journey-title">'+esc(j.business_name)+'</div>'
      +'<div class="journey-sub">'+esc(j.website_url)+' • '+esc(j.customer_email)+' • <b>'+esc(j.status)+'</b></div>'
      +'<div class="steps">';
    for(var i=0;i<stages.length;i++){ html+=makeStep(stages[i].replaceAll("_"," "), idx>=i); }
    html+='</div>';
    if(j.observation){html+=makeArtifact("Oracle observation",j.observation);}
    if(j.audit_text){html+=makeArtifact("Forge audit",j.audit_text);}
    if(j.audit_qa){html+=makeArtifact("Sentinel audit QA",j.audit_qa);}
    if(j.outreach_subject){html+=makeArtifact("Mercury email","Subject: "+j.outreach_subject+"\n\n"+(j.outreach_body||""));}
    if(j.outreach_qa){html+=makeArtifact("Sentinel outreach QA",j.outreach_qa);}
    if(j.email_status){html+=makeArtifact("External action","Email: "+j.email_status+"\nPayment: NOT CONNECTED YET");}
    if(j.error_text){html+=makeArtifact("Error",j.error_text);}
    document.getElementById("journey").innerHTML=html;
  }

  var combined=[];
  d.journey_events.forEach(function(e){combined.push(e);});
  d.company_events.forEach(function(e){combined.push(e);});
  combined.sort(function(a,b){return (b.created_at||"").localeCompare(a.created_at||"");});
  combined=combined.slice(0,50);
  document.getElementById("events").innerHTML=combined.length?combined.map(makeEvent).join(""):'<div class="small">No events yet.</div>';

  var rows=d.prospects.map(function(p){
    return '<tr><td>'+esc(p.business_name)+'</td><td>'+esc(p.city)+'</td><td>'+esc(p.category)
      +'</td><td>'+esc(p.sales_score===null?"-":p.sales_score)+'</td><td>'+esc(p.status)
      +'</td><td>'+esc(p.contact_email||"-")+'</td></tr>';
  }).join("");
  document.getElementById("pipeline").innerHTML='<table><thead><tr><th>Business</th><th>Market</th><th>Category</th><th>Score</th><th>Status</th><th>Contact</th></tr></thead><tbody>'+rows+'</tbody></table>';
}
refresh();
setInterval(refresh,2000);
</script>
</body>
</html>"""


def _row(row):
    return dict(row) if row is not None else None


def state_payload():
    conn = connect()
    init_db(conn)

    agents = [
        dict(r)
        for r in conn.execute(
            """
            SELECT agent, title, status, last_action, confidence, stress,
                   motivation, job_security, updated_at
            FROM agent_state
            ORDER BY CASE agent
                WHEN 'Atlas' THEN 1 WHEN 'Mercury' THEN 2 WHEN 'Forge' THEN 3
                WHEN 'Freya' THEN 4 WHEN 'Nova' THEN 5 WHEN 'Satoshi' THEN 6
                WHEN 'Midas' THEN 7 WHEN 'Oracle' THEN 8 WHEN 'Ledger' THEN 9
                WHEN 'Sentinel' THEN 10 ELSE 99 END
            """
        ).fetchall()
    ]

    pipeline = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='DRAFT_READY' THEN 1 ELSE 0 END) AS draft_ready,
            SUM(CASE WHEN status='CONTACT_READY' THEN 1 ELSE 0 END) AS contact_ready,
            SUM(CASE WHEN status='OUTREACH_SENT' THEN 1 ELSE 0 END) AS outreach_sent
        FROM prospects
        """
    ).fetchone()

    session = conn.execute(
        "SELECT * FROM work_sessions ORDER BY id DESC LIMIT 1"
    ).fetchone()

    journey = conn.execute(
        "SELECT * FROM customer_journeys ORDER BY id DESC LIMIT 1"
    ).fetchone()

    journey_events = []
    if journey:
        journey_events = [
            dict(r)
            for r in conn.execute(
                """
                SELECT agent, stage, detail, created_at
                FROM journey_events
                WHERE journey_id=?
                ORDER BY id DESC
                LIMIT 40
                """,
                (journey["id"],),
            ).fetchall()
        ]

    company_events = [
        dict(r)
        for r in conn.execute(
            """
            SELECT event_type, detail, created_at
            FROM events
            ORDER BY id DESC
            LIMIT 40
            """
        ).fetchall()
    ]

    prospects = [
        dict(r)
        for r in conn.execute(
            """
            SELECT business_name, city, category, sales_score, status, contact_email
            FROM prospects
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()
    ]

    payload = {
        "metrics": {
            "workday_status": session["status"] if session else "IDLE",
            "total_prospects": int(pipeline["total"] or 0),
            "draft_ready": int(pipeline["draft_ready"] or 0),
            "contact_ready": int(pipeline["contact_ready"] or 0),
            "outreach_sent": int(pipeline["outreach_sent"] or 0),
            "email_enabled": email_sending_enabled(),
            "daily_cap": daily_send_cap(),
        },
        "agents": agents,
        "journey": _row(journey),
        "journey_events": journey_events,
        "company_events": company_events,
        "prospects": prospects,
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


def main() -> None:
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
