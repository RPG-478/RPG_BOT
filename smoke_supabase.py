import asyncio
import logging

import db

logger = logging.getLogger("rpgbot")


async def main() -> None:
    uid = 1301416493401243694
    ok1 = await db.log_command(uid, "!move", True, {"test": True})
    logger.info("log_command: %s", ok1)

    ok2 = await db.log_anti_cheat_event(uid, "periodic_check", "low", 0, {"test": True})
    logger.info("log_anti_cheat_event: %s", ok2)

    ok3 = await db.update_behavior_stats(uid)
    logger.info("update_behavior_stats: %s", ok3)


if __name__ == "__main__":
    asyncio.run(main())
