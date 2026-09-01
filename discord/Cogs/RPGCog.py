import asyncio
import copy
import datetime
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button

from . import rpg_logic
from .util import MONSTERS_PATH, PLAYERS_PATH, SHOP_PATH, load_json, load_json_list, save_json

logger = logging.getLogger(__name__)

MENU_TITLE = "🔮 Adventure Menu - Choose an action:"

DEFAULT_USER = {
    "level": 1,
    "health": 100,
    "max_health": 100,
    "stamina": 100,
    "max_stamina": 100,
    "mana": 100,
    "max_mana": 100,
    "hunger": 100,
    "max_hunger": 100,
    "thirst": 100,
    "max_thirst": 100,
    "attack": 10,
    "defense": 5,
    "experience": 0,
    "gold": 0,
    "inventory": [],
    "cooldowns": {},
    "skills": [],
    "defeated": False,
    "x": 0,
    "y": 0,
    "factions": {"NEUTRAL": 0},
    "active_quests": [],
    "quest_progress": {},
    "equipped": {},
}


class OwnerOnlyView(discord.ui.View):
    """Base for the RPG menu views: only the user who opened the menu may
    click its buttons."""

    denial_message = "❌ This menu is not for you!"

    def __init__(self, cog, user_id, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(self.denial_message, ephemeral=True)
            return False
        return True


class RPGView(OwnerOnlyView):
    def __init__(self, cog, user_id):
        super().__init__(cog, user_id, timeout=180)

    @discord.ui.button(label="Explore", style=discord.ButtonStyle.primary)
    async def explore_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        response = await self.cog.explore_action(interaction)
        await interaction.response.edit_message(content=response, embed=None, view=self)

    @discord.ui.button(label="Battle", style=discord.ButtonStyle.danger)
    async def battle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        if user.get("defeated"):
            await interaction.response.edit_message(
                content="💀 You are defeated and cannot fight! Wait for health regeneration or use a potion.",
                view=self,
            )
            return
        now = datetime.datetime.now().timestamp()
        last_battle = user["cooldowns"].get("battle", 0)
        if now - last_battle < 10:
            remaining = 10 - (now - last_battle)
            await interaction.response.edit_message(
                content=f"⏳ You need to wait {remaining:.1f}s before starting a new battle!",
                view=self,
            )
            return
        if "current_monster" not in user:
            await interaction.response.edit_message(
                content="❌ No monster to fight! Use Explore first!",
                view=self,
            )
            return
        battle_view = BattleView(self.cog, self.user_id)
        await battle_view.create_embed()
        await interaction.response.edit_message(
            content="⚔️ Battle!",
            embed=battle_view.embed,
            view=battle_view,
        )

    @discord.ui.button(label="Shop", style=discord.ButtonStyle.success)
    async def shop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        shop_view = ShopView(self.cog, self.user_id)
        await shop_view.create_embed()
        await interaction.response.edit_message(
            content="🛒 RPG Shop",
            embed=shop_view.embed,
            view=shop_view,
        )

    @discord.ui.button(label="Inventory", style=discord.ButtonStyle.secondary)
    async def inventory_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        embed = discord.Embed(title="Inventory", color=0x00FF00)
        if not user["inventory"]:
            embed.description = "Your inventory is empty!"
        else:
            for entry in user["inventory"]:
                name = entry["name"]
                label = name.capitalize() if entry.get("type") != "equipment" else name
                value = f"Quantity: {entry.get('qty', 1)}"
                if entry.get("type") == "equipment":
                    value = f"Slot: {entry.get('slot', '?')} | Bonus: {entry.get('bonus', {})}"
                embed.add_field(name=label, value=value, inline=True)
        await interaction.response.edit_message(content="🎒 Inventory", embed=embed, view=self)

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.secondary)
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        embed = discord.Embed(title=f"{interaction.user.display_name}'s Stats", color=0x00FF00)
        embed.add_field(name="Level", value=user["level"], inline=True)
        embed.add_field(name="Health", value=f"{user['health']}/{user['max_health']}", inline=True)
        embed.add_field(name="Attack", value=user["attack"], inline=True)
        embed.add_field(name="Defense", value=user["defense"], inline=True)
        embed.add_field(
            name="Experience",
            value=f"{user['experience']}/{rpg_logic.xp_to_next_level(user['level'])}",
            inline=True,
        )
        embed.add_field(name="Gold", value=user["gold"], inline=True)
        await interaction.response.edit_message(content="📊 Stats", embed=embed, view=self)


