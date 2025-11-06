"""
Admin Notification System
Sends alerts to admin channel for anti-cheat events
"""
import discord
from discord.ext import commands
import logging
from typing import Optional
from discord.ext import commands

logger = logging.getLogger("rpgbot")

# Admin notification channel ID
ADMIN_CHANNEL_ID = 1423275896445603953

async def send_admin_alert(bot: commands.Bot, alert_type: str, user_id: int, details: dict):
    """
    Send an alert to the admin channel
    
    Args:
        bot: Discord bot instance
        alert_type: Type of alert ("warning", "auto_ban", "suspicious_activity")
        user_id: User ID involved
        details: Dictionary with alert details
    """
    try:
        admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if not admin_channel:
            logger.error(f"Admin channel {ADMIN_CHANNEL_ID} not found")
            return False
        
        # Type check for text channel
        if not isinstance(admin_channel, discord.TextChannel):
            logger.error(f"Admin channel {ADMIN_CHANNEL_ID} is not a text channel")
            return False
        
        # Create embed based on alert type
        if alert_type == "auto_ban":
            embed = create_auto_ban_embed(user_id, details)
        elif alert_type == "warning":
            embed = create_warning_embed(user_id, details)
        elif alert_type == "suspicious_activity":
            embed = create_suspicious_activity_embed(user_id, details)
        else:
            embed = create_generic_alert_embed(user_id, alert_type, details)
        
        await admin_channel.send(embed=embed)
        return True
    
    except Exception as e:
        logger.error(f"Error sending admin alert: {e}")
        return False

def create_auto_ban_embed(user_id: int, details: dict) -> discord.Embed:
    """Create embed for auto-ban notification"""
    embed = discord.Embed(
        title="🚨 AUTO-BAN EXECUTED",
        description=f"User <@{user_id}> (`{user_id}`) has been automatically banned",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(
        name="Anomaly Score",
        value=f"**{details.get('total_score', 0)}/100**",
        inline=True
    )
    
    embed.add_field(
        name="Risk Level",
        value=details.get('risk_level', 'unknown').upper(),
        inline=True
    )
    
    # Add anomalies
    anomalies = details.get('anomalies', [])
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
    
    embed.set_footer(text="Anti-Cheat System | Review and unban if necessary")
    return embed

def create_warning_embed(user_id: int, details: dict) -> discord.Embed:
    """Create embed for warning notification"""
    embed = discord.Embed(
        title="⚠️ SUSPICIOUS BEHAVIOR WARNING",
        description=f"User <@{user_id}> (`{user_id}`) is showing suspicious patterns",
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(
        name="Anomaly Score",
        value=f"**{details.get('total_score', 0)}/100**",
        inline=True
    )
    
    embed.add_field(
        name="Risk Level",
        value=details.get('risk_level', 'unknown').upper(),
        inline=True
    )
    
    # Add anomalies
    anomalies = details.get('anomalies', [])
    if anomalies:
        anomaly_text = ""
        for anomaly in anomalies:
            anomaly_text += f"• **{anomaly.get('type', 'unknown')}** (+{anomaly.get('score', 0)})\n"
            anomaly_text += f"  _{anomaly.get('description', 'No description')}_\n\n"
        
        embed.add_field(
            name="Detected Patterns",
            value=anomaly_text[:1024],
            inline=False
        )
    
    embed.set_footer(text="Anti-Cheat System | Monitor this user")
    return embed

def create_suspicious_activity_embed(user_id: int, details: dict) -> discord.Embed:
    """Create embed for suspicious activity notification"""
    embed = discord.Embed(
        title="👁️ SUSPICIOUS ACTIVITY DETECTED",
        description=f"User <@{user_id}> (`{user_id}`) is showing unusual behavior",
        color=discord.Color.yellow(),
        timestamp=discord.utils.utcnow()
    )
    
    if 'session_hours' in details:
        embed.add_field(
            name="Session Duration",
            value=f"{details['session_hours']:.1f} hours",
            inline=True
        )
    
    if 'total_commands' in details:
        embed.add_field(
            name="Total Commands",
            value=str(details['total_commands']),
            inline=True
        )
    
    if 'upgrade_points' in details:
        embed.add_field(
            name="Unused Upgrade Points",
            value=str(details['upgrade_points']),
            inline=True
        )
    
    if 'has_equipment' in details:
        embed.add_field(
            name="Has Equipment",
            value="Yes" if details['has_equipment'] else "No",
            inline=True
        )
    
    embed.set_footer(text="Anti-Cheat System | Early warning")
    return embed

def create_generic_alert_embed(user_id: int, alert_type: str, details: dict) -> discord.Embed:
    """Create generic alert embed"""
    embed = discord.Embed(
        title=f"🔔 {alert_type.upper().replace('_', ' ')}",
        description=f"Alert for user <@{user_id}> (`{user_id}`)",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    # Add all details as fields
    for key, value in details.items():
        if isinstance(value, (str, int, float, bool)):
            embed.add_field(
                name=key.replace('_', ' ').title(),
                value=str(value),
                inline=True
            )
    
    embed.set_footer(text="Anti-Cheat System")
    return embed
