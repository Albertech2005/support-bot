# Support Ticket Bot

Users DM the bot → a Forum Topic is created in the staff group  
Staff reply in the topic → reply is forwarded back to the user  
Staff close the topic → user is notified and the ticket is cleared  

---

## Setup

### 1. Staff Group Requirements
- Must be a **Supergroup** with **Topics (Forums) enabled**
  - Group Settings → Topics → On
- Add the bot to the group and make it an **Admin** with:
  - ✅ Manage Topics
  - ✅ Send Messages

### 2. Install dependencies
```bash
cd support-bot
pip install -r requirements.txt
```

### 3. Run
```bash
python bot.py
```

That's it. The bot saves ticket state to `tickets.json` in the same folder.

---

## How it works

| Action | Result |
|---|---|
| User DMs the bot | Bot replies with welcome message + creates a topic in the staff group |
| User sends more messages | Forwarded into their topic |
| Staff replies in the topic | Forwarded back to the user's DM |
| Staff closes the topic | User is notified, ticket is cleared (user can open a new one) |

---

## Deploy on Railway / Render / VPS
Just make sure Python 3.10+ is available and run `python bot.py`.  
No webhook needed — it runs on long-polling.
