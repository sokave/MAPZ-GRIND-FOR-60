"""Lab 10: check BPMN/DI, CSV oracles, UML traces, and virtual BPMN scenarios.

Uses Python 3 standard library only. This is a model-level check, not an
execution of Camunda or of a deployed delivery service.
"""
import argparse
import base64
from collections import Counter, defaultdict
import csv
from fractions import Fraction
from heapq import heappop, heappush
from html.parser import HTMLParser
from itertools import count
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET


NS = {
    "b": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "di": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "dd": "http://www.omg.org/spec/DD/20100524/DI",
}
CSV = "Лаб10_тест_кейси.csv"
BPMN = "Лаб10_процес.bpmn"
BPMN_SVG = "Лаб10_діаграма_BPMN.svg"
PUML = "Лаб10_діаграма_станів_нумерована.puml"
STATE_SVG = "Лаб10_діаграма_станів_нумерована.svg"
COLS = ["ID","Назва","Вид","Передумова","Кроки (події)","Очікуваний результат","Що покриває","Вхід_JSON","Оракул_JSON"]
OFF, WAIT, OFFER, TRAVEL, PICKED, CLIENT, BREAK = (
    "Офлайн","ОчікуєЗамовлення","ОтримавПропозицію","ПрямуєДоЗакладу",
    "ЗабравЗамовлення","ПрямуєДоКлієнта","Перерва",
)
STATES = (OFF, WAIT, OFFER, TRAVEL, PICKED, CLIENT, BREAK)
PRETTY = dict(zip(STATES, ("Офлайн","Очікує замовлення","Отримав пропозицію","Прямує до закладу",
                         "Забрав замовлення","Прямує до клієнта","Перерва")))
ENTER, DISMISS, PROPOSE, REJECT, ACCEPT, PICK, LEAVE, DELIVER, FINISH, PAUSE, RESUME, GPS = (
    "увійтиНаЗміну","звільнити","пропозиціяНадійшла","відхилив","прийняв",
    "забравЗамовлення","вирушив","доставив","завершитиЗміну","взятиПерерву",
    "повернутисяЗПерерви","оновитиGPS",
)
EVENTS=(ENTER, DISMISS, PROPOSE, REJECT, ACCEPT, PICK, LEAVE, DELIVER, FINISH, PAUSE, RESUME, GPS)
TIDS=[f"T{i}" for i in range(1,13)]+["I1"]


def state_case(n,name,kind,start,steps,fired,end,expected,**extra):
    inp={"model":"state","start":start,"steps":[list(x) for x in steps]}
    if start==OFFER:
        inp["offer"]="з1"
    if start in (TRAVEL,CLIENT):
        inp["assigned"]="з1"
    if start==BREAK:
        inp["history"]=WAIT
    want={"fired":fired,"state":end,**extra}
    pre="Курʼєра ще не створено." if start=="@start" else f"Стан «{PRETTY[start]}»."
    if start==OFFER: pre+=" Активна пропозиція з1."
    if start in (TRAVEL,CLIENT): pre+=" Призначено з1."
    if start==BREAK: pre+=" Останній підстан — «Очікує замовлення»."
    actions=["створитиКурʼєра()"] if start=="@start" else []
    for event,*params in steps:
        actions.append(event+"("+(", ".join(map(str,params)) if event!=ACCEPT else "")+")"+
                       (f" [залишок {params[0]} хв, оцінка {params[1]} хв]" if event==ACCEPT else ""))
    edges=", ".join(t for t in fired if t)
    if None in fired:
        edges="T6: умова хибна, перехід не виконано" if steps[0][0]==ACCEPT else f"Прихований шлях: {PRETTY[start]} × {steps[0][0]}()"
    return [f"ТК-{n:02d}",name,kind,pre,"; ".join(actions),expected,edges,inp,want]


def scenario(n,name,given,when,then,flows,answers,ready,travel,delivery,present,want):
    return [f"С-{n:02d}",name,"Сценарний BPMN",given,when,then,flows,
            {"model":"bpmn","answers":answers,"ready":ready,"travel":travel,"delivery":delivery,"present":present},want]