class BattleView(OwnerOnlyView):
    def __init__(self, cog, user_id):
        super().__init__(cog, user_id, timeout=30)
        self.embed = None

    async def create_embed(self):
        user = self.cog.get_user(self.user_id)
        monster = user.get("current_monster", {})
        embed = discord.Embed(title="⚔️ Battle", color=0xFF0000)
        embed.add_field(
            name=f"🦖 {monster.get('name', 'Unknown').capitalize()}",
            value=f"❤️ Health: {monster.get('health', 0)}",
            inline=False,
        )
        embed.add_field(
            name="Your Health",
            value=f"❤️ {user['health']}/{user['max_health']}",
            inline=False,
        )
        self.embed = embed

    @discord.ui.button(label="Attack", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await self.cog.process_attack(interaction)
        await self.cog.render_after_attack(interaction, result)

    @discord.ui.button(label="Skills", style=discord.ButtonStyle.primary)
    async def skills_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        if not user["skills"]:
            await interaction.response.send_message("❌ You have no learned skills!", ephemeral=True)
            return
        view = SkillMenuView(self.cog, self.user_id, list(user["skills"]), learn_only=False)
        await interaction.response.edit_message(
            content="🔮 Choose a skill to use:",
            view=view,
        )

    @discord.ui.button(label="Flee", style=discord.ButtonStyle.secondary)
    async def flee_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        if random.random() < 0.5:
            del user["current_monster"]
            save_json(PLAYERS_PATH, self.cog.user_data)
            await interaction.response.edit_message(
                content="🏃♂️ You successfully fled!",
                embed=None,
                view=None,
            )
        else:
            monster = user.get("current_monster", {})
            damage = rpg_logic.monster_attack_damage(monster.get("attack", 0), user["defense"])
            user["health"] -= damage
            if user["health"] <= 0:
                user["health"] = 0
                user["defeated"] = True
                del user["current_monster"]
                save_json(PLAYERS_PATH, self.cog.user_data)
                await interaction.response.edit_message(
                    content="💀 You failed to flee and were defeated! Wait for health regeneration or use a potion to recover.",
                    embed=None,
                    view=None,
                )
            else:
                save_json(PLAYERS_PATH, self.cog.user_data)
                await self.create_embed()
                response = f"🏃♂️ You failed to flee! The {monster.get('name')} hit you for {damage} damage!"
                await interaction.response.edit_message(content=response, embed=self.embed, view=self)


class SkillMenuView(OwnerOnlyView):
    def __init__(self, cog, user_id, skills, learn_only=False):
        super().__init__(cog, user_id, timeout=30)
        self.learn_only = learn_only

        for skill_name in skills:
            skill_data = next(
                (s for level in cog.SKILLS.values() for s in level if s["name"] == skill_name),
                None,
            )
            if not skill_data:
                logger.warning("Skill %s is not defined in SKILLS; skipping button", skill_name)
                continue
            label = skill_name
            if not learn_only:
                cost_map = rpg_logic.SKILL_COSTS.get(skill_name, {})
                cost_label = " · ".join(f"{k} {v}" for k, v in cost_map.items())
                if cost_label:
                    label += f" ({cost_label})"
            button = Button(label=label, style=discord.ButtonStyle.primary, row=0)
            button.callback = self._make_skill_callback(skill_name)
            self.add_item(button)

        back_button = Button(label="Back", style=discord.ButtonStyle.secondary, row=1)
        back_button.callback = self._back_callback
        self.add_item(back_button)

    def _make_skill_callback(self, skill_name):
        async def _callback(interaction: discord.Interaction):
            if self.learn_only:
                await self._learn_skill(interaction, skill_name)
            else:
                await self._use_skill(interaction, skill_name)

        return _callback

    async def _learn_skill(self, interaction: discord.Interaction, skill_name: str):
        user = self.cog.get_user(self.user_id)
        if skill_name not in user["skills"]:
            user["skills"].append(skill_name)
            save_json(PLAYERS_PATH, self.cog.user_data)
        menu_view = RPGView(self.cog, self.user_id)
        await interaction.response.edit_message(
            content=f"✅ Learned **{skill_name}**!\n\n{MENU_TITLE}",
            embed=None,
            view=menu_view,
        )

    async def _use_skill(self, interaction: discord.Interaction, skill_name: str):
        result = await self.cog.process_attack(interaction, skill_name=skill_name)
        await self.cog.render_after_attack(interaction, result)

    async def _back_callback(self, interaction: discord.Interaction):
        if self.learn_only:
            menu_view = RPGView(self.cog, self.user_id)
            await interaction.response.edit_message(
                content=MENU_TITLE,
                embed=None,
                view=menu_view,
            )
        else:
            battle_view = BattleView(self.cog, self.user_id)
            await battle_view.create_embed()
            await interaction.response.edit_message(
                content="⚔️ Battle!",
                embed=battle_view.embed,
                view=battle_view,
            )


class ShopView(OwnerOnlyView):
    denial_message = "❌ This shop isn't for you!"

    def __init__(self, cog, user_id):
        super().__init__(cog, user_id, timeout=30)
        self.embed = None
        self._populate_buttons()

    def _populate_buttons(self):
        for idx, item in enumerate(self.cog.shop_data.get("items", [])):
            button = Button(
                label=f"Buy {item['name'].capitalize()} ({item['price']}g)",
                style=discord.ButtonStyle.success,
                disabled=item["stock"] <= 0,
            )
            button.callback = self._make_buy_callback(idx)
            self.add_item(button)

        back_button = Button(label="Back to Menu", style=discord.ButtonStyle.secondary)
        back_button.callback = self._back_to_menu
        self.add_item(back_button)

    def _make_buy_callback(self, idx):
        async def _buy(interaction: discord.Interaction):
            await self._handle_buy(interaction, idx)

        return _buy

    async def _back_to_menu(self, interaction: discord.Interaction):
        menu_view = RPGView(self.cog, self.user_id)
        await interaction.response.edit_message(
            content=MENU_TITLE,
            embed=None,
            view=menu_view,
        )

    async def create_embed(self):
        user = self.cog.get_user(self.user_id)
        self.embed = discord.Embed(title="🛒 RPG Shop", color=0x2B2D31)
        self.embed.set_footer(text=f"Your Gold: {user['gold']} 💰")
        for item in self.cog.shop_data.get("items", []):
            price = self.cog.get_shop_price(user, item["price"])
            price_label = f"~~{item['price']}g~~ {price}g (THE_CROWN discount)" if price != item["price"] else f"{price}g"
            self.embed.add_field(
                name=f"{item['name'].capitalize()} ({item['stock']} left)",
                value=f"Price: {price_label}\nType: {item['type']}",
                inline=True,
            )

    async def _handle_buy(self, interaction: discord.Interaction, item_idx: int):
        user = self.cog.get_user(self.user_id)
        try:
            item_data = self.cog.shop_data["items"][item_idx]
        except IndexError:
            await interaction.response.send_message("❌ Item no longer available!", ephemeral=True)
            return

        if item_data["stock"] <= 0:
            await interaction.response.send_message("❌ This item is out of stock!", ephemeral=True)
            return

        price = self.cog.get_shop_price(user, item_data["price"])
        if user["gold"] < price:
            await interaction.response.send_message("❌ You don't have enough gold!", ephemeral=True)
            return

        user["gold"] -= price
        self.cog.add_to_inventory(user, item_data["name"])
        self.cog.shop_data["items"][item_idx]["stock"] -= 1

        save_json(PLAYERS_PATH, self.cog.user_data)
        save_json(SHOP_PATH, self.cog.shop_data)

        shop_view = ShopView(self.cog, self.user_id)
        await shop_view.create_embed()
        await interaction.response.edit_message(
            content=f"✅ Successfully bought {item_data['name']} for {price}g!",
            embed=shop_view.embed,
            view=shop_view,
        )


class RPG(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.user_data: dict = load_json(PLAYERS_PATH)
        self.shop_data: dict = load_json(SHOP_PATH)
        self.monsters: list = load_json_list(MONSTERS_PATH)
        self.regen_task = None
        self.restock_task = None

        self.SKILLS = {
            2: [
                {"name": "Power Strike", "cost_type": "stamina", "cost": 20, "effect": {"attack_multiplier": 1.5}},
                {"name": "Mana Shield", "cost_type": "mana", "cost": 30, "effect": {"defense_bonus": 5}},
            ],
            4: [
                {"name": "Fireball", "cost_type": "mana", "cost": 40, "effect": {"damage_boost": 10}},
                {"name": "Dodge", "cost_type": "stamina", "cost": 25, "effect": {"evasion_chance": 0.3}},
            ],
        }

        self.items = {
            "potion": {"type": "heal", "value": 30},
            "sword": {"type": "weapon", "value": 5},
            "shield": {"type": "armor", "value": 5},
            "rare_artifact": {"type": "special", "value": 50},
        }

        self._default_shop_items = [
            {"name": "potion", "price": 50, "stock": 10, "type": "heal"},
            {"name": "sword", "price": 100, "stock": 5, "type": "weapon"},
            {"name": "shield", "price": 80, "stock": 5, "type": "armor"},
            {"name": "rare_artifact", "price": 500, "stock": 1, "type": "special"},
        ]

        if not self.shop_data:
            self.shop_data = {"items": copy.deepcopy(self._default_shop_items)}
            save_json(SHOP_PATH, self.shop_data)

        if not self.monsters:
            self.monsters = [
                {"name": "Goblin", "min_level": 1, "max_level": 5, "health": 50, "attack": 5},
                {"name": "Rat", "min_level": 1, "max_level": 3, "health": 20, "attack": 2},
                {"name": "Giant Spider", "min_level": 1, "max_level": 4, "health": 25, "attack": 3},
                {"name": "Skeleton", "min_level": 2, "max_level": 5, "health": 35, "attack": 4},
                {"name": "Slime", "min_level": 1, "max_level": 3, "health": 30, "attack": 2},
                {"name": "Wolf", "min_level": 2, "max_level": 5, "health": 40, "attack": 5},
                {"name": "Kobold", "min_level": 1, "max_level": 5, "health": 45, "attack": 4},
                {"name": "Giant Bat", "min_level": 1, "max_level": 4, "health": 22, "attack": 3},
                {"name": "Zombie", "min_level": 2, "max_level": 6, "health": 50, "attack": 4},
                {"name": "Imp", "min_level": 1, "max_level": 4, "health": 25, "attack": 3},
                {"name": "Orc", "min_level": 3, "max_level": 8, "health": 80, "attack": 8},
                {"name": "Hobgoblin", "min_level": 5, "max_level": 10, "health": 70, "attack": 7},
                {"name": "Wight", "min_level": 6, "max_level": 12, "health": 85, "attack": 8},
                {"name": "Ogre", "min_level": 7, "max_level": 14, "health": 100, "attack": 10},
                {"name": "Troll", "min_level": 8, "max_level": 15, "health": 120, "attack": 12},
                {"name": "Dragon", "min_level": 10, "max_level": 20, "health": 200, "attack": 15},
                {"name": "Lich", "min_level": 15, "max_level": 20, "health": 180, "attack": 14},
                {"name": "Kraken", "min_level": 20, "max_level": 25, "health": 250, "attack": 18},
            ]
            save_json(MONSTERS_PATH, self.monsters)

    def get_user(self, user_id: str) -> dict:
        user = self.user_data.setdefault(user_id, {})
        for key, default in DEFAULT_USER.items():
            if key not in user:
                user[key] = default
        if not isinstance(user.get("inventory"), list):
            user["inventory"] = []
        if not isinstance(user.get("cooldowns"), dict):
            user["cooldowns"] = {}
        if not isinstance(user.get("skills"), list):
            user["skills"] = []
        if not isinstance(user.get("active_quests"), list):
            user["active_quests"] = []
        if not isinstance(user.get("quest_progress"), dict):
            user["quest_progress"] = {}
        user["health"] = min(user["health"], user["max_health"])
        user["stamina"] = min(user["stamina"], user["max_stamina"])
        user["mana"] = min(user["mana"], user["max_mana"])
        user["hunger"] = min(user.get("hunger", 100), user.get("max_hunger", 100))
        user["thirst"] = min(user.get("thirst", 100), user.get("max_thirst", 100))
        user["defeated"] = bool(user.get("defeated"))
        return user

    def add_to_inventory(self, user: dict, name: str, qty: int = 1, **extra) -> None:
        """Add a stackable item, or a procedural equipment item, to inventory.

        Stackable items (no `extra`) merge with an existing entry of the same
        name; equipment items (with `extra` fields like slot/bonus) are always
        appended as their own entry since each roll can be unique.
        """
        if not extra:
            for entry in user["inventory"]:
                if entry["name"] == name and entry.get("type") != "equipment":
                    entry["qty"] = entry.get("qty", 1) + qty
                    return
            user["inventory"].append({"name": name, "qty": qty})
        else:
            entry = {"name": name, "qty": qty}
            entry.update(extra)
            user["inventory"].append(entry)

    def remove_from_inventory(self, user: dict, name: str, qty: int = 1) -> bool:
        """Remove qty of a stackable item by name. Returns False if not enough held."""
        for entry in user["inventory"]:
            if entry["name"] == name and entry.get("type") != "equipment":
                if entry.get("qty", 1) < qty:
                    return False
                entry["qty"] -= qty
                if entry["qty"] <= 0:
                    user["inventory"].remove(entry)
                return True
        return False

    def get_inventory_qty(self, user: dict, name: str) -> int:
        for entry in user["inventory"]:
            if entry["name"] == name and entry.get("type") != "equipment":
                return entry.get("qty", 1)
        return 0

    def apply_faction_bonuses(self, user: dict, biome: str, world_data: dict) -> dict:
        """Applies the per-faction bonuses described by get_factions():
        WILD_WALKERS get a higher monster encounter rate in Forests,
        SHADOW_GUILD get a higher loot rate in Swamps. Mutates and returns
        world_data (a fresh per-call dict from get_world_location, safe to
        mutate)."""
        factions = user.get("factions", {})
        if biome == "Forest" and factions.get("WILD_WALKERS", 0) > 0:
            world_data["monster_rate"] = min(1.0, world_data["monster_rate"] * 1.5)
        if biome == "Swamp" and factions.get("SHADOW_GUILD", 0) > 0:
            world_data["loot_rate"] = min(1.0, world_data["loot_rate"] * 1.5)
        return world_data

    def get_shop_price(self, user: dict, base_price: int) -> int:
        """THE_CROWN's described "Discount in Town shops" bonus - 10% off
        for any member with rep in that faction."""
        if user.get("factions", {}).get("THE_CROWN", 0) > 0:
            return max(1, round(base_price * 0.9))
        return base_price

    async def cog_load(self):
        """Start the regeneration and restock tasks when cog loads."""
        self.regen_task = asyncio.create_task(self.regen_resources())
        self.restock_task = self.restock_shop.start()

    def cog_unload(self):
        """Cancel regeneration and restock tasks on cog unload."""
        if self.regen_task and not self.regen_task.done():
            self.regen_task.cancel()
        if self.restock_task:
            self.restock_task.cancel()

    @tasks.loop(minutes=10)
    async def restock_shop(self):
        """Restore each shop item's stock toward its default value."""
        try:
            for item in self.shop_data.get("items", []):
                default = next(
                    (d for d in self._default_shop_items if d["name"] == item.get("name")),
                    None,
                )
                if default is not None:
                    item["stock"] = min(default["stock"], item.get("stock", 0) + 1)
            save_json(SHOP_PATH, self.shop_data)
        except Exception:
            logger.exception("Error restocking shop")

    @restock_shop.before_loop
    async def before_restock(self):
        await self.client.wait_until_ready()

    async def regen_resources(self):
        """Regenerate 10 stamina/mana per minute; defeated players heal 5 HP/min.
        Also handles hunger and thirst decay."""
        await self.client.wait_until_ready()
        while not self.client.is_closed():
            try:
                await asyncio.sleep(60)
                for user_id in list(self.user_data.keys()):
                    user = self.get_user(user_id)
                    user["stamina"] = min(user["max_stamina"], user["stamina"] + 10)
                    user["mana"] = min(user["max_mana"], user["mana"] + 10)

                    # Hunger/Thirst decay (per minute)
                    user["hunger"] = max(0, user["hunger"] - 1)
                    user["thirst"] = max(0, user["thirst"] - 2)

                    # Starvation penalty
                    if user["hunger"] <= 0 or user["thirst"] <= 0:
                        user["health"] = max(0, user["health"] - 2)
                        if user["health"] <= 0:
                            user["defeated"] = True

                    if user.get("defeated"):
                        user["health"] = min(user["max_health"], user["health"] + 5)
                        if user["health"] > 0:
                            user["defeated"] = False
                save_json(PLAYERS_PATH, self.user_data)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in regen_resources")
                await asyncio.sleep(5)

    @app_commands.command(name="register", description="Start your RPG adventure!")
    @app_commands.guild_only()
    async def register(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id in self.user_data:
            await interaction.response.send_message("❌ You're already registered! Use `/playrpg` to start playing!", ephemeral=True)
            return

        self.get_user(user_id)
        save_json(PLAYERS_PATH, self.user_data)
        await interaction.response.send_message("🎉 Welcome to the RPG! Use `/playrpg` to access your adventure menu!", ephemeral=True)

    @app_commands.command(name="playrpg", description="Access your RPG menu")
    @app_commands.guild_only()
    async def playrpg(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id not in self.user_data:
            await interaction.response.send_message("❌ You need to register first with `/register`!", ephemeral=True)
            return

        view = RPGView(self, user_id)
        await interaction.response.send_message(
            MENU_TITLE,
            view=view,
            ephemeral=True,
        )

    async def explore_action(self, interaction: discord.Interaction) -> str:
        user_id = str(interaction.user.id)
        user = self.get_user(user_id)
        current_time = datetime.datetime.now().timestamp()

        if user.get("defeated"):
            return "💀 You are defeated and cannot explore! Wait for health regeneration or use a potion."

        if current_time - user["cooldowns"].get("explore", 0) < 5:
            remaining = 5 - (current_time - user["cooldowns"].get("explore", 0))
            return f"⏳ You need to wait {remaining:.1f}s before exploring again!"

        user["cooldowns"]["explore"] = current_time

        outcome = random.choice(["gold", "item", "monster", "nothing"])
        response = ""

        if outcome == "gold":
            gold_found = random.randint(10, 50)
            user["gold"] += gold_found
            response = f"💰 You found {gold_found} gold!"
        elif outcome == "item":
            item = random.choice(list(self.items.keys()))
            self.add_to_inventory(user, item)
            response = f"🎁 You found a {item}!"
        elif outcome == "monster":
            if not self.monsters:
                return "❌ No monsters are defined in the game!"
            monster = copy.deepcopy(rpg_logic.choose_monster(self.monsters, user["level"]))
            if monster is None:
                return "❌ No monsters are defined in the game!"
            user["current_monster"] = monster
            response = f"🐉 You encountered a {monster['name']}! Use the Battle menu to fight it!"
        else:
            response = "🌲 You explored but found nothing..."

        save_json(PLAYERS_PATH, self.user_data)
        return response

    async def process_attack(self, interaction: discord.Interaction, skill_name: str | None = None):
        user = self.get_user(str(interaction.user.id))

        if user.get("defeated"):
            return ("💀 You are defeated and cannot fight!", [])
        if "current_monster" not in user:
            return ("❌ No monster to fight!", [])

        monster = user["current_monster"]

        player_damage = 0
        dodged = False
        shielded = False
        if skill_name:
            skill_data = next(
                (s for level in self.SKILLS.values() for s in level if s["name"] == skill_name),
                None,
            )
            if not skill_data:
                return (f"❌ Skill {skill_name} not found!", [])

            cost_map = dict(rpg_logic.SKILL_COSTS.get(skill_name, {}))
            if user.get("factions", {}).get("ARCANE_ORDER", 0) > 0 and "mana" in cost_map:
                # ARCANE_ORDER's described "Faster Magic training" bonus - 20% cheaper mana costs.
                cost_map["mana"] = max(1, round(cost_map["mana"] * 0.8))
            for resource, cost in cost_map.items():
                if user.get(resource, 0) < cost:
                    return (f"❌ Not enough {resource} to use {skill_name}!", [])
            for resource, cost in cost_map.items():
                user[resource] -= cost

            base_damage = rpg_logic.player_attack_damage(user["attack"], user["level"])
            if skill_name == "Power Strike":
                player_damage = rpg_logic.skill_power_strike(base_damage)
            elif skill_name == "Fireball":
                player_damage = rpg_logic.skill_fireball(base_damage)
            elif skill_name == "Dodge":
                dodged = rpg_logic.skill_dodge_succeeds()
            elif skill_name == "Mana Shield":
                shielded = True
            else:
                player_damage = base_damage
        else:
            player_damage = rpg_logic.roll_crit(rpg_logic.player_attack_damage(user["attack"], user["level"]))

        monster["health"] -= player_damage

        if monster["health"] <= 0:
            exp_gain = rpg_logic.xp_reward(monster)
            gold_gain = random.randint(10, 30)
            user["experience"] += exp_gain
            user["gold"] += gold_gain
            response = f"⚔️ You defeated the {monster['name']}!\n🏆 Gained {exp_gain} XP and {gold_gain} gold!"
            kill_biome, _ = self.get_world_location(user["x"], user["y"])
            self.advance_quest_progress(user, "kill", kill_biome)
            if random.random() < 0.2:
                dropped_item = self.generate_random_item(monster["name"])
                self.add_to_inventory(
                    user,
                    dropped_item["name"],
                    type=dropped_item["type"],
                    slot=dropped_item["slot"],
                    bonus=dropped_item["bonus"],
                )
                response += f"\n✨ It dropped **{dropped_item['name']}**!"
            del user["current_monster"]
            user["cooldowns"]["battle"] = datetime.datetime.now().timestamp()

            unlock_names = []
            owned = set(user["skills"])
            while user["experience"] >= rpg_logic.xp_to_next_level(user["level"]):
                old_level = user["level"]
                user["level"] += 1
                rpg_logic.apply_level_up(user)
                response += f"\n🎉 Level up! You're now level {user['level']}!"
                for unlock_level in (2, 4):
                    if old_level < unlock_level <= user["level"]:
                        for skill in self.SKILLS.get(unlock_level, []):
                            if skill["name"] not in owned:
                                unlock_names.append(skill["name"])
                                owned.add(skill["name"])
            save_json(PLAYERS_PATH, self.user_data)
            return (response, unlock_names)

        if dodged:
            monster_damage = 0
        elif shielded:
            monster_damage = rpg_logic.skill_mana_shield(rpg_logic.monster_attack_damage(monster["attack"], user["defense"]))
        else:
            monster_damage = rpg_logic.monster_attack_damage(monster["attack"], user["defense"])

        user["health"] -= monster_damage
        save_json(PLAYERS_PATH, self.user_data)

        if user["health"] <= 0:
            user["health"] = 0
            user["defeated"] = True
            del user["current_monster"]
            return (
                "💀 You were defeated! Wait for health regeneration or use a potion to recover.",
                [],
            )

        if dodged:
            response = f"🌀 You dodged the {monster['name']}'s attack! It dealt no damage!"
        elif shielded:
            response = (
                f"🛡️ Mana Shield absorbed most of the damage!\n"
                f"💔 The {monster['name']} hit you for {monster_damage} damage!\n"
                f"❤️ Your health: {user['health']}/{user['max_health']}"
            )
        elif skill_name:
            response = (
                f"✨ You used **{skill_name}** for {player_damage} damage!\n"
                f"💔 The {monster['name']} hit you for {monster_damage} damage!\n"
                f"❤️ Your health: {user['health']}/{user['max_health']}"
            )
        else:
            response = (
                f"⚔️ You attacked the {monster['name']} for {player_damage} damage!\n"
                f"💔 The {monster['name']} hit you for {monster_damage} damage!\n"
                f"❤️ Your health: {user['health']}/{user['max_health']}"
            )
        return (response, [])

    async def render_after_attack(self, interaction: discord.Interaction, result):
        response, unlock_names = result
        user_id = str(interaction.user.id)
        user = self.get_user(user_id)

        if unlock_names:
            view = SkillMenuView(self, user_id, unlock_names, learn_only=True)
            await interaction.response.edit_message(content=response, embed=None, view=view)
            return

        if user.get("defeated"):
            await interaction.response.edit_message(content=response, embed=None, view=None)
            return

        if "current_monster" not in user:
            menu_view = RPGView(self, user_id)
            await interaction.response.edit_message(
                content=f"{response}\n\n{MENU_TITLE}",
                embed=None,
                view=menu_view,
            )
            return

        battle_view = BattleView(self, user_id)
        await battle_view.create_embed()
        await interaction.response.edit_message(
            content=response,
            embed=battle_view.embed,
            view=battle_view,
        )

    def get_world_location(self, x, y):
        biomes = {
            "Forest": {"monster_rate": 0.3, "loot_rate": 0.1},
            "Desert": {"monster_rate": 0.2, "loot_rate": 0.05},
            "Mountains": {"monster_rate": 0.4, "loot_rate": 0.15},
            "Swamp": {"monster_rate": 0.5, "loot_rate": 0.1},
            "Plains": {"monster_rate": 0.1, "loot_rate": 0.05},
            "Town": {"monster_rate": 0.0, "loot_rate": 0.0}
        }
        if x == 0 and y == 0:
            return "Town", biomes["Town"]
        # A local Random instance keeps a given tile's biome deterministic
        # without disturbing the global random state used by combat rolls.
        tile_rng = random.Random(f"{x}_{y}")
        biome_name = tile_rng.choice(list(biomes.keys()))
        if biome_name == "Town" and tile_rng.random() > 0.05:
            biome_name = "Plains"
        return biome_name, biomes[biome_name]

    async def handle_move(self, interaction: discord.Interaction, dx, dy):
        user_id = str(interaction.user.id)
        user = self.get_user(user_id)
        if user["stamina"] < 5:
            await interaction.response.send_message("You're too exhausted to move! Use a potion or wait for regen.", ephemeral=True)
            return
        user["x"] += dx
        user["y"] += dy
        user["stamina"] -= 5
        biome, world_data = self.get_world_location(user["x"], user["y"])
        world_data = self.apply_faction_bonuses(user, biome, world_data)
        msg = f"🚶 You moved to **({user['x']}, {user['y']})**. You are now in the **{biome}**."
        self.advance_quest_progress(user, "move", biome)
        roll = random.random()
        if roll < world_data["monster_rate"]:
            # In S.A.R.A.H's current logic, we set 'current_monster' in the user object
            if not self.monsters:
                await interaction.response.send_message(msg + "\n❌ No monsters in this world!", ephemeral=True)
                return
            monster = copy.deepcopy(random.choice(self.monsters))
            user["current_monster"] = monster
            msg += f"\n🐉 You encountered a **{monster['name']}**! Use the RPG menu to fight!"
        elif roll < world_data["monster_rate"] + world_data["loot_rate"]:
            loot_gold = random.randint(5, 50)
            user["gold"] += loot_gold
            msg += f"\n💰 You found a discarded pouch with **{loot_gold} gold**!"
        save_json(PLAYERS_PATH, self.user_data)
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="north", description="Move North in the RPG world")
    async def move_north(self, interaction: discord.Interaction):
        await self.handle_move(interaction, 0, 1)

    @app_commands.command(name="south", description="Move South in the RPG world")
    async def move_south(self, interaction: discord.Interaction):
        await self.handle_move(interaction, 0, -1)

    @app_commands.command(name="east", description="Move East in the RPG world")
    async def move_east(self, interaction: discord.Interaction):
        await self.handle_move(interaction, 1, 0)

    @app_commands.command(name="west", description="Move West in the RPG world")
    async def move_west(self, interaction: discord.Interaction):
        await self.handle_move(interaction, -1, 0)

    @app_commands.command(name="where", description="Check your RPG location")
    async def where(self, interaction: discord.Interaction):
        user = self.get_user(str(interaction.user.id))
        biome, _ = self.get_world_location(user["x"], user["y"])
        await interaction.response.send_message(f"📍 You are at **({user['x']}, {user['y']})** in the **{biome}**.", ephemeral=True)

    def get_factions(self):
        return {
            "THE_CROWN": {"description": "The ruling monarchy of the realm.", "bonus": "Discount in Town shops"},
            "SHADOW_GUILD": {"description": "A secret network of thieves and assassins.", "bonus": "Higher loot rate in Swamps"},
            "ARCANE_ORDER": {"description": "Masters of the mystic arts.", "bonus": "Faster Magic training"},
            "WILD_WALKERS": {"description": "Protectors of the natural world.", "bonus": "Higher monster rate in Forests"}
        }

    @app_commands.command(name="factions", description="List all available factions and your standing")
    async def factions(self, interaction: discord.Interaction):
        user = self.get_user(str(interaction.user.id))
        f_db = self.get_factions()

        res = "**Available Factions:**\n"
        for f, info in f_db.items():
            rep = user["factions"].get(f, 0)
            res += f"**{f}**: {info['description']} | Your Rep: {rep}\n"

        await interaction.response.send_message(res, ephemeral=True)

    @app_commands.command(name="join", description="Join a faction")
    async def join_faction(self, interaction: discord.Interaction, faction: str):
        faction = faction.upper()
        f_db = self.get_factions()

        if faction not in f_db:
            await interaction.response.send_message("That faction does not exist!", ephemeral=True)
            return

        user = self.get_user(str(interaction.user.id))
        user["factions"][faction] = 10 # Starting rep
        save_json(PLAYERS_PATH, self.user_data)
        await interaction.response.send_message(f"🤝 You have joined **{faction}**!", ephemeral=True)

    def get_available_quests(self, user):
        x, y = user["x"], user["y"]
        biome, _ = self.get_world_location(x, y)

        quests = []
        if biome == "Town":
            quests.append({
                "id": "q1", "title": "Town Cleanup", "desc": "Move 5 times in the town",
                "reward": {"gold": 50, "xp": 20},
                "objective": {"type": "move", "biome": "Town", "count": 5},
            })
            quests.append({
                "id": "q2", "title": "Merchant Guard", "desc": "Hunt 1 monster",
                "reward": {"gold": 100, "xp": 50},
                "objective": {"type": "kill", "biome": None, "count": 1},
            })
        elif biome == "Forest":
            quests.append({
                "id": "q3", "title": "Wolf Hunt", "desc": "Defeat a monster in the forest",
                "reward": {"gold": 80, "xp": 60},
                "objective": {"type": "kill", "biome": "Forest", "count": 1},
            })

        return quests

    @app_commands.command(name="quests", description="View available quests in your current location")
    async def quests(self, interaction: discord.Interaction):
        user = self.get_user(str(interaction.user.id))
        available = self.get_available_quests(user)

        if not available:
            await interaction.response.send_message("No quests available here.", ephemeral=True)
            return

        res = "**Available Quests:**\n"
        for q in available:
            res += f"**{q['title']}**: {q['desc']} | Reward: {q['reward']}\n"

        await interaction.response.send_message(res, ephemeral=True)

    @app_commands.command(name="accept", description="Accept a quest by title")
    async def accept_quest(self, interaction: discord.Interaction, quest_title: str):
        user = self.get_user(str(interaction.user.id))
        available = self.get_available_quests(user)

        found = None
        for q in available:
            if q["title"].lower() == quest_title.lower():
                found = q
                break

        if not found:
            await interaction.response.send_message("Quest not found!", ephemeral=True)
            return

        if any(q["id"] == found["id"] for q in user["active_quests"]):
            await interaction.response.send_message(f"You already have **{found['title']}** active!", ephemeral=True)
            return

        user["active_quests"].append(found)
        user["quest_progress"][found["id"]] = 0
        save_json(PLAYERS_PATH, self.user_data)
        await interaction.response.send_message(f"📜 Accepted **{found['title']}**! ({found['desc']})", ephemeral=True)

    def advance_quest_progress(self, user, obj_type, biome):
        """Increments progress on any active quest whose objective matches
        obj_type/biome ('kill'/'move' events call this from wherever those
        actions actually happen - process_attack, handle_move)."""
        for quest in user["active_quests"]:
            objective = quest.get("objective")
            if not objective or objective["type"] != obj_type:
                continue
            if objective["biome"] is not None and objective["biome"] != biome:
                continue
            user["quest_progress"][quest["id"]] = user["quest_progress"].get(quest["id"], 0) + 1

    @app_commands.command(name="turnin", description="Turn in a completed quest by title")
    async def turnin_quest(self, interaction: discord.Interaction, quest_title: str):
        user = self.get_user(str(interaction.user.id))

        found = None
        for q in user["active_quests"]:
            if q["title"].lower() == quest_title.lower():
                found = q
                break

        if not found:
            await interaction.response.send_message("You don't have that quest active!", ephemeral=True)
            return

        objective = found.get("objective", {})
        progress = user["quest_progress"].get(found["id"], 0)
        required = objective.get("count", 0)
        if progress < required:
            await interaction.response.send_message(
                f"📜 **{found['title']}** isn't done yet ({progress}/{required}).", ephemeral=True
            )
            return

        reward = found.get("reward", {})
        gold = reward.get("gold", 0)
        xp = reward.get("xp", 0)
        user["gold"] += gold
        user["experience"] += xp

        user["active_quests"] = [q for q in user["active_quests"] if q["id"] != found["id"]]
        user["quest_progress"].pop(found["id"], None)

        response = f"✅ Turned in **{found['title']}**! Gained {gold} gold and {xp} XP."
        while user["experience"] >= rpg_logic.xp_to_next_level(user["level"]):
            user["level"] += 1
            rpg_logic.apply_level_up(user)
            response += f"\n🎉 Level up! You're now level {user['level']}!"

        save_json(PLAYERS_PATH, self.user_data)
        await interaction.response.send_message(response, ephemeral=True)

    def generate_random_item(self, monster_name):
        prefixes = {
            "Common": 1.0,
            "Sharp": 1.2,
            "Dull": 0.8,
            "Ancient": 1.5,
            "Cursed": 0.5,
            "Blessed": 1.4,
            "Masterwork": 2.0,
            "Rusted": 0.6
        }
        if "Slime" in monster_name:
            base_item, skill = "Slime Sword", "BRAWLING"
        elif "Goblin" in monster_name:
            base_item, skill = "Goblin Dagger", "PIERCING"
        elif "Skeleton" in monster_name:
            base_item, skill = "Bone Shield", "DEFENCE"
        elif "Orc" in monster_name:
            base_item, skill = "Orcish Axe", "BRAWLING"
        else:
            base_item, skill = "Mystic Artifact", "MEDITATION"

        prefix = random.choices(list(prefixes.keys()), weights=[40, 15, 15, 10, 5, 5, 5, 5])[0]
        mult = prefixes[prefix]
        bonus_val = int(5 * mult)

        return {
            "name": f"{prefix} {base_item}",
            "type": "equipment",
            "slot": "weapon" if any(x in base_item for x in ["Sword", "Dagger", "Axe"]) else "offhand" if "Shield" in base_item else "body",
            "bonus": {skill: bonus_val}
        }

    @app_commands.command(name="equip", description="Equip a piece of gear from your inventory")
    async def equip(self, interaction: discord.Interaction, item_name: str):
        user = self.get_user(str(interaction.user.id))
        inv = user["inventory"]

        found_item = next(
            (entry for entry in inv if entry.get("type") == "equipment" and entry["name"].lower() == item_name.lower()),
            None,
        )
        if not found_item:
            await interaction.response.send_message(
                f"❌ You don't have any equippable gear named '{item_name}'!", ephemeral=True
            )
            return

        slot = found_item.get("slot", "misc")
        inv.remove(found_item)
        previous = user["equipped"].get(slot)
        if previous:
            inv.append(previous)
        user["equipped"][slot] = found_item

        save_json(PLAYERS_PATH, self.user_data)
        response = f"🛠️ Equipped **{found_item['name']}** in the {slot} slot!"
        if previous:
            response += f"\n(Unequipped **{previous['name']}**, moved back to inventory.)"
        await interaction.response.send_message(response, ephemeral=True)

    @app_commands.command(name="stats", description="Check your character stats")
    @app_commands.guild_only()
    async def stats(self, interaction: discord.Interaction):
        user = self.get_user(str(interaction.user.id))
        embed = discord.Embed(title=f"{interaction.user.display_name}'s Stats", color=0x00FF00)
        embed.add_field(name="Level", value=user["level"], inline=True)
        embed.add_field(name="Health", value=f"{user['health']}/{user['max_health']}", inline=True)
        embed.add_field(name="Stamina", value=f"{user['stamina']}/{user['max_stamina']}", inline=True)
        embed.add_field(name="Mana", value=f"{user['mana']}/{user['max_mana']}", inline=True)
        embed.add_field(name="Hunger", value=f"{user['hunger']}/{user['max_hunger']}", inline=True)
        embed.add_field(name="Thirst", value=f"{user['thirst']}/{user['max_thirst']}", inline=True)
        embed.add_field(name="Attack", value=user["attack"], inline=True)
        embed.add_field(name="Defense", value=user["defense"], inline=True)
        embed.add_field(
            name="Experience",
            value=f"{user['experience']}/{rpg_logic.xp_to_next_level(user['level'])}",
            inline=True,
        )
        embed.add_field(name="Gold", value=user["gold"], inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="See the top RPG players")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🏆 RPG Leaderboard", color=0x00FF00)

        ranked = sorted(
            self.user_data.items(),
            key=lambda item: (item[1].get("level", 1), item[1].get("experience", 0)),
            reverse=True,
        )[:10]

        lines = []
        for idx, (user_id, user) in enumerate(ranked, 1):
            member = interaction.guild.get_member(int(user_id))
            name = member.mention if member else "Unknown User"
            lines.append(f"{idx}. {name} — Level {user.get('level', 1)}, {user.get('gold', 0)} gold")

        embed.description = "\n".join(lines) if lines else "No adventurers yet — use `/register` to start!"
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="use", description="Use an item from your inventory")
    @app_commands.guild_only()
    async def use(self, interaction: discord.Interaction, item: str):
        user_id = str(interaction.user.id)
        user = self.get_user(user_id)
        item = item.lower()

        if self.get_inventory_qty(user, item) <= 0:
            await interaction.response.send_message(f"You don't have any {item}!", ephemeral=True)
            return

        item_data = self.items.get(item)
        if not item_data:
            await interaction.response.send_message("That item doesn't exist!", ephemeral=True)
            return

        item_type = item_data["type"]
        if item_type == "heal":
            user["health"] = min(user["max_health"], user["health"] + item_data["value"])
            user["defeated"] = False
            response = f"❤️ Healed for {item_data['value']} HP!"
        elif item_type == "weapon":
            user["attack"] += item_data["value"]
            response = f"⚔️ Attack increased by {item_data['value']}!"
        elif item_type == "armor":
            user["defense"] += item_data["value"]
            response = f"🛡️ Defense increased by {item_data['value']}!"
        elif item_type == "special":
            user["gold"] += item_data.get("value", 50)
            response = f"💰 The rare artifact granted you {item_data.get('value', 50)} gold!"
        else:
            await interaction.response.send_message("❌ That item can't be used!", ephemeral=True)
            return

        self.remove_from_inventory(user, item)

        save_json(PLAYERS_PATH, self.user_data)
        await interaction.response.send_message(response, ephemeral=True)


async def setup(client):
    await client.add_cog(RPG(client))
    logger.info("RPG System Online")
