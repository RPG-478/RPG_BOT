# Discord RPG Bot - Koyeb Deployment Guide

## 📋 Pre-Deployment Checklist

### 1. Database Setup (Supabase)
Before deploying to Koyeb, you must set up the Supabase database:

#### Step 1: Create Supabase Project
1. Go to [Supabase](https://supabase.com)
2. Click "New Project"
3. Name your project (e.g., "discord-rpg-bot")
4. Set a strong database password
5. Select a region (recommended: Tokyo for JST timezone)
6. Wait for project provisioning to complete

#### Step 2: Get Connection Details
1. In your project dashboard, go to "Settings" → "API"
2. Copy the following:
   - **Project URL** (looks like: `https://xxxxx.supabase.co`)
   - **Anon/Public Key** (starts with `eyJ...`)

#### Step 3: Run Database Migrations
1. In Supabase, go to "SQL Editor"
2. Click "New Query"
3. **First**, run the base schema:
   - Open `attached_assets/supabase_schema_1762125002111.sql`
   - Copy the entire content
   - Paste into SQL Editor
   - Click "Run"

4. **Then**, run the raid HP recovery migration:
   - Open `migration_raid_hp_recovery.sql`
   - Copy the entire content
   - Paste into SQL Editor
   - Click "Run"

5. Verify tables were created:
   - Go to "Table Editor"
   - You should see: `players`, `player_raid_stats`, `raid_bosses`, `raid_contributions`, etc.

### 2. Discord Bot Setup

#### Step 1: Create Discord Application
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Name your bot (e.g., "RPG Bot")
4. Go to "Bot" section
5. Click "Reset Token" and copy the token **immediately** (you won't see it again)
6. Enable the following Privileged Gateway Intents:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent

#### Step 2: Bot Permissions
1. Go to "OAuth2" → "URL Generator"
2. Select scopes:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Select bot permissions:
   - ✅ Send Messages
   - ✅ Manage Messages
   - ✅ Embed Links
   - ✅ Read Message History
   - ✅ Add Reactions
   - ✅ Manage Channels (for adventure channels)
4. Copy the generated URL and invite bot to your server

## 🚀 Deploying to Koyeb

### Step 1: Prepare Your Repository
1. Push this project to GitHub (or GitLab/Bitbucket)
2. Make sure `.env` is in `.gitignore` (don't commit secrets!)
3. Verify `requirements.txt` contains all dependencies

### Step 2: Create Koyeb Service

#### Option A: Deploy from GitHub
1. Go to [Koyeb](https://www.koyeb.com)
2. Create new service
3. Select "GitHub" as deployment source
4. Connect your repository
5. Configure build settings:
   - **Build command**: Leave empty (no build needed)
   - **Run command**: `python main.py`
   - **Port**: 8000 (health check server)

#### Option B: Deploy via Docker
1. Create `Dockerfile` (if not exists):
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

2. In Koyeb, select "Docker" as deployment source
3. Set run command: `python main.py`

### Step 3: Configure Environment Variables
In Koyeb service settings, add these environment variables:

| Variable Name | Value | Example |
|--------------|-------|---------|
| `DISCORD_BOT_TOKEN` | Your bot token from Discord Developer Portal | `MTI3...` |
| `SUPABASE_URL` | Your Supabase project URL | `https://xxxxx.supabase.co` |
| `SUPABASE_KEY` | Your Supabase anon/public key | `eyJ...` |

⚠️ **Important**: Never commit these values to Git!

### Step 4: Deploy
1. Click "Deploy"
2. Wait for deployment to complete (2-3 minutes)
3. Check logs for "Logged in as [Bot Name]"

### Step 5: Verify Deployment
1. Go to your Discord server
2. Type `!start` in any channel
3. Bot should respond and create your adventure
4. Test raid system: Move to 500m and encounter a raid boss
5. Type `!raid_info` to see current boss

## 🔧 Post-Deployment Configuration

### Update Notification Channel ID
If you want raid defeat notifications in a different channel:

1. In Discord, enable Developer Mode (User Settings → Advanced → Developer Mode)
2. Right-click your notification channel → Copy ID
3. Edit `views.py` line 3903:
```python
notify_channel = bot.get_channel(YOUR_CHANNEL_ID_HERE)
```
4. Redeploy to Koyeb

### Health Check Endpoint
The bot runs a health check server on port 8000. Koyeb will ping:
- `http://your-bot.koyeb.app:8000/` (returns "OK")

This ensures the bot stays alive and Koyeb knows it's running.

## 🐛 Troubleshooting

### Bot Not Responding
1. Check Koyeb logs for errors
2. Verify environment variables are set correctly
3. Ensure bot token is valid (regenerate if needed)
4. Check bot permissions in Discord server

### Database Errors
1. Verify Supabase migrations ran successfully
2. Check Supabase URL and Key are correct
3. Test connection: In Supabase SQL Editor, run `SELECT * FROM players;`

### "Gateway connection lost"
1. This is normal - Discord occasionally reconnects
2. Bot should auto-reconnect within seconds
3. If persistent, check Koyeb instance isn't restarting repeatedly

### Raid Boss Not Appearing
1. Verify you're at exactly 500m, 1000m, 1500m, etc.
2. Check database: `SELECT * FROM raid_bosses;`
3. Ensure JST timezone is working (boss rotates at midnight JST)

## 📊 Monitoring

### Koyeb Dashboard
- Monitor CPU/Memory usage
- Check logs for errors
- View deployment history

### Supabase Dashboard
- Monitor database size
- Check query performance
- View real-time connections

## 🔄 Updating the Bot

### Code Changes
1. Push changes to Git repository
2. Koyeb auto-deploys (if enabled)
3. Or manually trigger deployment in Koyeb dashboard

### Database Schema Changes
1. Create new migration SQL file
2. Run in Supabase SQL Editor
3. Update code accordingly
4. Redeploy bot

## 💡 Best Practices

### Security
- ✅ Never commit `.env` files
- ✅ Rotate Discord bot token periodically
- ✅ Use Supabase Row Level Security (RLS) for production
- ✅ Enable Supabase API rate limiting

### Performance
- ✅ Monitor database query performance
- ✅ Use database indexes (already created in migrations)
- ✅ Consider connection pooling for high traffic

### Backups
- ✅ Enable Supabase automatic backups
- ✅ Export player data periodically
- ✅ Keep migration scripts in version control

## 📞 Support

### Common Issues
- **Bot offline**: Check Koyeb service status
- **Commands not working**: Verify bot permissions
- **Raid system broken**: Check database migrations

### Resources
- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [Supabase Documentation](https://supabase.com/docs)
- [Koyeb Documentation](https://www.koyeb.com/docs)

---

## ✅ Deployment Checklist

Before going live, verify:

- [ ] Supabase project created
- [ ] Database migrations executed (both SQL files)
- [ ] Discord bot created with correct intents
- [ ] Bot invited to server with proper permissions
- [ ] Environment variables configured in Koyeb
- [ ] Bot deployed and running on Koyeb
- [ ] Health check endpoint responding
- [ ] Bot responds to `!start` command
- [ ] Raid system working (test at 500m)
- [ ] Notification channel ID updated (if needed)
- [ ] Logs show no errors

**Status**: Once all checked, your bot is production-ready! 🎉
