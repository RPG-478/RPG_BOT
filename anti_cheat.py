"""
Anti-Cheat / Anomaly Detection System
Detects suspicious grinding patterns and script usage in the Discord RPG bot
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import db

logger = logging.getLogger("rpgbot")

# ==============================
# Detection Configuration
# ==============================

# Thresholds for anomaly scoring
SCORE_THRESHOLDS = {
    "auto_ban": 70,      # Automatic ban threshold
    "warning": 30,       # Warning threshold
}

# Detection weights
ANOMALY_WEIGHTS = {
    "no_equipment_grinding": 15,        # Grinding 8+ hours with no equipment
    "unused_upgrade_points": 10,        # Has 50+ unused upgrade points
    "consistent_timing": 20,            # Bot-like command intervals
    "non_responsive": 25,               # Doesn't respond to admin pings
    "extreme_session": 15,              # 12+ hour continuous grinding
    "perfect_intervals": 25,            # Near-perfect command timing
}

# Time windows
LONG_GRIND_HOURS = 8
EXTREME_GRIND_HOURS = 12
MIN_COMMANDS_FOR_PATTERN = 50  # Need this many commands to detect patterns

# ==============================
# Core Detection Functions
# ==============================

async def analyze_player_behavior(user_id: int) -> Dict:
    """
    Analyze player behavior and calculate anomaly score
    
    Returns:
        {
            "total_score": int,
            "anomalies": [list of detected anomalies],
            "risk_level": str ("low", "medium", "high", "critical"),
            "recommend_action": str ("monitor", "warn", "ban")
        }
    """
    anomalies = []
    total_score = 0
    
    # Get player stats
    stats = await db.get_user_behavior_stats(user_id)
    if not stats:
        return {
            "total_score": 0,
            "anomalies": [],
            "risk_level": "low",
            "recommend_action": "monitor"
        }
    
    # Detection 1: No-equipment grinding for extended periods
    if await detect_no_equipment_grinding(user_id, stats):
        score = ANOMALY_WEIGHTS["no_equipment_grinding"]
        total_score += score
        anomalies.append({
            "type": "no_equipment_grinding",
            "description": f"Grinding 8+ hours with no equipment equipped",
            "score": score,
            "severity": "medium"
        })
    
    # Detection 2: Unused upgrade points hoarding
    if await detect_unused_upgrade_points(user_id, stats):
        score = ANOMALY_WEIGHTS["unused_upgrade_points"]
        total_score += score
        anomalies.append({
            "type": "unused_upgrade_points",
            "description": f"Has {stats.get('unused_upgrade_points', 0)}+ unused upgrade points",
            "score": score,
            "severity": "medium"
        })
    
    # Detection 3: Bot-like execution patterns (consistent timing)
    timing_analysis = await detect_bot_like_timing(user_id)
    if timing_analysis["is_suspicious"]:
        score = timing_analysis["score"]
        total_score += score
        anomalies.append({
            "type": "bot_like_timing",
            "description": timing_analysis["description"],
            "score": score,
            "severity": "high"
        })
    
    # Detection 4: Extreme session length
    if await detect_extreme_session(user_id, stats):
        score = ANOMALY_WEIGHTS["extreme_session"]
        total_score += score
        anomalies.append({
            "type": "extreme_session",
            "description": f"Continuous grinding for 12+ hours",
            "score": score,
            "severity": "medium"
        })
    
    # Determine risk level and recommended action
    if total_score >= SCORE_THRESHOLDS["auto_ban"]:
        risk_level = "critical"
        recommend_action = "ban"
    elif total_score >= SCORE_THRESHOLDS["warning"]:
        risk_level = "high"
        recommend_action = "warn"
    elif total_score >= 15:
        risk_level = "medium"
        recommend_action = "monitor"
    else:
        risk_level = "low"
        recommend_action = "monitor"
    
    return {
        "total_score": total_score,
        "anomalies": anomalies,
        "risk_level": risk_level,
        "recommend_action": recommend_action
    }

async def detect_no_equipment_grinding(user_id: int, stats: Dict) -> bool:
    """
    Detect if player is grinding for 8+ hours with no equipment
    """
    # Check if player has been active for 8+ hours
    session_hours = stats.get("current_session_hours", 0)
    if session_hours < LONG_GRIND_HOURS:
        return False
    
    # Check if player has no equipment
    player = await db.get_player(user_id)
    if not player:
        return False
    
    equipped_weapon = player.get("equipped_weapon")
    equipped_armor = player.get("equipped_armor")
    
    # If no equipment and long session, suspicious
    if not equipped_weapon and not equipped_armor:
        return True
    
    return False

async def detect_unused_upgrade_points(user_id: int, stats: Dict) -> bool:
    """
    Detect if player has 50+ upgrade points and hasn't used them
    """
    player = await db.get_player(user_id)
    if not player:
        return False
    
    upgrade_points = player.get("upgrade_points", 0)
    
    # If they have 50+ points unused, suspicious
    if upgrade_points >= 50:
        return True
    
    return False

async def detect_bot_like_timing(user_id: int) -> Dict:
    """
    Detect bot-like command execution patterns
    - Consistent intervals between commands
    - Perfect timing (e.g., exactly every 3 seconds)
    """
    # Get recent command logs (last 100 commands)
    recent_commands = await db.get_recent_command_logs(user_id, limit=100)
    
    if len(recent_commands) < MIN_COMMANDS_FOR_PATTERN:
        return {
            "is_suspicious": False,
            "score": 0,
            "description": "Not enough data for pattern analysis"
        }
    
    # Calculate intervals between commands
    intervals = []
    for i in range(1, len(recent_commands)):
        time_diff = recent_commands[i]["timestamp"] - recent_commands[i-1]["timestamp"]
        intervals.append(time_diff.total_seconds())
    
    if not intervals:
        return {
            "is_suspicious": False,
            "score": 0,
            "description": "No intervals to analyze"
        }
    
    # Calculate statistics
    avg_interval = sum(intervals) / len(intervals)
    
    # Calculate variance (how much intervals deviate from average)
    variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
    std_dev = variance ** 0.5
    
    # Calculate coefficient of variation (CV)
    # Low CV means very consistent timing (suspicious)
    if avg_interval > 0:
        cv = std_dev / avg_interval
    else:
        cv = 0
    
    # Check for perfect intervals (within 0.5 seconds of each other)
    perfect_count = 0
    for i in range(1, len(intervals)):
        if abs(intervals[i] - intervals[i-1]) < 0.5:
            perfect_count += 1
    
    perfect_ratio = perfect_count / len(intervals) if intervals else 0
    
    # Scoring
    score = 0
    description = ""
    is_suspicious = False
    
    # Very low CV (< 0.1) = very consistent timing = likely bot
    if cv < 0.1 and len(intervals) >= 50:
        score = ANOMALY_WEIGHTS["perfect_intervals"]
        description = f"Near-perfect command timing (CV: {cv:.3f}, avg: {avg_interval:.1f}s)"
        is_suspicious = True
    # Moderate CV but high perfect ratio
    elif cv < 0.3 and perfect_ratio > 0.7:
        score = ANOMALY_WEIGHTS["consistent_timing"]
        description = f"Highly consistent timing pattern (CV: {cv:.3f}, {perfect_ratio:.1%} perfect intervals)"
        is_suspicious = True
    
    return {
        "is_suspicious": is_suspicious,
        "score": score,
        "description": description,
        "cv": cv,
        "avg_interval": avg_interval,
        "perfect_ratio": perfect_ratio
    }

async def detect_extreme_session(user_id: int, stats: Dict) -> bool:
    """
    Detect continuous grinding for 12+ hours
    """
    session_hours = stats.get("current_session_hours", 0)
    return session_hours >= EXTREME_GRIND_HOURS

# ==============================
# Logging Functions
# ==============================

async def log_command(user_id: int, command: str, success: bool = True, metadata: Dict = None, bot=None):
    """
    Log a command execution for anti-cheat analysis
    """
    try:
        await db.log_command(user_id, command, success, metadata)
        
        # Update behavior stats
        await db.update_behavior_stats(user_id)
        
        # Periodic check (every 50 commands)
        total_commands = await db.get_total_command_count(user_id)
        if total_commands % 50 == 0:
            # Run analysis
            analysis = await analyze_player_behavior(user_id)
            
            # Log the analysis
            await db.log_anti_cheat_event(
                user_id=user_id,
                event_type="periodic_check",
                severity=analysis["risk_level"],
                score=analysis["total_score"],
                details={
                    "anomalies": analysis["anomalies"],
                    "recommend_action": analysis["recommend_action"]
                }
            )
            
            # Take action if needed
            if analysis["recommend_action"] == "ban":
                await handle_auto_ban(user_id, analysis, bot)
            elif analysis["recommend_action"] == "warn":
                await handle_warning(user_id, analysis, bot)
        
    except Exception as e:
        logger.error(f"Error logging command for user {user_id}: {e}")

# ==============================
# Action Handlers
# ==============================

async def handle_auto_ban(user_id: int, analysis: Dict, bot=None):
    """
    Handle automatic ban for high-risk players
    """
    try:
        # Ban the player
        await db.ban_player(user_id, reason=f"Auto-ban: Anomaly score {analysis['total_score']}")
        
        # Log the ban
        await db.log_anti_cheat_event(
            user_id=user_id,
            event_type="auto_ban",
            severity="critical",
            score=analysis["total_score"],
            details={
                "anomalies": analysis["anomalies"],
                "reason": f"Anomaly score exceeded threshold ({analysis['total_score']} >= {SCORE_THRESHOLDS['auto_ban']})"
            }
        )
        
        logger.warning(f"Auto-banned user {user_id} with score {analysis['total_score']}")
        
        # Send admin notification if bot is provided
        if bot:
            import admin_notifications
            await admin_notifications.send_admin_alert(
                bot=bot,
                alert_type="auto_ban",
                user_id=user_id,
                details=analysis
            )
        
    except Exception as e:
        logger.error(f"Error auto-banning user {user_id}: {e}")

async def handle_warning(user_id: int, analysis: Dict, bot=None):
    """
    Handle warning for medium-risk players
    """
    try:
        # Log the warning
        await db.log_anti_cheat_event(
            user_id=user_id,
            event_type="warning",
            severity="high",
            score=analysis["total_score"],
            details={
                "anomalies": analysis["anomalies"],
                "reason": f"Anomaly score in warning range ({analysis['total_score']} >= {SCORE_THRESHOLDS['warning']})"
            }
        )
        
        logger.info(f"Warning issued for user {user_id} with score {analysis['total_score']}")
        
        # Send admin notification if bot is provided
        if bot:
            import admin_notifications
            await admin_notifications.send_admin_alert(
                bot=bot,
                alert_type="warning",
                user_id=user_id,
                details=analysis
            )
        
    except Exception as e:
        logger.error(f"Error issuing warning for user {user_id}: {e}")

# ==============================
# Manual Review Functions
# ==============================

async def manual_review_player(user_id: int) -> Dict:
    """
    Manually trigger a review of a player's behavior
    """
    analysis = await analyze_player_behavior(user_id)
    
    # Get additional context
    player = await db.get_player(user_id)
    stats = await db.get_user_behavior_stats(user_id)
    recent_logs = await db.get_recent_anti_cheat_logs(user_id, limit=10)
    
    return {
        "user_id": user_id,
        "analysis": analysis,
        "player_data": {
            "level": player.get("level", 1) if player else 0,
            "distance": player.get("distance", 0) if player else 0,
            "upgrade_points": player.get("upgrade_points", 0) if player else 0,
            "equipped_weapon": player.get("equipped_weapon") if player else None,
            "equipped_armor": player.get("equipped_armor") if player else None,
        },
        "behavior_stats": stats,
        "recent_events": recent_logs
    }
