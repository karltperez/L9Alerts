import os
import random
import discord
from discord.ext import commands, tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import pytz
import json
from discord import app_commands, Interaction
from discord.ui import View, Select, Button, Modal, TextInput
from typing import Optional

# Load your bot token from environment
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError('DISCORD_BOT_TOKEN environment variable not set. Please set it before running the bot.')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)
scheduler = AsyncIOScheduler()

# Event schedule (GMT+8)
events = [
    {"name": "Guild Boss", "day": "Saturday", "hour": 20, "minute": 0},
    {"name": "Garbana Dungeon", "day": "Saturday", "hour": 20, "minute": 0},
    {"name": "World Boss: Ratan, Parto, Nedra", "day": "Everyday", "hour": 11, "minute": 0},
    {"name": "World Boss: Ratan, Parto, Nedra", "day": "Everyday", "hour": 20, "minute": 0},
]

# Quotes about min-maxing
quotes = [
    "Min-maxing: because every stat point counts!",
    "A true hero knows the value of optimization.",
    "Why settle for average when you can be legendary?",
    "In Lord Nine, min-maxing is the path to glory.",
    "The difference between good and great is in the details.",
]

CONFIG_FILE = 'bot_config.json'
EVENTS_FILE = 'events_config.json'

WORLD_BOSS_BANNERS = {
    "Ratan, Parto, Nedra": "https://cdn.discordapp.com/attachments/1262911795333566465/1420453316898459831/image.png?ex=68d573bd&is=68d4223d&hm=bda257b318454fffb305bff98c25e050d091d055e90c0cf714380519cf737597",
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"reminder_channel_id": 0, "mention_role_id": 0}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def load_events():
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, 'r') as f:
            return json.load(f)
    return events.copy()

def save_events(events_data):
    with open(EVENTS_FILE, 'w') as f:
        json.dump(events_data, f)

config = load_config()
events_data = load_events()

@bot.command()
@commands.has_permissions(administrator=True)
async def setchannel(ctx, channel: discord.TextChannel):
    if not hasattr(channel, 'send'):
        await ctx.send("Error: The selected channel is not a text channel.")
        return
    config['reminder_channel_id'] = channel.id
    save_config(config)
    await ctx.send(f"Reminder channel set to {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setrole(ctx, role: Optional[discord.Role] = None):
    if role:
        if not ctx.guild.get_role(role.id):
            await ctx.send("Error: The selected role does not exist.")
            return
        config['mention_role_id'] = role.id
        await ctx.send(f"Role to mention set to {role.mention}")
    else:
        config['mention_role_id'] = 0
        await ctx.send("Role mention removed.")
    save_config(config)

def get_time_remaining(event_time):
    now = datetime.now(pytz.timezone('Asia/Singapore'))
    delta = event_time - now
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}m"

def format_time_12h(hour, minute):
    suffix = "AM" if hour < 12 or hour == 24 else "PM"
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12
    return f"{hour_12}:{minute:02d} {suffix}"

async def send_reminder(event, when):
    channel_id = config.get('reminder_channel_id', 0)
    channel = bot.get_channel(channel_id) if channel_id else None
    mention_role_id = config.get('mention_role_id')
    mention_text = f'<@&{mention_role_id}>' if mention_role_id else ''
    if isinstance(channel, discord.TextChannel):
        now = datetime.now(pytz.timezone('Asia/Singapore'))
        event_time = now.replace(hour=event['hour'], minute=event['minute'], second=0, microsecond=0)
        if event_time < now:
            event_time += timedelta(days=1)
        time_remaining = get_time_remaining(event_time)
        embed = discord.Embed(
            title=f"{event['name']} Reminder ({when})",
            description=f"Scheduled for {format_time_12h(event['hour'], event['minute'])} GMT+8\nTime Remaining: {time_remaining}",
            color=0x00ff99
        )
        embed.set_footer(text=random.choice(quotes))
        # Add banner for world bosses
        for boss in WORLD_BOSS_BANNERS:
            if boss in event['name']:
                embed.set_image(url=WORLD_BOSS_BANNERS[boss])
                break
        await channel.send(content=mention_text if mention_text else None, embed=embed)