def catalog():
    cases=[
        state_case(1,"Повний цикл доставки","Базовий шлях", "@start",
          [(ENTER,),(PROPOSE,"з1"),(ACCEPT,60,30),(PICK,),(LEAVE,),(DELIVER,),(FINISH,),(DISMISS,)],
          ["T1","T2","T4","T6","T7","T8","T9","T10","T3"],"@end",
          "Замовлення доставлено, призначення знято, зміна закрита. Курʼєр у кінцевому стані; дії доступності й зайнятості по 2 рази.",
          entry=2,exit=2,assigned=None,offer=None,delivered=["з1"]),
        state_case(2,"Відмова від пропозиції","Базовий шлях","@start",
          [(ENTER,),(PROPOSE,"з1"),(REJECT,),(FINISH,),(DISMISS,)],
          ["T1","T2","T4","T5","T10","T3"],"@end",
          "Після відмови пропозицію знято й відновлено очікування. Після закриття зміни та звільнення — кінець.",
          entry=2,exit=2,offer=None,assigned=None,delivered=[]),
        state_case(3,"Перерва та повернення через історію","Базовий шлях","@start",
          [(ENTER,),(PAUSE,),(RESUME,),(FINISH,),(DISMISS,)],
          ["T1","T2","T11","T12","T10","T3"],"@end",
          "Повернення з перерви відновлює «Очікує замовлення». Зміна закривається; досягнуто кінця.",
          entry=2,exit=2,history=WAIT,delivered=[]),
        state_case(4,"Звільнення без зміни","Базовий шлях","@start",[(DISMISS,)],
          ["T1","T3"],"@end","Офлайн → кінець. Дії доступності й зайнятості не викликано.",entry=0,exit=0),
        state_case(5,"Зміна без замовлень","Базовий шлях","@start",[(ENTER,),(FINISH,),(DISMISS,)],
          ["T1","T2","T10","T3"],"@end","Очікування → офлайн → кінець. По одному виклику дій входу й виходу.",entry=1,exit=1),
        state_case(6,"Рівно достатньо часу","Граничний",OFFER,[(ACCEPT,40,40)],["T6"],TRAVEL,
          "Стан «Прямує до закладу»; з1 призначено, активну пропозицію знято.",assigned="з1",offer=None),
        state_case(7,"На хвилину менше","Граничний",OFFER,[(ACCEPT,39,40)],[None],OFFER,
          "Подію відхилено; стан і пропозиція з1 збережені, призначення немає.",offer="з1",assigned=None,entry=0,exit=0),
        state_case(8,"На хвилину більше","Граничний",OFFER,[(ACCEPT,41,40)],["T6"],TRAVEL,
          "Стан «Прямує до закладу»; з1 призначено.",assigned="з1",offer=None),
        state_case(9,"Перерва під час доставки","Прихований шлях",CLIENT,[(PAUSE,)],[None],CLIENT,
          "Подію відхилено. Призначення з1, стан і лічильники entry/exit не змінено.",assigned="з1",entry=0,exit=0),
        state_case(10,"Доставка без замовлення","Прихований шлях",WAIT,[(DELIVER,)],[None],WAIT,
          "Подію відхилено, доставлених замовлень немає; дії entry/exit не виконано.",delivered=[],entry=0,exit=0),
        state_case(11,"Пропозиція на перерві","Прихований шлях",BREAK,[(PROPOSE,"з1")],[None],BREAK,
          "Пропозицію не створено; стан і історію не змінено.",offer=None,history=WAIT,entry=0,exit=0),
        state_case(12,"Закриття зміни з пропозицією","Прихований шлях",OFFER,[(FINISH,)],[None],OFFER,
          "Подію відхилено; активна пропозиція з1 лишається.",offer="з1",entry=0,exit=0),
        state_case(13,"GPS у дорозі до закладу","Внутрішній",TRAVEL,[(GPS,50.25,28.66)],["I1"],TRAVEL,
          "GPS оновлено; стан, призначення й дії entry/exit незмінні.",gps=[50.25,28.66],assigned="з1",entry=0,exit=0),
        state_case(14,"Нова пропозиція після відмови","Пара переходів",WAIT,
          [(PROPOSE,"з1"),(REJECT,),(PROPOSE,"з2"),(ACCEPT,60,30)],["T4","T5","T4","T6"],TRAVEL,
          "Відмову з1 зафіксовано. Призначено лише з2. Пара T5 → T4 виконана.",
          assigned="з2",offer=None,entry=1,exit=2),
    ]
    def w(status,attempts,failed,timeouts=0,bonus=0,**rest):
        return {"status":status,"attempts":attempts,"failed":failed,"timeouts":timeouts,
                "bonus":bonus,"join_count":0 if status=="ESCALATED" else 1,
                "notifications":[] if status=="ESCALATED" else ["Курʼєр у дорозі",status],**rest}
    cases += [
        scenario(1,"Доставка з першої пропозиції",
          "Замовлення оплачене, заклад готує 6 хв, курʼєр їде до закладу 8 хв.",
          "Першу пропозицію прийнято, курʼєр дочекався злиття гілок; доставка 30 хв, клієнт на місці.",
          "Спочатку готова їжа; після прибуття курʼєра забір рівно один. DELIVERED, 2 сповіщення, бонусу немає.",
          "f7, f20, f24; AND: готовність → курʼєр",["accept"],6,8,30,True,
          w("DELIVERED",1,0,join_order=["ready","courier"])),
        scenario(2,"Доставка після відмови",
          "Замовлення оплачене; два кандидати; готовність через 15 хв.",
          "Перший відмовив, другий прийняв і прибув до готовності; клієнт на місці.",
          "Дві пропозиції, одна невдала. Забір після готовності; доставив другий курʼєр.",
          "f8, f9, f7, f20, f24; AND: курʼєр → готовність",["reject","accept"],15,4,30,True,
          w("DELIVERED",2,1,join_order=["courier","ready"])),
        scenario(3,"Три відмови після ранньої готовності",
          "Готовність надійшла через 1 хв; замовлення ще не призначене.",
          "Три курʼєри поспіль відмовляються.",
          "ESCALATED після 3 спроб. Токен готовності вилучено з AND-злиття, четвертої спроби й доставки немає.",
          "f8, f9, f10; terminate; скасування токена AND",["reject"]*3,1,4,30,True,
          w("ESCALATED",3,3,cancelled=1,join_order=["ready"])),
        scenario(4,"Клієнта немає на місці",
          "Замовлення оплачено; курʼєр прийняв, забрав і везе замовлення.",
          "Клієнт недоступний при прибутті, доставка до адреси тривала 23 хв.",
          "Замовлення повернуто; збережено й повідомлено RETURNED, повідомлення DELIVERED не надсилалося.",
          "f7, f21, f24; повідомлення m5",["accept"],5,4,23,False,w("RETURNED",1,0)),
        scenario(5,"Доставка довша за 45 хв",
          "Курʼєр забрав замовлення, клієнт на місці.",
          "Дія «Доставити замовлення» триває 46 хв.",
          "На 45-й хвилині один бонус; доставка продовжується й завершується DELIVERED.",
          "f18, f19; f7, f20, f24; PT45M",["accept"],3,4,46,True,
          w("DELIVERED",1,0,bonus=1,bonus_before_finish=True)),
        scenario(6,"Три тайм-аути до готовності",
          "Оплачене замовлення; заклад буде готовий через 10 хв.",
          "На кожну з трьох пропозицій немає відповіді впродовж 2 хв.",
          "Три невдалі спроби, ескалація на 6-й хвилині, очікування готовності скасовано. Нових пропозицій немає.",
          "f_reply, f_failed, f9, f10; PT2M; terminate",["timeout"]*3,10,4,30,True,
          w("ESCALATED",3,3,3,cancelled=1,ended_at=6,join_order=[])),
        scenario(7,"Прийняття після тайм-ауту",
          "Оплачене замовлення, двоє кандидатів.",
          "Перший не відповів за 2 хв, другий прийняв; доставка 20 хв, клієнт на місці.",
          "Перша пропозиція знята, друга прийнята. Одна невдала спроба і DELIVERED; дубль пропозиції не виник.",
          "f_reply, f_failed, f9, f7, f20, f24",["timeout","accept"],8,4,20,True,w("DELIVERED",2,1,1)),
    ]
    return cases


