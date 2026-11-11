# Connecting Relay to Gmail with n8n

New emails in a Gmail inbox go to Relay; Relay's draft comes back as a **Gmail draft** in the same thread.
Nothing is sent automatically: reading the draft and pressing **Send** in Gmail is the approval step.

Use a separate demo Gmail account if you can, so test emails and drafts stay out of your own inbox.

## 1. A secret for the connection

Make one in PowerShell and copy it:
```powershell
[guid]::NewGuid().ToString() + [guid]::NewGuid().ToString()
```
Put it in Relay's `deploy.env.yaml` as `INBOUND_SECRET: "..."` and redeploy Relay (see DEPLOY.md).

## 2. Import the workflow

1. n8n → **Overview → Create → Import from file** → choose `automation/n8n_relay.json`.
2. **Settings** node: set `relay_url` to your Relay API address (no `/` at the end).
3. **Ask Relay** node → **Credential** → **Create new** (Header Auth): **Name** `X-Webhook-Secret`, **Value** the secret from step 1.
4. **New Gmail email** and **Save as a Gmail draft** nodes: pick your Gmail credential (or create one for the
   demo account with **Sign in with Google**).
5. **Publish** (top right).

## 3. Try it

From another email address, send the demo inbox something like *"Where is my order?"*. Within about a minute
a draft reply appears in that thread in Gmail.

To have your test address act as one of Fernwood's customers (so the agent finds real orders), add to
`deploy.env.yaml` and redeploy:
```yaml
GMAIL_AS: "your.test.address@gmail.com=noah.tanaka1286@example.com"
```
