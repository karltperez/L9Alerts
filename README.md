# Lord Nine Infinite Class Game - NFT Discord Bot

This bot sends scheduled reminders for:
- Guild Boss
- Garbana Dungeon
- World Bosses (Ratan, Parto, Nedra)

Reminders are sent 15 minutes before and at the event time (11AM & 8PM GMT+8). Each reminder includes a random MMORPG min-maxing quote.

## Setup
1. Ensure you have Python 3.8+ installed.
2. Install dependencies:
   ```sh
   pip install discord.py apscheduler pytz
   ```
3. Add your Discord bot token to a `.env` file or directly in the script.
4. Run the bot:
   ```sh
   python bot.py
   ```

## Customization
- Edit event times or quotes in `bot.py` as needed.

---

For more details, see the code and comments in `bot.py`.
