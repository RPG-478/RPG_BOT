# Discord RPG Bot - Project Documentation

## Project Overview
A Japanese text-based RPG Discord bot featuring a complete raid boss system with cooperative multiplayer battles. Players explore a 100-floor dungeon with weekday-rotating raid bosses at every 500m milestone.

## Current Status
✅ **PRODUCTION READY** - All raid system features implemented and tested
✅ **KOYEB DEPLOY READY** - Configured for Koyeb deployment (Replit 24/7 is ToS violation)

### Last Updated
November 3, 2025

## Recent Changes
### 500m Raid Boss Optional Encounter (November 3, 2025)
- **FIXED**: 500m地点でレイドボスが強制出現していた問題を修正
- レイドボスは**オプションボタン**経由で挑戦可能に変更
- 500m地点では通常イベント（商人、鍛冶屋、ストーリー、宝箱、敵）も発生
- 追加: `RaidOptionButton`ビュー - "レイドボスに挑戦"/"続けて探索"ボタン
- TreasureView, TrapChestViewを修正 - イベント終了後にレイドボスボタン表示
- 通常イベントとレイドボスの両立が可能になりました

### Koyeb Deployment Configuration (November 3, 2025)
- Configured project for Koyeb deployment (Replit 24/7 violates ToS)
- Added `Procfile` for Koyeb worker process
- Added `runtime.txt` specifying Python 3.11
- Created `KOYEB_DEPLOY.md` with deployment instructions
- Created `IMPLEMENTATION_STATUS.md` documenting all implemented features
- Set up dummy workflow for Replit system compliance

### Raid HP Recovery System (November 2, 2025)
- Implemented 6-hour automatic HP recovery system
- Added upgradeable recovery rate (`!raid_recovery` command, 4PT cost)
- Recovery rate starts at 10 HP/6h, increases by +5 per upgrade
- Automatic recovery applied when player accesses raid stats

### Defeat Notification System (November 2, 2025)
- Added special channel notifications (ID: 1424712515396305007)
- Shows contributors with 5%+ damage contribution
- Displays total damage, user mentions, and contribution percentages
- Triggered automatically when raid boss is defeated

### Raid Stats Persistence (November 2, 2025)
- Modified `!reset` command to preserve `player_raid_stats` table
- Raid progression is now permanent across resets
- Players keep raid HP, ATK, DEF, and all upgrades

## Project Architecture

### Core System
- **Discord Bot**: discord.py library with button-based UI
- **Database**: Supabase (PostgreSQL) with automatic schema
- **Timezone**: JST (Japan Standard Time) for daily boss rotation
- **Health Check**: HTTP server on port 8000 for Koyeb monitoring

### Raid System Design
```
┌─────────────────────────────────────────┐
│         Weekday Boss Rotation           │
│  Monday-Sunday: 7 unique raid bosses    │
│  Auto-reset at midnight JST             │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│      Shared Boss HP (Global)            │
│  All players attack same boss instance  │
│  HP depletes across entire server       │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│    Player Raid Stats (Individual)       │
│  - raid_hp / raid_max_hp                │
│  - raid_atk / raid_def                  │
│  - raid_hp_recovery_rate                │
│  - Separate from normal stats           │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│       Contribution Tracking             │
│  - Damage dealt per player              │
│  - Attack count                         │
│  - Rewards based on contribution %      │
└─────────────────────────────────────────┘
```

### Key Features
1. **Separate Stat System**: Raid stats (HP/ATK/DEF) independent from adventure stats
2. **Permanent Progress**: `!reset` preserves raid stats, never deleted
3. **Auto HP Recovery**: 6-hour intervals with upgradeable rate
4. **Contribution Rewards**: Rewards scale with damage contribution
5. **Social Notifications**: Public announcements for top contributors

## File Structure

### Core Files
- `main.py` - Bot entry point, command handlers, event loops
- `db.py` - Database operations (Supabase client)
- `views.py` - Discord UI components (buttons, embeds)
- `raid_system.py` - Raid boss data, calculations, utilities

### Supporting Files
- `config.py` - Environment configuration
- `game.py` - Adventure/exploration mechanics
- `story.py` - Story events and narrative
- `death_system.py` - Death mechanics and penalties
- `death_stories.py` - Death flavor text
- `titles.py` - Achievement/title system
- `debug_commands.py` - Admin/debug utilities

### Documentation
- `README.md` - Setup instructions, raid system documentation
- `DEPLOYMENT_GUIDE.md` - Koyeb deployment step-by-step guide
- `migration_raid_hp_recovery.sql` - Database migration for HP recovery
- `requirements.txt` - Python dependencies

### Database Schema Location
- `attached_assets/supabase_schema_1762125002111.sql` - Base schema

## Environment Variables Required

```env
DISCORD_BOT_TOKEN=<Discord bot token>
SUPABASE_URL=<Supabase project URL>
SUPABASE_KEY=<Supabase anon/public key>
```

## Database Tables

### player_raid_stats (Core Raid Data)
- `user_id` - Discord user ID
- `raid_hp` / `raid_max_hp` - Current/max HP for raids
- `raid_atk` / `raid_def` - Raid combat stats
- `raid_hp_recovery_rate` - HP recovered every 6 hours
- `raid_hp_recovery_upgrade` - Upgrade level for recovery
- `last_hp_recovery` - Timestamp of last recovery
- Upgrade levels for ATK/DEF/HP

