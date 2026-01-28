# YNAB Slack Agent - Quick Start 🚀

Your AI-powered YNAB categorization agent is ready! Here's how to get it running:

## What You're Getting

- **DeepSeek V3** for ultra-cheap AI categorization (~$0.03/month)
- **Batch mode** that runs while you sleep (6 AM default)
- **Slack integration** for one-tap approvals
- **Learning system** that remembers your preferences
- **GitHub Actions** for automated scheduling

## 5-Minute Setup

### 1. Get API Keys (5 min)

**YNAB Token:**
- https://app.ynab.com/settings/developer → "New Token"

**OpenRouter Key:**
- https://openrouter.ai/keys → Create key, add $5 credit

**Slack Bot:**
- https://api.slack.com/apps → "Create New App"
- OAuth & Permissions → Add scopes: `chat:write`, `channels:history`, `channels:read`
- Install to workspace
- Copy Bot Token (xoxb-...)

### 2. Deploy to GitHub (2 min)

```bash
# Create new repo on GitHub
# Then:
git init
git add .
git commit -m "Initial YNAB agent"
git remote add origin YOUR_GITHUB_REPO_URL
git push -u origin main
```

### 3. Add Secrets (2 min)

Go to your repo → Settings → Secrets and variables → Actions

Add these secrets:
- `YNAB_API_TOKEN` = your YNAB token
- `YNAB_BUDGET_ID` = `last-used`
- `SLACK_BOT_TOKEN` = xoxb-...
- `SLACK_CHANNEL` = `#ynab-transactions` (create this channel)
- `OPENROUTER_API_KEY` = your OpenRouter key

### 4. Test It! (1 min)

1. Go to Actions tab → "YNAB Categorization Agent"
2. Click "Run workflow"
3. Check your Slack channel!

## Daily Workflow

**Every morning at 6 AM:**
1. Wake up ☕
2. Check Slack 📱
3. See uncategorized transactions
4. Reply: `approve all`
5. Done! ✅

**That's it!** Your transactions are categorized while you're making coffee.

## Commands

In Slack, reply to the transaction batch:

- `approve all` → Approve everything
- `approve 1,3,5` → Approve specific ones
- `1: Dining` → Change category
- `skip` → Ignore for now

## Costs

- **DeepSeek V3**: ~$0.001 per batch = **$0.03/month**
- **GitHub Actions**: Free (2000 min/month)
- **Slack**: Free
- **Total**: ~$0.03/month 🎉

## Files Explained

- `categorize_agent.py` - Fetches transactions, calls AI, sends to Slack
- `approval_handler.py` - Handles your Slack replies (optional, needs hosting)
- `.github/workflows/categorize.yml` - Runs agent daily at 6 AM
- `test_setup.py` - Test your API keys before deploying
- `README.md` - Full documentation

## Next Steps

1. **Test locally** (optional):
   ```bash
   cp .env.example .env
   # Edit .env with your keys
   pip install -r requirements.txt
   python test_setup.py
   ```

2. **Adjust schedule**: Edit `.github/workflows/categorize.yml` for your timezone

3. **Host approval handler** (optional): Deploy to Railway/Fly.io for automatic approvals

4. **Customize**: Add emojis, change model, adjust lookback period

## Troubleshooting

**No transactions appearing?**
- Make sure you have uncategorized transactions in YNAB
- Check GitHub Actions logs for errors

**Slack not working?**
- Verify bot is in the channel
- Check token starts with `xoxb-`

**AI suggestions wrong?**
- They'll improve as you approve! The agent learns from you
- You can always override with `1: Correct Category`

## Need Help?

- Check `README.md` for full documentation
- Open an issue on GitHub
- The code is simple Python - customize it!

---

**You're all set!** Push to GitHub, run the workflow, and enjoy never opening YNAB again. 🎊
