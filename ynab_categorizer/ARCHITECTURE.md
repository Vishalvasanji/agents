# System Architecture

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                        GitHub Actions                        │
│                  (Runs daily at 6 AM)                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ Triggers
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   categorize_agent.py                        │
│  1. Fetch uncategorized transactions from YNAB              │
│  2. Load learned patterns from state file                   │
│  3. Call DeepSeek V3 via OpenRouter for categorization     │
│  4. Format batch message with suggestions                   │
│  5. Send to Slack channel                                   │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌──────────────┐  ┌──────────┐  ┌──────────────┐
│  YNAB API    │  │ OpenRouter│  │  Slack API   │
│              │  │ (DeepSeek)│  │              │
└──────────────┘  └──────────┘  └──────┬───────┘
                                        │
                                        │ Message appears
                                        ▼
                                ┌──────────────┐
                                │   You! ☕    │
                                │  (in Slack)  │
                                └──────┬───────┘
                                       │
                                       │ Reply: "approve all"
                                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   approval_handler.py                        │
│  (Optional - hosted on Railway/Fly.io)                      │
│  1. Receive Slack message event                             │
│  2. Parse approval command                                  │
│  3. Update transactions in YNAB                             │
│  4. Learn patterns for future categorization                │
│  5. Send confirmation back to Slack                         │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌──────────────┐  ┌──────────┐  ┌──────────────┐
│  YNAB API    │  │ State    │  │  Slack API   │
│  (Updated!)  │  │ File     │  │  (Reply)     │
└──────────────┘  └──────────┘  └──────────────┘
```

## Data Flow

### Morning Batch (Automated)
```
YNAB → categorize_agent → OpenRouter (AI) → Slack → You
```

### Approval (Interactive)
```
You → Slack → approval_handler → YNAB
                    ↓
               State File (Learning)
```

## Components

### categorize_agent.py
**Purpose**: Fetch and categorize transactions  
**Runs**: Daily via GitHub Actions (scheduled)  
**Dependencies**: YNAB API, OpenRouter API, Slack API  
**State**: Stores processed transaction IDs and learned patterns  

**Key Functions**:
- `get_uncategorized_transactions()` - Fetch from YNAB
- `categorize_with_ai()` - Call DeepSeek V3
- `format_slack_message()` - Create batch message
- `send_to_slack()` - Post to channel

### approval_handler.py
**Purpose**: Process your Slack approvals  
**Runs**: Continuously (Flask web server)  
**Dependencies**: YNAB API, Slack Events API  
**State**: Updates learned patterns, marks transactions processed  

**Key Functions**:
- `process_approval()` - Parse Slack commands
- `approve_all()` - Bulk update YNAB
- `change_category()` - Override AI suggestion
- `learn_pattern()` - Remember for next time

### State Management

**State File** (`ynab_agent_state.json`):
```json
{
  "processed_transactions": [
    "transaction-id-1",
    "transaction-id-2"
  ],
  "category_patterns": {
    "walmart": "Groceries",
    "starbucks": "Coffee",
    "shell": "Gas"
  },
  "pending_1234567": {
    "transactions": [...],
    "timestamp": "2026-01-28T06:00:00"
  }
}
```

**Persistence**:
- GitHub Actions: Uploads/downloads as artifact
- Local: Stored in `/tmp/`
- Hosted: Ephemeral (relearns patterns)

## API Integrations

### YNAB API
**Endpoints Used**:
- `GET /budgets/{id}/categories` - Fetch available categories
- `GET /budgets/{id}/transactions` - Fetch uncategorized
- `PATCH /budgets/{id}/transactions/{id}` - Update category

**Authentication**: Bearer token in header

### OpenRouter API
**Endpoint**: `POST /v1/chat/completions`  
**Model**: `deepseek/deepseek-chat` (DeepSeek V3)  
**Input**: Transaction list + category list + learned patterns  
**Output**: JSON array of categorization suggestions  

**Cost**: ~$0.001 per batch (10 transactions)

### Slack API
**Send Message**: `POST /chat.postMessage`  
**Receive Events**: Webhook to `/slack/events`  

**Events Subscribed**:
- `message.channels` - Channel messages
- `message.groups` - Private channel messages

## Deployment Options

### Option 1: GitHub Actions Only (No Hosting)
- ✅ Free
- ✅ Simple setup
- ❌ Manual approval in YNAB (no Slack replies)

### Option 2: GitHub Actions + Railway/Fly.io
- ✅ Full automation
- ✅ Slack reply support
- ✅ Learning enabled
- ⚠️ Requires hosting (free tier available)

### Option 3: Local Cron + Manual
- ✅ Full control
- ✅ Works anywhere
- ❌ Requires always-on computer

## Security Considerations

**Secrets Storage**:
- GitHub Secrets (encrypted at rest)
- Environment variables (never in code)
- State file (no sensitive data)

**API Tokens**:
- YNAB: Read transactions, write categories only
- Slack: Bot scope limited to posting/reading
- OpenRouter: Usage tracked, rate limited

**Best Practices**:
- Rotate tokens periodically
- Use `.env` for local testing (gitignored)
- Never commit secrets to repository
- Review GitHub Actions logs for leaks

## Scaling & Optimization

**Current Design**:
- Processes ~10 transactions/day
- Costs ~$0.001 per batch
- Takes ~5 seconds total

**If You Have More Transactions**:
- Batch size unlimited (API limits: YNAB 200/day)
- Cost scales linearly (~$0.0001/transaction)
- Consider parallel processing for 100+ txns

**Performance Tips**:
- Increase `days_back` to catch more at once
- Use category caching to reduce API calls
- Batch YNAB updates (single API call)

## Error Handling

**Retry Logic**:
- YNAB API: 3 retries with exponential backoff
- OpenRouter: 2 retries (fast fail)
- Slack: No retry (user can resend)

**Failure Modes**:
1. **API down**: Agent logs error, exits gracefully
2. **Invalid category**: Falls back to "Uncategorized"
3. **State file corrupt**: Rebuilds from scratch
4. **No transactions**: Success (nothing to do)

**Logging**:
- GitHub Actions: Full console output
- Flask: Access logs for debugging
- State: Timestamps for audit trail

---

This architecture is designed to be:
- ✅ **Simple**: Minimal moving parts
- ✅ **Cheap**: ~$0.03/month total cost
- ✅ **Reliable**: Graceful error handling
- ✅ **Extensible**: Easy to add features
