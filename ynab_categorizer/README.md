# YNAB Slack Categorization Agent 🤖

An AI-powered agent that automatically categorizes your YNAB transactions and sends them to Slack for easy approval. Wake up, check Slack, approve with a single message, and you're done!

## Features

✨ **Batch Mode** - Get all uncategorized transactions in one message  
🧠 **AI-Powered** - Uses DeepSeek V3 (super cheap!) to intelligently suggest categories  
📚 **Learning** - Remembers your approvals and gets better over time  
💬 **Slack Native** - Approve with simple commands: `approve all`, `1: Groceries`, etc.  
⏰ **Automated** - Runs on schedule via GitHub Actions while you sleep  
💰 **Cost Effective** - Uses DeepSeek V3 (~$0.001 per batch of transactions)

## How It Works

1. **6 AM Daily** (configurable): GitHub Action runs `categorize_agent.py`
2. **Fetches** uncategorized YNAB transactions from the past week
3. **AI Categorizes** each transaction using learned patterns + smart analysis
4. **Sends to Slack** in batch format with suggested categories
5. **You Approve** via simple Slack commands
6. **Updates YNAB** and learns from your choices

## Setup Instructions

### 1. Get Your API Keys

#### YNAB Personal Access Token
1. Go to https://app.ynab.com/settings/developer
2. Click "New Token"
3. Copy the token (starts with `ynab-`)

#### OpenRouter API Key
1. Go to https://openrouter.ai/keys
2. Create a new API key
3. Add $5 credit (will last months with DeepSeek V3)

#### Slack Bot Token
1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name it "YNAB Agent" and select your workspace
4. Go to "OAuth & Permissions"
5. Add these Bot Token Scopes:
   - `chat:write`
   - `channels:history`
   - `channels:read`
   - `groups:history`
   - `groups:read`
6. Install app to workspace
7. Copy the "Bot User OAuth Token" (starts with `xoxb-`)
8. Go to "Event Subscriptions"
   - Enable Events
   - Subscribe to bot events: `message.channels`, `message.groups`
   - Add Request URL (see step 3 below for hosting)

### 2. Fork This Repository

1. Fork this repo to your GitHub account
2. Go to Settings → Secrets and variables → Actions
3. Add these secrets:
   - `YNAB_API_TOKEN`: Your YNAB token
   - `YNAB_BUDGET_ID`: Your budget ID (or use `last-used`)
   - `SLACK_BOT_TOKEN`: Your Slack bot token (xoxb-...)
   - `SLACK_CHANNEL`: Channel to post to (e.g., `#ynab-transactions`)
   - `OPENROUTER_API_KEY`: Your OpenRouter API key

#### Finding Your Budget ID (Optional)
Run this command with your YNAB token:
```bash
curl -H "Authorization: Bearer YOUR_YNAB_TOKEN" https://api.ynab.com/v1/budgets
```
Or just use `last-used` which works for most people.

### 3. Host the Approval Handler (Optional but Recommended)

The approval handler needs to be publicly accessible for Slack to send events to it. Options:

#### Option A: Railway (Free Tier, Easiest)
1. Go to https://railway.app
2. "New Project" → "Deploy from GitHub repo"
3. Select your forked repo
4. Add these environment variables:
   - `YNAB_API_TOKEN`
   - `YNAB_BUDGET_ID`
   - `SLACK_BOT_TOKEN`
5. Copy the public URL
6. In Slack app settings, set Request URL to: `https://YOUR-RAILWAY-URL.railway.app/slack/events`

#### Option B: Fly.io (Free Tier)
1. Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
2. Run: `fly launch` in the repo directory
3. Set environment variables: `fly secrets set YNAB_API_TOKEN=...`
4. Deploy: `fly deploy`
5. Update Slack Request URL

#### Option C: Manual Approval (No Hosting Needed)
If you don't want to host the approval handler, you can still use the agent! Just:
- Reply to the Slack message with transaction numbers
- Then manually run: `python categorize_agent.py --approve 1,2,3`
- Or update YNAB manually based on the suggestions

### 4. Set Your Timezone

Edit `.github/workflows/categorize.yml` and change the cron schedule:

```yaml
schedule:
  # 6 AM Central Time = 12:00 PM UTC
  - cron: '0 12 * * *'
```

Time zone conversions:
- **Eastern (EST)**: 6 AM = `0 11 * * *`
- **Central (CST)**: 6 AM = `0 12 * * *`
- **Mountain (MST)**: 6 AM = `0 13 * * *`
- **Pacific (PST)**: 6 AM = `0 14 * * *`

Or use https://crontab.guru to calculate your time

### 5. Test It!

