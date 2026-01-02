"""
Admin Commands for Anti-Cheat System
Commands for viewing logs, managing bans, and reviewing player behavior
"""
import discord
from discord.ext import commands
import anti_cheat
import db
from typing import Optional

# ==============================
# Admin Commands
# ==============================

def setup_admin_commands(bot: commands.Bot):
    """Setup admin anti-cheat commands"""
    
    @bot.command(name="ac_review")
    @commands.has_permissions(administrator=True)
    async def anti_cheat_review(ctx: commands.Context, user_id: str):
        """
        Manually review a player's behavior
        Usage: !ac_review <user_id>
        """
        try:
            user_id_int = int(user_id)
        except ValueError:
            await ctx.send("❌ Invalid user ID. Please provide a numeric user ID.")
            return
        
        await ctx.send(f"🔍 Analyzing player behavior for user `{user_id_int}`...")
        
        # Run manual review
        review = await anti_cheat.manual_review_player(user_id_int)
        
        # Create embed
        analysis = review["analysis"]
        player_data = review["player_data"]
        
        embed = discord.Embed(
            title=f"🔍 Anti-Cheat Review: {user_id_int}",
            description=f"Risk Level: **{analysis['risk_level'].upper()}**",
            color=get_risk_color(analysis['risk_level']),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="Anomaly Score",
            value=f"**{analysis['total_score']}/100**",
            inline=True
        )
        
        embed.add_field(
            name="Recommended Action",
            value=analysis['recommend_action'].upper(),
            inline=True
        )
        
        embed.add_field(
            name="Player Stats",
            value=f"Level: {player_data['level']}\n"
                  f"Distance: {player_data['distance']}m\n"
                  f"Upgrade Points: {player_data['upgrade_points']}",
            inline=True
        )
        
        embed.add_field(
            name="Equipment",
            value=f"Weapon: {player_data['equipped_weapon'] or 'None'}\n"
                  f"Armor: {player_data['equipped_armor'] or 'None'}\n"
                  f"Shield: {player_data.get('equipped_shield') or 'None'}",
            inline=True
        )
        
        # Add anomalies
        anomalies = analysis.get('anomalies', [])
        if anomalies:
            anomaly_text = ""
            for anomaly in anomalies:
                anomaly_text += f"• **{anomaly.get('type', 'unknown')}** (+{anomaly.get('score', 0)})\n"
                anomaly_text += f"  _{anomaly.get('description', 'No description')}_\n\n"
            
            embed.add_field(
                name="Detected Anomalies",
                value=anomaly_text[:1024],
                inline=False
            )
        else:
            embed.add_field(
                name="Detected Anomalies",
                value="No anomalies detected",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @bot.command(name="ac_logs")
    @commands.has_permissions(administrator=True)
    async def anti_cheat_logs(ctx: commands.Context, user_id: str, limit: int = 10):
        """
        View recent anti-cheat logs for a user
        Usage: !ac_logs <user_id> [limit]
        """
        try:
            user_id_int = int(user_id)
        except ValueError:
            await ctx.send("❌ Invalid user ID. Please provide a numeric user ID.")
            return
        
        logs = await db.get_recent_anti_cheat_logs(user_id_int, limit=min(limit, 25))
        
        if not logs:
            await ctx.send(f"No anti-cheat logs found for user `{user_id_int}`.")
            return
        
        embed = discord.Embed(
            title=f"📋 Anti-Cheat Logs: {user_id_int}",
            description=f"Showing {len(logs)} most recent events",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        for log in logs[:10]:  # Show max 10 in embed
            event_type = log.get('event_type', 'unknown')
            severity = log.get('severity', 'unknown')
            score = log.get('anomaly_score', 0)
            timestamp = log.get('timestamp', 'unknown')
            
            embed.add_field(
                name=f"{event_type.upper()} - {severity}",
                value=f"Score: {score} | Time: {timestamp}",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @bot.command(name="ac_ban")
    @commands.has_permissions(administrator=True)
    async def anti_cheat_ban(ctx: commands.Context, user_id: str, *, reason: str = "Manual ban by administrator"):
        """
        Manually ban a player
        Usage: !ac_ban <user_id> [reason]
        """
        try:
            user_id_int = int(user_id)
        except ValueError:
            await ctx.send("❌ Invalid user ID. Please provide a numeric user ID.")
            return
        
        success = await db.ban_player(user_id_int, reason=reason)
        
        if success:
            embed = discord.Embed(
                title="🔨 Player Banned",
                description=f"User <@{user_id_int}> (`{user_id_int}`) has been banned.",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Banned By", value=ctx.author.mention, inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Failed to ban user `{user_id_int}`. Check logs for details.")
    
    @bot.command(name="ac_unban")
    @commands.has_permissions(administrator=True)
    async def anti_cheat_unban(ctx: commands.Context, user_id: str):
        """
        Unban a player
        Usage: !ac_unban <user_id>
        """
        try:
            user_id_int = int(user_id)
        except ValueError:
            await ctx.send("❌ Invalid user ID. Please provide a numeric user ID.")
            return
        
        success = await db.unban_player(user_id_int)
        
        if success:
            embed = discord.Embed(
                title="✅ Player Unbanned",
                description=f"User <@{user_id_int}> (`{user_id_int}`) has been unbanned.",
                color=discord.Color.green()
            )
            embed.add_field(name="Unbanned By", value=ctx.author.mention, inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Failed to unban user `{user_id_int}`. Check logs for details.")
    
    @bot.command(name="ac_stats")
    @commands.has_permissions(administrator=True)
    async def anti_cheat_stats(ctx: commands.Context, user_id: str):
        """
        View behavior statistics for a user
        Usage: !ac_stats <user_id>
        """
        try:
            user_id_int = int(user_id)
        except ValueError:
            await ctx.send("❌ Invalid user ID. Please provide a numeric user ID.")
            return
        
        stats = await db.get_user_behavior_stats(user_id_int)
        
        if not stats:
            await ctx.send(f"No behavior statistics found for user `{user_id_int}`.")
            return
        
        embed = discord.Embed(
            title=f"📊 Behavior Statistics: {user_id_int}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="Total Commands",
            value=str(stats.get('total_commands', 0)),
            inline=True
        )
        
        embed.add_field(
            name="Session Hours",
            value=f"{stats.get('current_session_hours', 0):.1f}h",
            inline=True
        )
        
        embed.add_field(
            name="Unused Upgrade Points",
            value=str(stats.get('unused_upgrade_points', 0)),
            inline=True
        )
        
        embed.add_field(
            name="Has Equipment",
            value="Yes" if stats.get('has_equipment', False) else "No",
            inline=True
        )
        
        embed.add_field(
            name="Last Active",
            value=stats.get('last_active', 'Unknown'),
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @bot.command(name="ac_commands")
    @commands.has_permissions(administrator=True)
    async def anti_cheat_commands_list(ctx: commands.Context):
        """
        List all anti-cheat admin commands
        """
        embed = discord.Embed(
            title="🛡️ Anti-Cheat Admin Commands",
            description="Available commands for managing the anti-cheat system",
            color=discord.Color.purple()
        )
        
        commands_list = [
            ("!ac_review <user_id>", "Manually review a player's behavior"),
            ("!ac_logs <user_id> [limit]", "View recent anti-cheat logs"),
            ("!ac_ban <user_id> [reason]", "Manually ban a player"),
            ("!ac_unban <user_id>", "Unban a player"),
            ("!ac_stats <user_id>", "View behavior statistics"),
            ("!ac_commands", "Show this help message")
        ]
        
        for cmd, desc in commands_list:
            embed.add_field(
                name=cmd,
                value=desc,
                inline=False
            )
        
        embed.set_footer(text="All commands require administrator permissions")
        
        await ctx.send(embed=embed)

def get_risk_color(risk_level: str) -> discord.Color:
    """Get color based on risk level"""
    colors = {
        "low": discord.Color.green(),
        "medium": discord.Color.yellow(),
        "high": discord.Color.orange(),
        "critical": discord.Color.red()
    }
    return colors.get(risk_level, discord.Color.blue())