class EditEventTimeModal(Modal):
    def __init__(self, event_idx, event_name, current_hour, current_minute, current_day=None):
        super().__init__(title=f"Edit Time: {event_name}")
        self.event_idx = event_idx
        self.hour_input = TextInput(label="Hour (0-23)", default=str(current_hour), required=True, max_length=2)
        self.minute_input = TextInput(label="Minute (0-59)", default=str(current_minute), required=True, max_length=2)
        self.add_item(self.hour_input)
        self.add_item(self.minute_input)
        # Only allow day change for Guild Boss and Garbana
        if event_name in ["Guild Boss", "Garbana Dungeon"]:
            self.day_input = TextInput(label="Day (e.g. Saturday)", default=str(current_day), required=True, max_length=10)
            self.add_item(self.day_input)

    async def on_submit(self, interaction: Interaction):
        try:
            hour = int(self.hour_input.value)
            minute = int(self.minute_input.value)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Invalid time. Please enter valid hour (0-23) and minute (0-59).", ephemeral=True)
            return
        events_data[self.event_idx]['hour'] = hour
        events_data[self.event_idx]['minute'] = minute
        # Save new day if allowed
        if hasattr(self, 'day_input'):
            new_day = self.day_input.value.strip()
            valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            if new_day not in valid_days:
                await interaction.response.send_message(f"Invalid day. Please enter one of: {', '.join(valid_days)}.", ephemeral=True)
                return
            events_data[self.event_idx]['day'] = new_day
        save_events(events_data)
        await interaction.response.send_message(f"Updated {events_data[self.event_idx]['name']} to {hour:02d}:{minute:02d} {events_data[self.event_idx]['day']}.", ephemeral=True)
        schedule_events()

class EventSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=f"{e['name']} ({e['day']})", value=str(idx))
            for idx, e in enumerate(events_data)
        ]
        super().__init__(placeholder="Select event to edit time...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        idx = int(self.values[0])
        event = events_data[idx]
        modal = EditEventTimeModal(idx, event['name'], event['hour'], event['minute'], event['day'])
        await interaction.response.send_modal(modal)

class ChannelSelect(Select):
    def __init__(self, guild):
        options = [
            discord.SelectOption(label=channel.name, value=str(channel.id))
            for channel in guild.text_channels
        ]
        if not options:
            options = [discord.SelectOption(label="No channels found", value="none")]  # fallback
        super().__init__(placeholder="Select alert channel...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No channels available to select.", ephemeral=True)
            return
        config['reminder_channel_id'] = int(self.values[0])
        save_config(config)
        await interaction.response.send_message(f"Alert channel set to <#{self.values[0]}>.", ephemeral=True)

class RoleSelect(Select):
    def __init__(self, guild):
        roles = [role for role in guild.roles if not role.is_default()]
        # Limit to 24 roles for Discord's 25-option limit (1 is 'No Role Mention')
        roles = roles[:24]
        options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in roles
        ]
        options.insert(0, discord.SelectOption(label="No Role Mention", value="none"))
        if len(options) == 1:  # Only 'No Role Mention' present
            options.append(discord.SelectOption(label="No roles found", value="noroles"))
        super().__init__(placeholder="Select role to mention...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        if self.values[0] == "none":
            config['mention_role_id'] = 0
            save_config(config)
            await interaction.response.send_message("Role mention removed.", ephemeral=True)
        elif self.values[0] == "noroles":
            await interaction.response.send_message("No roles available to select.", ephemeral=True)
        else:
            config['mention_role_id'] = int(self.values[0])
            save_config(config)
            await interaction.response.send_message(f"Role to mention set to <@&{self.values[0]}>.", ephemeral=True)

class EditEventTimeButton(Button):
    def __init__(self):
        super().__init__(label="Edit Event Times", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: Interaction):
        await interaction.response.send_message("Select an event to edit:", view=EventTimeView(), ephemeral=True)

class EventTimeView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(EventSelect())

class SettingsView(View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        self.guild = guild
        self.add_item(ChannelSelect(guild))
        self.add_item(RoleSelect(guild))
        self.add_item(EditEventTimeButton())

GUILD_ID = 1072094900776087572  # <-- Replace with your Discord server's ID

guild_obj = discord.Object(id=GUILD_ID)

l9_group = app_commands.Group(name="l9", description="Lord Nine bot commands", guild_ids=[GUILD_ID])
bot.tree.add_command(l9_group)

class SetAlertModal(Modal):
    def __init__(self):
        super().__init__(title="Set Alert Channel and Role")
        self.channel_id_input = TextInput(label="Channel ID", placeholder="Enter the channel ID for alerts", required=True, max_length=25)
        self.role_id_input = TextInput(label="Role ID (optional)", placeholder="Enter the role ID to mention (or leave blank)", required=False, max_length=25)
        self.add_item(self.channel_id_input)
        self.add_item(self.role_id_input)

    async def on_submit(self, interaction: Interaction):
        channel_id = self.channel_id_input.value.strip()
        role_id = self.role_id_input.value.strip()
        # Validate channel ID
        if not channel_id.isdigit():
            await interaction.response.send_message("Error: Channel ID must be a number.", ephemeral=True)
            return
        channel_obj = interaction.client.get_channel(int(channel_id))
        if not channel_obj or not hasattr(channel_obj, 'send'):
            await interaction.response.send_message("Error: Channel ID is invalid or not a text channel.", ephemeral=True)
            return
        # Validate role ID if provided
        if role_id:
            if not role_id.isdigit():
                await interaction.response.send_message("Error: Role ID must be a number.", ephemeral=True)
                return
            guild = interaction.guild or interaction.client.get_guild(GUILD_ID)
            if not guild:
                await interaction.response.send_message("Error: Could not determine guild context.", ephemeral=True)
                return
            role_obj = guild.get_role(int(role_id))
            if not role_obj:
                await interaction.response.send_message("Error: Role ID is invalid.", ephemeral=True)
                return
            config['mention_role_id'] = int(role_id)
        else:
            config['mention_role_id'] = 0
        config['reminder_channel_id'] = int(channel_id)
        save_config(config)
        role_mention = f'<@&{role_id}>' if role_id else 'None'
        await interaction.response.send_message(f"Alert channel set to <#{channel_id}>. Role mention set to {role_mention}.", ephemeral=True)

@l9_group.command(name="setalert", description="Configure alert channel and mention role (admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def setalert_command(interaction: Interaction):
    await interaction.response.send_modal(SetAlertModal())

@setalert_command.error
async def setalert_command_error(interaction: Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Error: {error}", ephemeral=True)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        # Only sync commands for the guild
        synced = await bot.tree.sync(guild=guild_obj)
        print(f'Synced {len(synced)} slash commands for guild {GUILD_ID}. Commands: {[cmd.name for cmd in synced]}')
    except Exception as e:
        print(f'Error syncing commands: {e}')
    scheduler.start()
    schedule_events()

# Helper to get next event time (today or next correct weekday)
def next_event_time(event, now):
    days_map = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6, "Everyday": None
    }
    event_weekday = days_map.get(event['day'], None)
    event_time = now.replace(hour=event['hour'], minute=event['minute'], second=0, microsecond=0)
    if event_weekday is not None:
        # Calculate days until next event weekday
        days_ahead = (event_weekday - now.weekday()) % 7
        if days_ahead == 0 and event_time < now:
            days_ahead = 7
        event_time = event_time + timedelta(days=days_ahead)
    else:
        # 'Everyday' events
        if event_time < now:
            event_time += timedelta(days=1)
    return event_time

def schedule_events():
    scheduler.remove_all_jobs()
    days_map = {
        "Monday": 'mon', "Tuesday": 'tue', "Wednesday": 'wed', "Thursday": 'thu',
        "Friday": 'fri', "Saturday": 'sat', "Sunday": 'sun', "Everyday": '*'
    }
    for event in events_data:
        day = days_map.get(event['day'], '*')
        hour = event['hour']
        minute = event['minute']
        # Calculate 15 minutes before
        before_hour = hour
        before_minute = minute - 15
        before_day = day
        if before_minute < 0:
            before_minute += 60
            before_hour -= 1
            if before_hour < 0:
                before_hour = 23
                # Adjust day_of_week for previous day if not 'Everyday'
                if day != '*':
                    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    idx = days.index(day)
                    before_day = days[(idx - 1) % 7]
        # Reminder 15 minutes before
        scheduler.add_job(
            send_reminder,
            CronTrigger(day_of_week=before_day, hour=before_hour, minute=before_minute, timezone='Asia/Singapore'),
            args=[event, '15 min before']
        )
        # Reminder at event time
        scheduler.add_job(
            send_reminder,
            CronTrigger(day_of_week=day, hour=hour, minute=minute, timezone='Asia/Singapore'),
            args=[event, 'Start']
        )

@l9_group.command(name="schedule", description="Show the current event schedule and edit times")
async def schedule_command(interaction: Interaction):
    lines = []
    for event in events_data:
        lines.append(f"**{event['name']}**: {event['day']} at {format_time_12h(event['hour'], event['minute'])} GMT+8")
    schedule_text = "\n".join(lines)
    view = EventTimeView()
    await interaction.response.send_message(f"**Event Schedule:**\n{schedule_text}\n\n*Click the button below to edit event times.*", view=view, ephemeral=True)

@l9_group.command(name="samplealert", description="Send a sample alert to the configured channel for preview/testing")
async def samplealert_command(interaction: Interaction):
    channel_id = config.get('reminder_channel_id', 0)
    channel = bot.get_channel(channel_id) if channel_id else None
    mention_role_id = config.get('mention_role_id')
    mention_text = f'<@&{mention_role_id}>' if mention_role_id else ''
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Configured channel is invalid. Please set a valid text channel.", ephemeral=True)
        return
    now = datetime.now(pytz.timezone('Asia/Singapore'))
    # Guild Boss
    guild_boss = next((e for e in events_data if 'Guild Boss' in e['name']), None)
    guild_boss_str = "Guild Boss Schedule: Not set"
    if guild_boss:
        gb_time = next_event_time(guild_boss, now)
        gb_remain = get_time_remaining(gb_time)
        guild_boss_str = f"**Guild Boss Schedule**:\n{guild_boss['day']} at {format_time_12h(guild_boss['hour'], guild_boss['minute'])} GMT+8 (Time Remaining: {gb_remain})"
    # Garbana Rally
    garbana = next((e for e in events_data if 'Garbana' in e['name']), None)
    garbana_str = "Garbana Rally Schedule: Not set"
    if garbana:
        garbana_time = next_event_time(garbana, now)
        garbana_remain = get_time_remaining(garbana_time)
        garbana_str = f"**Garbana Rally Schedule**:\n{garbana['day']} at {format_time_12h(garbana['hour'], garbana['minute'])} GMT+8 (Time Remaining: {garbana_remain})"
    # World Boss
    world_bosses = [e for e in events_data if 'World Boss' in e['name']]
    next_boss_events = []
    boss_names = set(WORLD_BOSS_BANNERS.keys())
    for boss in boss_names:
        boss_events = [e for e in world_bosses if boss in e['name']]
        soonest = None
        soonest_time = None
        for event in boss_events:
            event_time = next_event_time(event, now)
            delta = (event_time - now).total_seconds()
            if 0 <= delta <= 900:
                if soonest is None or (soonest_time is not None and event_time < soonest_time):
                    soonest = event
                    soonest_time = event_time
        if soonest:
            time_remaining = get_time_remaining(soonest_time)
            next_boss_events.append((soonest, soonest_time, time_remaining))
    embed_desc = (
        "📢 **ATTENTION**📢\n\n"
        f"{guild_boss_str}\n"
        f"{garbana_str}\n"
    )
    embed_desc += "\n---------------------------------------------\n\n**World Boss Timer**\n"
    if next_boss_events:
        for event, event_time, time_remaining in next_boss_events:
            embed_desc += f"- {event['name']} : {event['day']} at {format_time_12h(event['hour'], event['minute'])} GMT+8 (Time Remaining: {time_remaining})\n"
    else:
        embed_desc += "No world boss event is within the next 15 minutes.\n"
    banner_url = next(iter(WORLD_BOSS_BANNERS.values()))
    embed = discord.Embed(
        title="Daily Guild & World Boss Reminder (Sample)",
        description=embed_desc + "\n" + random.choice(quotes),
        color=0x00ff99
    )
    embed.set_image(url=banner_url)
    await channel.send(content=mention_text if mention_text else None, embed=embed)
    await interaction.response.send_message(f"Sample daily reminder sent to {channel.mention}.", ephemeral=True)

bot.run(TOKEN)