def write_csv(path):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f,delimiter=";"); w.writerow(COLS)
        for row in catalog():
            w.writerow(row[:7]+[json.dumps(v,ensure_ascii=False,separators=(",",":")) for v in row[7:]])


def local(el):
    return el.tag.rsplit("}",1)[-1]


def read_graph(path, validate=True):
    root=ET.parse(path).getroot()
    assert root.tag=="{"+NS["b"]+"}definitions"
    ident=[e.get("id") for e in root.iter() if e.get("id")]
    assert len(set(ident))==len(ident), "Nonunique BPMN/DI id"
    index={e.get("id"):e for e in root.iter() if e.get("id")}
    procs=root.findall("b:process",NS)
    owner={el.get("id"):p.get("id") for p in procs for el in p if el.get("id") and local(el)!="laneSet"}
    seq={el.get("id"):el for el in root.findall(".//b:sequenceFlow",NS)}
    msg={el.get("id"):el for el in root.findall(".//b:messageFlow",NS)}
    actors={e.get("id"):e.get("processRef") or e.get("id") for e in root.findall(".//b:participant",NS)}
    outgoing=defaultdict(list); incoming=defaultdict(list)
    for fid,f in seq.items():
        a,b=f.get("sourceRef"),f.get("targetRef")
        assert owner[a]==owner[b]==owner[fid]
        outgoing[a].append(fid); incoming[b].append(fid)
    for fid,f in msg.items():
        a,b=f.get("sourceRef"),f.get("targetRef")
        assert (actors.get(a) or owner[a])!=(actors.get(b) or owner[b]), fid
    if validate:
        for fid,f in msg.items(): assert local(index[f.get("messageRef")])=="message",fid
        flow_nodes=set(owner)-set(seq)
        lane_refs=[e.text for e in index["Process_Service"].findall(".//b:flowNodeRef",NS)]
        assert len(set(lane_refs))==len(lane_refs)
        assert set(lane_refs)=={k for k in flow_nodes if owner[k]=="Process_Service"}
        for k in flow_nodes:
            e=index[k]
            assert set(incoming[k])=={n.text for n in e.findall("b:incoming",NS)},k
            assert set(outgoing[k])=={n.text for n in e.findall("b:outgoing",NS)},k
            if local(e)=="boundaryEvent": assert owner[e.get("attachedToRef")]==owner[k]
            for d in e.findall("b:messageEventDefinition",NS):
                assert local(index[d.get("messageRef")])=="message"
            if e.get("default"): assert e.get("default") in outgoing[k]
        assert {s.get("bpmnElement") for s in root.findall(".//di:BPMNShape",NS)}==flow_nodes|set(actors)|{"Lane_Platform","Lane_Courier"}
        di={e.get("bpmnElement"):e for e in root.findall(".//di:BPMNEdge",NS)}
        assert set(di)==set(seq)|set(msg) and all(len(e.findall("dd:waypoint",NS))>=2 for e in di.values())
        for k in ("id_XOR1","id_XOR2","id_XOR3"):
            assert len(outgoing[k])==2 and index[k].get("default") in outgoing[k]
            assert sum(seq[f].find("b:conditionExpression",NS) is not None for f in outgoing[k])==1
        assert len(outgoing["id_PG1"])==2 and len(incoming["id_PG2"])==2
        assert len(incoming["id_XOR4"])==2 and outgoing["id_XOR4"]==["f24"]
        assert index["id_EE2"].find("b:terminateEventDefinition",NS) is not None
    return root,index,seq,msg,outgoing,incoming


