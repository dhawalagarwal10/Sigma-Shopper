# Sigma Shopper

An agent-readable Razorpay merchant, plus an AI buyer that finds a real product on the web and actually buys it.

Built for Razorpay's Buildathon, Track 01: AI Growth & Agentic Commerce.

You tell it once what you want. It searches the web, checks the real price on the actual product page, and pays for it through a merchant API that has hard spend limits, requires a confirmed mandate before checkout, and logs every decision it makes.

## What this is for

Most stores can only be shopped by a human clicking around a website. AI shopping agents are becoming a real thing (NPCI's UAP and protocols like AP2, ACP, and x402 are all trying to standardize this), and merchants need a way to let an outside AI agent, one that knows nothing about their catalog, safely browse, decide, and pay, with no human clicking through the checkout, and without losing control of what that agent can spend.

This project has two parts:

1. A merchant backend where every action that touches money goes through the same guardrail code, no matter who's calling it.
2. An AI buyer that isn't tied to a fixed product list. Give it a goal in plain English and it goes and finds something real that matches, confirms the actual price, and checks out on its own.

Every guardrail decision, whether it passed or got blocked, gets written to an audit log, so the whole thing can be explained after the fact instead of just trusted.

## Architecture

```mermaid
flowchart TD
    subgraph Human["Human"]
        H1["Tells the buyer once: 'buy me X'"]
    end

    subgraph Buyer["ai_buyer/buyer.py (autonomous AI buyer)"]
        direction TB
        LLM["Claude tool-use loop"]
        WS["web_search: finds real listings"]
        WF["web_fetch: confirms the real price on the page"]
        LLM --> WS
        LLM --> WF
    end

    subgraph PathB["path_b/api.py (agent-readable API, FastAPI)"]
        direction TB
        EP1["/catalog"]
        EP2["/cart/{session}/add_custom"]
        EP3["/cart/{session}"]
        EP4["/checkout/{session}"]
        EP5["/status/{link_id}"]
        EP6["/audit/{session}"]
    end

    subgraph Core["merchant_core/ (shared by both paths)"]
        direction TB
        Cat["catalog.py"]
        Cart["cart.py: catalog items and web-sourced items"]
        Guard["guardrails.py: spend limit, action gating, mandate"]
        Audit["audit.py: append-only log"]
        RP["razorpay_client.py"]
    end

    subgraph Razorpay["Razorpay test mode"]
        Link["Payment link"]
    end

    subgraph Extra["path_a/ (human chat concierge, built but not demoed)"]
        Chat["Streamlit chat plus upsell agent"]
    end

    subgraph Dash["dashboard/audit_viewer.py"]
        DashUI["Live audit feed"]
    end

    H1 --> LLM
    LLM -- "HTTP calls" --> PathB
    PathB --> Core
    Core --> RP --> Link
    Link -- "poll /status" --> PathB
    Core --> Audit
    Audit -.-> Dash
    Chat -. "in-process, same guardrails" .-> Core
```

Both paths (the AI buyer's API and the human chat concierge) call into the same `merchant_core`, so neither one can skip a guardrail by going through the other. The spend limit, the mandate requirement, and the audit log only exist once, not once per path.

## The guardrails

| Guardrail | What it does | Where |
|---|---|---|
| Spend limit | Hard ceiling (`MAX_SESSION_SPEND`, 50 rupees in test mode). Anything over it gets blocked before it's added to the cart. | `guardrails.check_spend_limit` |
| Action gating | Checkout, adding a large quantity, and discounts always need an explicit mandate, not just an instruction in a prompt. | `guardrails.gate_action` |
| Mandate | A `Mandate` object (items, total, reason, timestamp) has to exist before any payment link gets created. There's no path to checkout without one. | `guardrails.create_mandate` |

Every check gets written to `data/audit_log.jsonl` with a plain-English reason, and you can watch it live in the dashboard.

## Project structure

```
Razorpay/
├── merchant_core/          # shared by both paths
│   ├── catalog.py
│   ├── cart.py             # catalog items and web-sourced (custom) items
│   ├── guardrails.py
│   ├── audit.py
│   └── razorpay_client.py
├── path_b/
│   └── api.py              # agent-readable REST API
├── ai_buyer/
│   └── buyer.py            # the web-search-driven buyer
├── dashboard/
│   └── audit_viewer.py     # live audit trail
├── path_a/                 # human chat concierge, see "scope" below
│   ├── agent.py
│   ├── tools.py
│   └── chat_app.py
├── data/
│   ├── catalog.json
│   └── audit_log.jsonl     # created at runtime
├── config.py
├── .env.example
└── requirements.txt
```

## Setup

```bash
git clone <your-repo-url>
cd Razorpay
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env        # then fill in real keys
```

`.env` needs:

```
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
```

One thing to do before running the buyer: turn on the `web_search` tool for your Anthropic org at console.anthropic.com. It's a separate toggle from the API key just working. `web_fetch` is a beta feature, but the code already sends the required header, so nothing to enable for that one.

## Running it

Start the API:
```bash
uvicorn path_b.api:app --reload --port 8000
```

Run the buyer:
```bash
python -m ai_buyer.buyer
```
It asks once, "What do you want me to buy?", then runs on its own from there: searches, checks a real price, adds to cart, checks out, prints a real Razorpay test-mode payment link.

Watch the audit trail live:
```bash
streamlit run dashboard/audit_viewer.py --server.port 8502
```

The human chat concierge (not part of the demo, see scope below):
```bash
streamlit run path_a/chat_app.py
```

## Completing a test-mode payment

Razorpay's test mode doesn't support scanning the UPI QR code, that only works in live mode. To actually pay the link:

- UPI: type `success@razorpay` (or `failure@razorpay` to test a decline) as the UPI ID, don't scan the QR.
- Card: `4111 1111 1111 1111`, any future expiry, any CVV, then click "Success" on the mock bank page.

The buyer polls for up to 5 minutes before giving up.

## Showing the failure case

```bash
python -m ai_buyer.buyer --simulate-failure
```
Skips real payment completion and forces the timeout path, so you can see the agent clear its cart and retry from scratch, with all of it logged.

## Scope of this submission

This repo also has `path_a/`, a human-facing chat concierge (Claude plus Streamlit) built on the same `merchant_core`. It's there to show the guardrail layer works the same way for a human storefront as it does for a machine-to-machine API.

It's not part of the demo. The track allows either direction (growth agent, or agent-readable merchant), and we decided to go deep on the AI buyer instead of splitting time across both.

## Known limitations

- Payment authorization is the one step that still needs a human or a live test instrument to act. No test-mode setup, including this one, can make that part zero-touch. Real AP2/ACP flows have the same limitation.
- The price the agent uses is only as good as what `web_fetch` can actually read off the page. It does confirm the price before buying, but a page that's heavily JS-rendered could still mislead it occasionally.
- The agent doesn't currently prefer known marketplaces over smaller independent sites if the smaller site's price looks better. Worth knowing if the retailer's reliability matters as much as the price does for your use case.

## Built with

FastAPI, Streamlit, Anthropic Claude (`claude-haiku-4-5-20251001`) with the `web_search` and `web_fetch` tools, Razorpay's test-mode API, Pydantic.
