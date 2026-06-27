import json
import sys
import uuid
import urllib.request

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from e2e_client import find_custom, all_text
from test_data import DIAGNOSTIC_CORRECT_ANSWERS

uri = "http://localhost:5005/webhooks/rest/webhook"
parse_uri = "http://localhost:5005/model/parse"
sender = "debug-" + uuid.uuid4().hex[:6]


def send(msg):
    data = json.dumps({"sender": sender, "message": msg}).encode("utf-8")
    req = urllib.request.Request(
        uri, data=data, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def parse(text):
    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        parse_uri, data=data, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


for t in DIAGNOSTIC_CORRECT_ANSWERS[5:8]:
    p = parse(t)
    print("NLU:", t[:60], "->", p["intent"]["name"], p["intent"]["confidence"])

send("oi")
send("sim")
for i, a in enumerate(DIAGNOSTIC_CORRECT_ANSWERS[:6], 1):
    msgs = send(a)
    d = find_custom(msgs, "diagnostic")
    idx = d.get("index") if d else None
    print(f"after answer {i}: diagnostic index={idx}")
    if i == 6:
        print("FULL TEXT:", all_text(msgs)[:300])