def svg_text(data):
    root=ET.fromstring(data)
    assert all(local(el) not in {"script","foreignObject"} for el in root.iter())
    return tuple(" ".join("".join(e.itertext()).split()) for e in root.iter() if local(e)=="text")


def read_state(path):
    text=path.read_text()
    rx=r"(?m)^\s*(\S+) --> (\S+)\s*:\s*(T\d+)(?:\s+([^\s(]+)\([^)]*\))?"
    edges={i:(a,b,event or "") for a,b,i,event in re.findall(rx,text)}
    assert list(sorted(edges,key=lambda k:int(k[1:])))==TIDS[:-1]
    assert re.search(r"state .+ as НаЗміні \{\s*\[\*\] --> ОчікуєЗамовлення",text)
    assert "state H <<history>>" in text and ": I1 оновитиGPS()" in text
    assert edges["T11"]==(WAIT,BREAK,PAUSE) and edges["T12"]==(BREAK,"H",RESUME)
    fix={"НаЗміні":WAIT,"H":WAIT}
    edges={i:("@start" if a=="[*]" else a,"@end" if b=="[*]" else fix.get(b,b),event)
           for i,(a,b,event) in edges.items()}
    assert "[є вільний час]" in text
    by_event={(a,event):(i,b) for i,(a,b,event) in edges.items() if event}
    by_event[(TRAVEL,GPS)]=("I1",TRAVEL)
    assert len(by_event)==12 and set(e for _,e in by_event)==set(EVENTS)
    return edges,by_event