### raid_bosses (Global Boss State)
- `boss_id` - Weekday-based boss identifier
- `current_hp` - Shared HP across all players
- `max_hp` - Starting HP
- `total_damage` - Cumulative damage from all players
- `is_defeated` - Defeat status
- `defeated_at` - Timestamp of defeat

### raid_contributions (Player Contributions)
- `boss_id` + `user_id` - Composite key
- `damage_dealt` - Total damage by this player
- `attacks_made` - Number of attacks
- `created_at` / `updated_at` - Timestamps

## Important Implementation Details

### HP Recovery System
- **Function**: `check_and_apply_hp_recovery()` in `db.py`
- **Trigger**: Called automatically when fetching player raid stats
- **Logic**: 
  1. Calculate hours elapsed since `last_hp_recovery`
  2. If ≥6 hours, calculate recovery cycles (hours ÷ 6)
  3. Apply recovery: `new_hp = min(max_hp, current_hp + (rate × cycles))`
  4. Update `last_hp_recovery` to account for applied cycles

### Defeat Notification
- **Function**: `handle_raid_victory()` in `views.py` (line 3856)
- **Channel**: Hardcoded to 1424712515396305007
- **Filter**: Contributors with ≥5% of total damage
- **Display**: Top 10 contributors (if more than 10 qualify)
- **Error Handling**: Graceful failure if channel not found

### Reset Protection
- **Function**: `delete_player()` in `db.py` (line 85)
- **Behavior**: Deletes ONLY from `players` table
- **Preserved**: `player_raid_stats`, `raid_contributions`, `raid_bosses`
- **Reason**: Raid progression is permanent by design

## Raid Commands

| Command | Aliases | Cost | Description |
|---------|---------|------|-------------|
| `!raid_info` | `!ri` | Free | Show current boss info |
| `!raid_upgrade` | `!ru` | Free | Show raid stats & upgrades |
| `!raid_atk` | `!ra` | 3PT | +5 attack |
| `!raid_def` | `!rd` | 3PT | +3 defense |
| `!raid_hp` | `!rh` | 5PT | +50 max HP |
| `!raid_heal` | `!rhe` | 1PT | Full HP restore |
| `!raid_recovery` | `!rr` | 4PT | +5 HP/6h recovery |

## Raid Boss Schedule (JST)

| Day | Boss | Icon | Element |
|-----|------|------|---------|
| Monday | 古代の巨像ゴーレム | 🗿 | Earth |
| Tuesday | 炎竜インフェルノ | 🐉 | Fire |
| Wednesday | 深海の支配者クラーケン | 🦑 | Water |
| Thursday | 魔界将軍ベリアル | 👹 | Dark |
| Friday | 不死王リッチロード | 💀 | Undead |
| Saturday | 雷神タイタン | ⚡ | Lightning |
| Sunday | 不死鳥フェニックス | 🔥 | Fire/Holy |

## Deployment Notes

### Koyeb-Specific Configuration
- Bot runs continuously (not serverless)
- Health check endpoint: `0.0.0.0:8000`
- Auto-restart on crash
- Environment variables managed via Koyeb dashboard

### Database Migration Steps
1. Run `supabase_schema_1762125002111.sql` first (base tables)
2. Run `migration_raid_hp_recovery.sql` second (HP recovery fields)
3. Verify with `SELECT * FROM player_raid_stats;`

### Testing Checklist
- [ ] Bot connects to Discord Gateway
- [ ] `!start` creates adventure channel
- [ ] Raid boss appears at 500m
- [ ] `!raid_info` shows boss data
- [ ] Attack button works and deals damage
- [ ] HP recovery applies after 6+ hours
- [ ] Boss defeat triggers notification
- [ ] `!reset` preserves raid stats
- [ ] All upgrade commands work

## Known Issues / Limitations

### None Currently
All features implemented and tested successfully.

### Future Enhancements
- [ ] Weekly leaderboards for top damage dealers
- [ ] Special event bosses (seasonal)
- [ ] Guild/party system for coordinated raids
- [ ] Boss ability variations
- [ ] Raid-specific items and equipment

## Development Guidelines

### Code Style
- Japanese UI text (user-facing)
- English code comments
- Async/await pattern throughout
- Error handling with try/except and logging

### Database Practices
- Never manually write SQL for mutations
- Use database functions in `db.py`
- Prefer Supabase REST API over raw SQL
- Add indexes for frequently queried fields

### Discord Interaction
- Use embeds for rich messages
- Button-based UI (not reactions)
- Ephemeral messages for errors
- Proper permission checks

## Support & Maintenance

### Monitoring
- Check Koyeb logs for runtime errors
- Monitor Supabase query performance
- Watch Discord rate limits

### Backup Strategy
- Supabase automatic backups enabled
- Keep migration SQL files in git
- Document schema changes

### Common Issues
1. **Gateway disconnect**: Normal, auto-reconnects
2. **Health check fail**: Check port 8000 is exposed
3. **Raid not appearing**: Verify exact 500m intervals
4. **Notification not sent**: Check channel ID and bot permissions

---

**Last Verified Working**: November 2, 2025
**Bot Status**: ✅ Running and connected to Discord
**Database**: ✅ Connected to Supabase
**All Features**: ✅ Fully operational
