"""Writes n8n_relay.json, the workflow to import into n8n:  python automation/build_workflow.py

    New Gmail email ─▶ Settings ─▶ Ask Relay (POST /api/inbound) ─▶ Has a reply? ─▶ Save as a Gmail draft

Every minute n8n checks the inbox for new, unread emails (not your own, not promotions) and sends each one to
Relay. Relay's agent drafts a reply, and n8n saves it as a draft in the same Gmail thread. Nothing is sent:
you read the draft in Gmail and press Send yourself, which is the human approval step.
"""
import json
import uuid
from pathlib import Path

NS = uuid.UUID("5d0f3a0e-6b3c-4c55-9a51-2c1f77d0e3a4")
def uid(name): return str(uuid.uuid5(NS, name))
MSG = "$('New Gmail email').item.json"
RELAY = "$('Ask Relay').item.json"

nodes = [
    {"id": uid("trigger"), "name": "New Gmail email", "type": "n8n-nodes-base.gmailTrigger", "typeVersion": 1.2,
     "position": [0, 300],
     "parameters": {"pollTimes": {"item": [{"mode": "everyMinute"}]}, "simple": False,
                    "filters": {"labelIds": ["INBOX"], "readStatus": "unread", "q": "-from:me -category:promotions -category:social"},
                    "options": {}}},
    {"id": uid("settings"), "name": "Settings", "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [220, 300],
     "parameters": {"assignments": {"assignments": [
         {"id": uid("relay_url"), "name": "relay_url", "type": "string",
          "value": "https://relay-PASTE-YOUR-NUMBER.us-west1.run.app"}]},           # <- your Relay API address
         "includeOtherFields": False, "options": {}}},
    {"id": uid("http"), "name": "Ask Relay", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [440, 300],
     "parameters": {"method": "POST", "url": "={{ $('Settings').item.json.relay_url }}/api/inbound",
                    "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                    "sendBody": True, "specifyBody": "json",
                    "jsonBody": ("={{ JSON.stringify({ message_id: " + MSG + ".id, thread_id: " + MSG + ".threadId, "
                                 "from_addr: " + MSG + ".from.value[0].address, from_name: " + MSG + ".from.value[0].name || '', "
                                 "subject: " + MSG + ".subject || '', body: " + MSG + ".text || '' }) }}"),
                    "options": {"timeout": 120000}}},
    {"id": uid("if"), "name": "Has a reply?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [660, 300],
     "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                   "conditions": [{"id": uid("cond"), "leftValue": "={{ $json.reply }}", "rightValue": "",
                                                   "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}}],
                                   "combinator": "and"}, "options": {}}},
    {"id": uid("draft"), "name": "Save as a Gmail draft", "type": "n8n-nodes-base.gmail", "typeVersion": 2.1,
     "position": [900, 280], "webhookId": uid("drafthook"),
     "parameters": {"resource": "draft", "subject": "={{ " + RELAY + ".subject }}", "emailType": "text",
                    "message": "={{ (" + RELAY + ".needs_human ? '[Relay: needs a person: ' + " + RELAY +
                               ".reasons.join('; ') + '. Edit before sending.]\\n\\n' : '') + " + RELAY + ".reply }}",
                    "options": {"threadId": "={{ " + RELAY + ".thread_id }}", "sendTo": "={{ " + RELAY + ".to }}"}}},
]


def link(*targets): return [[{"node": t, "type": "main", "index": 0} for t in targets]]


connections = {
    "New Gmail email": {"main": link("Settings")},
    "Settings": {"main": link("Ask Relay")},
    "Ask Relay": {"main": link("Has a reply?")},
    "Has a reply?": {"main": [[{"node": "Save as a Gmail draft", "type": "main", "index": 0}], []]},
}
workflow = {"name": "Relay: new Gmail emails become draft replies", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "timezone": "America/New_York"}, "pinData": {}, "active": False,
            "meta": {"templateCredsSetupCompleted": False}}
out = Path(__file__).with_name("n8n_relay.json")
out.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out}")