def eval_state(model, inp):
    edges,ev=model
    s={"state":inp["start"],"entry":0,"exit":0,"offer":inp.get("offer"),"assigned":inp.get("assigned"),
       "history":inp.get("history"),"gps":None,"delivered":[],"fired":[]}
    if s["state"]=="@start":
        s["state"]=edges["T1"][1];s["fired"].append("T1")
    for event,*args in inp["steps"]:
        cur=s["state"]; step=ev.get((cur,event))
        if step and step[0]=="T6" and args[0]<args[1]:
            step=None
        if not step:
            s["fired"].append(None);continue
        tid,dst=step
        if tid=="I1":
            s["gps"]=args
        else:
            if cur==WAIT:s["exit"]+=1
            if dst==WAIT:s["entry"]+=1
            if tid=="T4":
                assert s["offer"] is None
                s["offer"]=args[0]
            if tid=="T5":s["offer"]=None
            if tid=="T6":
                assert s["offer"] and s["assigned"] is None
                s["assigned"],s["offer"]=s["offer"],None
            if tid=="T9":
                assert s["assigned"]
                s["delivered"].append(s["assigned"]);s["assigned"]=None
            if tid=="T11":s["history"]=cur
            if tid=="T12":dst=s["history"]
            s["state"]=dst
        s["fired"].append(tid)
    return s


def evaluate_bpmn(graph, inp):
    _,index,seq,_,outgoing,incoming=graph
    out={"status":None,"attempts":0,"failed":0,"timeouts":0,"bonus":0,
         "join_count":0,"join_order":[],"notifications":[],"cancelled":0,"ended_at":0,
         "bonus_before_finish":False,"covered":[]}
    q=[]; tick=count(); joined=set(); answers=iter(inp["answers"]); active=False
    accepted=False;ready_at=None; bonus_at=None; finished_at=None
    def put(t,k,via=None): heappush(q,(t,next(tick),k,via))
    def go(fid,t): put(t,seq[fid].get("targetRef"),fid)
    def timer(k):
        value=index[k].find("b:timerEventDefinition/b:timeDuration",NS).text
        return int(re.fullmatch(r"PT(\d+)M",value)[1])
    def select(k,values):
        defaults=index[k].get("default")
        for f in outgoing[k]:
            c=seq[f].find("b:conditionExpression",NS)
            if c is None: continue
            name,op,right=c.text.split()
            ok=values[name]==(right=="true") if op=="=" else values[name]<int(right)
            if ok: return f
        return defaults
    assert timer("id_TR")==2 and index["id_TR"].get("cancelActivity")=="true"
    assert timer("id_TM")==45 and index["id_TM"].get("cancelActivity")=="false"
    put(0,"id_SE")
    for _ in range(250):
        if not q:break
        t,_,k,via=heappop(q)
        out["ended_at"]=t
        if via:out["covered"].append(via)
        if k=="id_PG2":
            assert via not in joined
            joined.add(via);out["join_order"].append("ready" if via=="f12" else "courier")
            if joined!=set(incoming[k]):continue
            joined.clear();out["join_count"]+=1
        if k=="id_T1":ready_at=t+inp["ready"]
        if k=="id_IE":
            assert ready_at is not None
            go("f12",max(t,ready_at));continue
        if k=="id_T2":
            assert not active and out["attempts"]<3
            active=True;out["attempts"]+=1
        if k=="id_T3":
            answer=next(answers)
            if answer=="timeout":
                put(t+timer("id_TR"),"id_TR");continue
            accepted=answer=="accept"
            assert answer in ("accept","reject")
            go("f6",t+1);continue
        if k=="id_TR":out["timeouts"]+=1
        if k=="id_TF":
            assert active
            active=False;out["failed"]+=1
        if k=="id_T4":
            assert active and accepted
            active=False;go("f13",t+inp["travel"]);continue
        if k in ("id_XOR1","id_XOR2","id_XOR3"):
            go(select(k,{"offerAccepted":accepted,"failedAttempts":out["failed"],"clientPresent":inp["present"]}),t)
            continue
        if k=="id_EE2":
            assert index[k].find("b:terminateEventDefinition",NS) is not None
            out["status"]="ESCALATED";out["cancelled"]=len(q)+len(joined)
            q.clear();joined.clear();break
        if k=="id_T7":out["notifications"].append("Курʼєр у дорозі")
        if k=="id_T8":
            finished_at=t+inp["delivery"]
            if inp["delivery"]>timer("id_TM"):
                put(t+timer("id_TM"),"id_TM")
            go("f17",finished_at);continue
        if k=="id_T12":
            assert bonus_at is None
            bonus_at=t;out["bonus"]+=1
        if k=="id_T9":out["status"]="DELIVERED"
        if k=="id_T11":out["status"]="RETURNED"
        if k=="id_EE":
            assert out["status"] in ("DELIVERED","RETURNED")
            out["notifications"].append(out["status"])
        for fid in outgoing[k]:go(fid,t)
    else:
        raise AssertionError("Nonterminating simulation")
    assert not active and not joined and not q
    out["bonus_before_finish"]=bonus_at is not None and bonus_at<finished_at
    return out