#### Test Locally
```bash
# Set environment variables
export YNAB_API_TOKEN="your_token"
export YNAB_BUDGET_ID="last-used"
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_CHANNEL="#ynab-transactions"
export OPENROUTER_API_KEY="your_key"

# Install dependencies
pip install -r requirements.txt

# Run the agent
python categorize_agent.py
```

#### Test on GitHub
1. Go to Actions tab in your repo
2. Select "YNAB Categorization Agent"
3. Click "Run workflow"
4. Check your Slack!

## Usage

### Approving Transactions in Slack

When you get the morning batch message:

```
📋 Good morning! You have 5 uncategorized transaction(s):

1. 🛒 Walmart - $47.23
   → Groceries 🟢
   2026-01-27

2. ⛽ Shell - $52.10
   → Gas 🟢
   2026-01-27

...

To approve:
• Reply `approve all` to categorize everything
• Reply `approve 1,3,5` to approve specific numbers
• Reply `1: Groceries` to change category for transaction 1
• Reply `skip` to ignore for now
```

**Commands:**
- `approve all` - Approve all suggestions ✅
- `approve 1,3,5` - Approve specific transactions
- `1: Dining` - Change transaction 1 to "Dining" category
- `skip` - Skip this batch (will appear again tomorrow)

### The Agent Learns!

Every time you approve a transaction, the agent remembers:
- "Walmart" → "Groceries"
- "Starbucks" → "Coffee"
- etc.

Next time it sees these merchants, it'll categorize them automatically with high confidence! 🎯

## Cost Analysis

**DeepSeek V3 Pricing:**
- Input: $0.27 per 1M tokens
- Output: $1.10 per 1M tokens

**Typical batch (10 transactions):**
- ~2,000 input tokens
- ~500 output tokens
- Cost: **$0.001** per batch

**Monthly cost for daily batches:** ~$0.03 (3 cents!)

Compare to Claude Sonnet: ~$0.20 per batch = $6/month

## Customization

### Change the Model

Edit `categorize_agent.py`:
```python
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
```

Other good cheap models:
- `google/gemini-flash-1.5` - Fast and cheap
- `meta-llama/llama-3.1-70b-instruct` - Great quality
- `anthropic/claude-3-haiku` - Best quality/cost for this task

### Adjust Schedule

Edit `.github/workflows/categorize.yml` cron expression

### Change Lookback Period

Edit `categorize_agent.py`:
```python
transactions = self.get_uncategorized_transactions(days_back=7)  # Change to 3, 14, etc.
```

### Add More Emojis

Edit the `get_category_emoji()` method in `categorize_agent.py`

## Troubleshooting

### "No uncategorized transactions found"
- Check that transactions exist in YNAB
- Verify `YNAB_BUDGET_ID` is correct
- Make sure transactions aren't already categorized

### "Slack API error"
- Verify bot token starts with `xoxb-`
- Check bot is added to the channel
- Ensure channel name includes # (e.g., `#ynab-transactions`)

### "OpenRouter API error"
- Check API key is valid
- Ensure you have credits ($5 minimum)
- Verify model name is correct

### GitHub Action fails
- Check all secrets are set correctly
- View logs in Actions tab
- Make sure state artifact is uploading/downloading

## Architecture

```
┌─────────────────────┐
│   GitHub Actions    │  ← Runs on schedule
│   (categorize.yml)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  categorize_agent   │  ← Fetches transactions
│       .py           │  ← Calls AI
└──────────┬──────────┘  ← Sends to Slack
           │
           ▼
┌─────────────────────┐
│   OpenRouter API    │  ← DeepSeek V3 model
│  (DeepSeek V3)      │
└─────────────────────┘
           │
           ▼
┌─────────────────────┐
│       Slack         │  ← You approve here
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  approval_handler   │  ← Listens for replies
│       .py           │  ← Updates YNAB
└──────────┬──────────┘  ← Learns patterns
           │
           ▼
┌─────────────────────┐
│     YNAB API        │  ← Categories updated!
└─────────────────────┘
```

## Files

- `categorize_agent.py` - Main agent that fetches and categorizes transactions
- `approval_handler.py` - Flask app that handles Slack interactions
- `.github/workflows/categorize.yml` - GitHub Actions workflow for scheduling
- `requirements.txt` - Python dependencies
- `README.md` - This file

## Future Enhancements

Ideas for extending the agent:

- 📊 Weekly spending summary
- 🚨 Budget alerts ("You're 80% through dining budget!")
- 📈 Trend analysis ("You're spending 20% more on groceries this month")
- 🔄 Auto-handle recurring transactions
- 💡 Suggest budget adjustments based on patterns
- 🎯 Split transaction handling

## License

MIT - Do whatever you want with it!

## Contributing

PRs welcome! This is a simple agent designed to remove friction from YNAB categorization.

---

**Questions?** Open an issue or modify the code - it's yours now! 🚀
