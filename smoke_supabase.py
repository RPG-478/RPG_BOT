import asyncio

import db


async def main() -> None:
    uid = 1301416493401243694
    ok1 = await db.log_command(uid, "!move", True, {"test": True})
    print("log_command:", ok1)

    ok2 = await db.log_anti_cheat_event(uid, "periodic_check", "low", 0, {"test": True})
    print("log_anti_cheat_event:", ok2)

    ok3 = await db.update_behavior_stats(uid)
    print("update_behavior_stats:", ok3)


if __name__ == "__main__":
    asyncio.run(main())