def rank(vectors):
    a=[list(map(Fraction,row)) for row in vectors]; r=0
    for col in range(len(a[0])):
        p=next((i for i in range(r,len(a)) if a[i][col]),None)
        if p is None: continue
        a[r],a[p]=a[p],a[r]
        q=a[r][col]; a[r]=[x/q for x in a[r]]
        for i in range(r+1,len(a)):
            q=a[i][col]
            a[i]=[x-q*y for x,y in zip(a[i],a[r])]
        r+=1
        if r==len(a):break
    return r


class Embedded(HTMLParser):
    def __init__(self): super().__init__();self.images=[]
    def handle_starttag(self, tag, attrs):
        src=dict(attrs).get("src","")
        if tag=="img" and src.startswith("data:image/svg+xml;base64,"):
            self.images.append(svg_text(base64.b64decode(src.split(",",1)[1])))


def check_inputs(src, dest):
    p=Path(src); md=(p/"Лабораторна_робота_10.md").read_text()
    assert (p/PUML).read_text().strip() in md and (p/PUML).read_bytes()==(dest/PUML).read_bytes()
    assert (p/STATE_SVG).read_bytes()==(dest/STATE_SVG).read_bytes()
    html=Embedded();html.feed((p/"Лабораторна_робота_10.html").read_text())
    assert len(html.images)==2
    for file in (BPMN_SVG,STATE_SVG): assert svg_text((p/file).read_bytes()) in html.images
    with (p/CSV).open(encoding="utf-8-sig",newline="") as f:
        orig=list(csv.DictReader(f,delimiter=";"))
    assert [x["ID"] for x in orig]==[f"ТК-{i:02d}" for i in range(1,14)]
    _,idx,_,msg,_,_=read_graph(p/"Лаб10_процес_виконання_замовлення.bpmn",validate=False)
    assert idx["id_EE2"].find("b:terminateEventDefinition",NS) is None
    assert "доставлено" in msg["m5"].get("name") and "id_TR" not in idx


def verify(p, original=None):
    root,ix,seq,msg,outgoing,_=g=read_graph(p/BPMN)
    all_types=Counter(local(e) for e in root.iter())
    assert all_types["participant"]==3 and all_types["lane"]==2
    assert sum(v for k,v in all_types.items() if k.lower().endswith("task"))==15
    assert (all_types["startEvent"],all_types["endEvent"],all_types["boundaryEvent"])==(2,4,2)
    assert all_types["parallelGateway"]==2 and all_types["exclusiveGateway"]==4
    assert len(seq)==30 and len(msg)==5
    svg=ET.parse(p/BPMN_SVG).getroot()
    graphic_ids={e.get("data-bpmn-id"):e for e in svg.iter() if e.get("data-bpmn-id")}
    assert set(graphic_ids)=={e.get("bpmnElement") for e in root.findall(".//di:BPMNShape",NS)+root.findall(".//di:BPMNEdge",NS)}
    for e in root.findall(".//di:BPMNEdge",NS):
        route=" ".join(f"{v.get('x')},{v.get('y')}" for v in e.findall("dd:waypoint",NS))
        assert any(c.get("points")==route for c in graphic_ids[e.get("bpmnElement")])
    if original:check_inputs(original,p)
    model=read_state(p/PUML)
    labels=svg_text((p/STATE_SVG).read_bytes())
    assert all(any(re.search(rf"\b{tid}\b",x) for x in labels) for tid in TIDS)
    with (p/CSV).open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f,delimiter=";"); rows=list(reader)
        assert reader.fieldnames==COLS
    assert len({r["ID"] for r in rows})==len(rows)==21
    assert all(all(r[c] for c in COLS) for r in rows)
    state_results={}; scenario_results={}; paths=[]
    for r in rows:
        inp=json.loads(r["Вхід_JSON"]); want=json.loads(r["Оракул_JSON"])
        result=eval_state(model,inp) if inp["model"]=="state" else evaluate_bpmn(g,inp)
        for k,v in want.items(): assert result[k]==v,(r["ID"],k,v,result[k])
        if inp["model"]=="state":
            state_results[r["ID"]]=result
            if r["Вид"]=="Базовий шлях":
                assert result["fired"][0]=="T1" and result["state"]=="@end"
                paths.append([result["fired"].count(i) for i in TIDS[:-1]])
        else:scenario_results[r["ID"]]=result
    used={i for s in state_results.values() for i in s["fired"] if i}
    allowed=model[1]
    assert used==set(TIDS) and len(paths)==rank(paths)==12-9+2==5
    expected_xor={f for k in ("id_XOR1","id_XOR2","id_XOR3","id_XOR4") for f in outgoing[k]}
    seen_xor=expected_xor & {f for s in scenario_results.values() for f in s["covered"]}
    assert seen_xor==expected_xor and len(seen_xor)==7
    assert 7*12-len(allowed)==72
    print("ЛАБОРАТОРНА 10  |  ПЕРЕВІРКА МОДЕЛЕЙ")
    print("BPMN/DI: 3 пули, 2 доріжки, 15 завдань, 30 + 5 потоків.")
    print("SVG і BPMN: координати потоків збігаються.")
    print("Між пулами лише потоки повідомлень; 2 таймери.")
    print("CSV: 21/21 випадків відповідають оракулам моделі.")
    print("UML: T1–T12 та I1 — 13/13; ранг базових шляхів = 5.")
    print("T6, 39 / 40 / 41 хв: відхилено / прийнято / прийнято.")
    print("Негативні тести: 4/4; прихованих пар у матриці: 72.")
    print("BPMN: 7/7 виходів XOR; обидва порядки AND-злиття.")
    for case,r in scenario_results.items():
        status={"DELIVERED":"доставлено","RETURNED":"повернено","ESCALATED":"оператор"}[r["status"]]
        print(f"{case}: {status}; спроб {r['attempts']}; тайм-аутів {r['timeouts']}; бонусів {r['bonus']}")
    print("С-03 і С-06: після ескалації активних токенів немає.")
    print("Перевірку завершено.")
    return {"state":state_results,"scenarios":scenario_results,"xor":sorted(seen_xor)}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir",type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument("--original-dir",type=Path)
    parser.add_argument("--write-csv",action="store_true")
    parser.add_argument("--json-report",type=Path)
    args=parser.parse_args()
    if args.write_csv:write_csv(args.source_dir/CSV)
    summary=verify(args.source_dir,args.original_dir)
    if args.json_report:args.json_report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
