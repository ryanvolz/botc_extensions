# ----------------------------------------------------------------------------
# Copyright (c) 2020 Ryan Volz
# All rights reserved.
#
# Distributed under the terms of the BSD 3-clause license.
#
# The full license is in the LICENSE file, distributed with this software.
#
# SPDX-License-Identifier: BSD-3-Clause
# ----------------------------------------------------------------------------
"""Discord extension for Blood on the Clocktower."""

import ast
import collections
import functools
import math
import random
import re
import typing

import discord
from discord.ext import commands

from ..utils.commands import acknowledge_command, delete_command_message
from ..utils.persistent_settings import DiscordIDSettings

EMOJI_DIGITS = {
    str(num): "{}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}".format(num)
    for num in range(10)
}
EMOJI_DIGITS[" "] = "\N{BLACK LARGE SQUARE}"
EMOJI_DIGITS["10"] = "\N{KEYCAP TEN}"
EMOJI_DIGITS["*"] = "*\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}"

BOTC_COUNT = {
    5: dict(town=3, out=0, minion=1, demon=1),
    6: dict(town=3, out=1, minion=1, demon=1),
    7: dict(town=5, out=0, minion=1, demon=1),
    8: dict(town=5, out=1, minion=1, demon=1),
    9: dict(town=5, out=2, minion=1, demon=1),
    10: dict(town=7, out=0, minion=2, demon=1),
    11: dict(town=7, out=1, minion=2, demon=1),
    12: dict(town=7, out=2, minion=2, demon=1),
    13: dict(town=9, out=0, minion=3, demon=1),
    14: dict(town=9, out=1, minion=3, demon=1),
    15: dict(town=9, out=2, minion=3, demon=1),
}

BOTC_CATEGORY_DEFAULT_SETTINGS = dict(
    category_re=re.compile(r".*(CLOCKTOWER)|(BOTC).*", re.IGNORECASE),
    dead_emoji="💀",
    vote_emoji="👻",
    novote_emoji="🚫",
    traveling_emoji="🚁",
)

BOTC_MESSAGE_DELETE_DELAY = 60


def is_called_from_botc_category():
    """Check if called from a BOTC town category."""

    async def predicate(ctx):
        if ctx.guild is None:
            # don't restrict match if command is in a DM
            return True
        else:
            cat_id = ctx.message.channel.category.id
            return ctx.bot.botc_townsquare_settings.get(
                cat_id, "is_enabled", False
            ) or ctx.bot.botc_townsquare_settings.get(cat_id, "category_re").match(
                ctx.message.channel.category.name
            )

    return commands.check(predicate)


def require_locked_town():
    """Return command decorator that raises an error if the town is lunocked."""

    def decorator(command):
        @functools.wraps(command)
        async def wrapper(self, ctx, *args, **kwargs):
            town = self.bot.botc_townsquare.get_town(ctx)
            if not town["locked"]:
                raise BOTCTownSquareErrors.TownUnlocked(
                    "Command requires a locked town."
                )
            return await command(self, ctx, *args, **kwargs)

        return wrapper

    return decorator


def require_unlocked_town():
    """Return command decorator that raises an error if the town is locked."""

    def decorator(command):
        @functools.wraps(command)
        async def wrapper(self, ctx, *args, **kwargs):
            town = self.bot.botc_townsquare.get_town(ctx)
            if town["locked"]:
                raise BOTCTownSquareErrors.TownLocked(
                    "Command requires an unlocked town."
                )
            return await command(self, ctx, *args, **kwargs)

        return wrapper

    return decorator


class BOTCTownSquareErrors(object):
    class BadPlayerArgument(commands.UserInputError):
        """Bad argument intended to resolve to a player."""

        def __init__(self, message, member, *args):
            self.member = member
            super().__init__(message, *args)

    class BadSeatArgument(commands.UserInputError):
        """Bad argument intented to resolve to a player seat number."""

        pass

    class TownLocked(commands.UserInputError):
        """Town is locked for a command requiring an unlocked town."""

        pass

    class TownUnlocked(commands.UserInputError):
        """Town is unlocked for a command requiring a locked town."""

        pass


class BOTCTownSquareErrorMixin(object):
    async def cog_command_error(self, ctx, error):
        """Handle common cog errors."""
        if isinstance(error, BOTCTownSquareErrors.BadPlayerArgument):
            await ctx.send(
                f"This game isn't meant for {error.member.display_name}.",
                delete_after=BOTC_MESSAGE_DELETE_DELAY,
            )
        elif isinstance(error, BOTCTownSquareErrors.BadSeatArgument):
            await ctx.send("That seat doesn't look like anything to me.")
        elif isinstance(error, BOTCTownSquareErrors.TownLocked):
            locked_message = (
                f"Before I'll allow that, you'll need to put the town into a deep and"
                f" dreamless slumber. [`{ctx.prefix}unlock` first]"
            )
            await ctx.send(locked_message, delete_after=BOTC_MESSAGE_DELETE_DELAY)
        elif isinstance(error, BOTCTownSquareErrors.TownUnlocked):
            unlocked_message = (
                f"This game isn't meant for anyone yet. [`{ctx.prefix}lock` first]"
            )
            await ctx.send(unlocked_message, delete_after=BOTC_MESSAGE_DELETE_DELAY)
        else:
            # if we're not handling the error here, return so the rest doesn't happen
            return
        # mark error as handled so that bot error handler ignores it
        error.handled = True
        # delete errored command message with same delay as deletion of bot's response
        await ctx.message.delete(delay=BOTC_MESSAGE_DELETE_DELAY)


class BOTCTownSquare(object):
    """Blood on the Clocktower Town Square."""

    def __init__(self, bot):
        """Load/initialize state for the town square."""
        self.bot = bot
        self.towns = collections.defaultdict(self._empty_town)
        self.name_regexes = {}

    @staticmethod
    def _empty_town():
        return dict(
            players=set(),
            player_order=[],
            player_info=collections.defaultdict(
                lambda: dict(seat=None, dead=False, num_votes=None, traveling=False)
            ),
            travelers=set(),
            storytellers=set(),
            locked=False,
            nomination=None,
            prev_nomination=None,
        )

    def teardown(self):
        """Save state for the town square."""
        pass

    def get_town(self, ctx):
        """Return the town dictionary for the command's category."""
        return self.towns[ctx.message.channel.category]

    def format_name_re(self, category):
        """Format BOTC name regular expression using the category settings."""
        name_re_template = (
            r"^(?:(?P<seat>_\d+)|(?P<st>!ST))?"
            r"\s*"
            r"(?P<dead>{dead_emoji})?"
            r"(?P<votes>{novote_emoji}|{vote_emoji}+)?"
            r"(?P<traveling>{traveling_emoji})?"
            r"\s*"
            r"(?P<nick>.*)"
        )
        emoji_vars = ["dead_emoji", "novote_emoji", "vote_emoji", "traveling_emoji"]
        emojis = {
            k: self.bot.botc_townsquare_settings.get(category.id, k) for k in emoji_vars
        }
        name_re = re.compile(name_re_template.format(**emojis))
        return name_re

    def get_name_re(self, category):
        """Get BOTC name regular expression from the category settings."""
        try:
            return self.name_regexes[category.id]
        except KeyError:
            name_re = self.format_name_re(category)
            self.name_regexes[category.id] = name_re
            return name_re

    def match_name_re(self, category, member):
        """Match a display name to the name regex, extracting player state and nick."""
        return self.get_name_re(category).match(member.display_name)

    def player_nickname_components(self, ctx, member):
        """Get a players' nickname components based on their data in player_info."""
        category = ctx.message.channel.category
        info = self.get_town(ctx)["player_info"][member]
        fill = dict(seat="", dead="", votes="", traveling="")
        fill["nick"] = self.match_name_re(category, member)["nick"]
        # build the info-derived fill values for the nickname string
        if info["seat"] is not None:
            fill["seat"] = f"_{info['seat']:02d}"
        if info["dead"]:
            fill["dead"] = self.bot.botc_townsquare_settings.get(
                category.id, "dead_emoji"
            )
        if info["num_votes"] is not None:
            if info["num_votes"] == 0:
                fill["votes"] = self.bot.botc_townsquare_settings.get(
                    category.id, "novote_emoji"
                )
            else:
                vote_emoji = self.bot.botc_townsquare_settings.get(
                    category.id, "vote_emoji"
                )
                fill["votes"] = info["num_votes"] * vote_emoji
        if info["traveling"]:
            fill["traveling"] = self.bot.botc_townsquare_settings.get(
                category.id, "traveling_emoji"
            )
        return fill

    async def set_player_nickname(self, ctx, member):
        """Set a players' nickname based on their data in player_info."""
        fill = self.player_nickname_components(ctx, member)
        nickname = "{seat}{dead}{votes}{traveling} {nick}".format(**fill)
        await member.edit(nick=nickname)

    async def set_player_info(self, ctx, member, **kwargs):
        """Set new values for player info and then adjust their nickname."""
        info = self.get_town(ctx)["player_info"][member]
        info.update(kwargs)
        await self.set_player_nickname(ctx, member)

    async def set_storyteller_nickname(self, ctx, member):
        """Set a member's nickname to have storyteller markings."""
        nick = self.match_name_re(ctx.message.channel.category, member)["nick"]
        name = f"!ST {nick}"
        await member.edit(nick=name)

    async def restore_name(self, ctx, member):
        """Restore a member's nickname after playing."""
        nick = self.match_name_re(ctx.message.channel.category, member)["nick"]
        name = f"{nick}"
        await member.edit(nick=name)

    async def resolve_member_arg(self, ctx, member):
        """Resolve argument intended to identify a member or player/storyteller."""
        if member is None:
            # member is None if no argument is passed, resolve to author
            member = ctx.message.author
        elif isinstance(member, discord.Member):
            # otherwise member is either a discord.Member...
            pass
        else:
            # or an int, representing seat order
            try:
                member = self.get_town(ctx)["player_order"][member - 1]
            except IndexError:
                if member == 0 and len(self.get_town(ctx)["storytellers"]) == 1:
                    member = self.get_town(ctx)["storytellers"].pop()
                else:
                    raise BOTCTownSquareErrors.BadSeatArgument("Seat number is invalid")
        return member

    async def resolve_player_arg(self, ctx, member):
        """Resolve member argument intended to identify a player."""
        member = await self.resolve_member_arg(ctx, member)
        # now verify that the member is a player
        if member in self.get_town(ctx)["players"]:
            return member
        else:
            raise BOTCTownSquareErrors.BadPlayerArgument(
                "Member isn't a player", member
            )


class BOTCTownSquareSetup(BOTCTownSquareErrorMixin, commands.Cog, name="Setup"):
    """Commands for Blood on the Clocktower voice/text town square setup.

    If you want to play in the next game, use the `play` command in the game's text
    chat. This will modify your nickname to include a seat number. If you want to be a
    traveler in the game, use `travel` instead.

    Even though the seating is virtual, you might want to 'sit' next to someone else or
    have a particular number. You can use the `sit` command followed by a seat number,
    like `.sit 4`, to move yourself to a particular seat. The current occupant and
    everyone in-between will shift toward your old seat. Anyone can also use the
    `shuffle` command to assign seats randomly.

    Once the town is locked by the Storyteller, in-game commands become active.

    """

    def __init__(self, bot):
        """Initialize cog for town square setup commands."""
        self.bot = bot

    async def cog_check(self, ctx):
        """Check that setup commands are called from a guild and a town category."""
        result = await commands.guild_only().predicate(
            ctx
        ) and await is_called_from_botc_category().predicate(ctx)
        return result

    @commands.command(brief="Add a player", usage="[<name>]")
    @require_unlocked_town()
    @delete_command_message()
    async def play(self, ctx, *, member: discord.Member = None):
        """Set the caller or given user as a player.

        Indicate another player if necessary using their *exact* name/tag.

        """
        town = self.bot.botc_townsquare.get_town(ctx)
        if member is None:
            member = ctx.message.author
        if member in town["players"]:
            return
        if member in town["storytellers"]:
            await ctx.invoke(self.unstorytell)
        town["players"].add(member)
        order = town["player_order"]
        order.append(member)
        number = len(order)
        await self.bot.botc_townsquare.set_player_info(ctx, member, seat=number)
        player_role = discord.utils.get(ctx.guild.roles, name="Playing BOTC")
        await member.add_roles(player_role)

    @commands.command(
        aliases=["quit"], brief="Remove a player", usage="[<seat>|<name>]"
    )
    @require_unlocked_town()
    @delete_command_message()
    async def unplay(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Remove the caller or given user as a player, also restoring name.

        Indicate another player if necessary using either their seat number or their
        *exact* name/tag.

        """
        town = self.bot.botc_townsquare.get_town(ctx)
        member = await self.bot.botc_townsquare.resolve_member_arg(ctx, member)
        if member in town["travelers"]:
            await ctx.invoke(self.untravel, member=member)
        if member in town["players"]:
            town["players"].remove(member)
            town["player_order"].remove(member)
        await self.bot.botc_townsquare.restore_name(ctx, member)
        player_role = discord.utils.get(ctx.guild.roles, name="Playing BOTC")
        await member.remove_roles(player_role)
        for idx, player in enumerate(town["player_order"]):
            if town["player_info"][player]["seat"] != idx + 1:
                await self.bot.botc_townsquare.set_player_info(
                    ctx, player, seat=idx + 1
                )

    @commands.command(brief="Set player as a traveler", usage="[<seat>|<name>]")
    @require_unlocked_town()
    @delete_command_message()
    async def travel(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Set the caller or given user as a traveler.

        Indicate another player if necessary using either their seat number (if already
        a player) or their *exact* name/tag.

        """
        town = self.bot.botc_townsquare.get_town(ctx)
        member = await self.bot.botc_townsquare.resolve_member_arg(ctx, member)
        if member not in town["players"]:
            await ctx.invoke(self.play, member=member)
        town["travelers"].add(member)
        await self.bot.botc_townsquare.set_player_info(ctx, member, traveling=True)
        traveler_role = discord.utils.get(ctx.guild.roles, name="Traveling BOTC")
        await member.add_roles(traveler_role)

    @commands.command(brief="Unset player as a traveler", usage="[<seat>|<name>]")
    @require_unlocked_town()
    @delete_command_message()
    async def untravel(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Unset the caller or given user as a traveler.

        Indicate another player if necessary using either their seat number or their
        *exact* name/tag.

        """
        town = self.bot.botc_townsquare.get_town(ctx)
        member = await self.bot.botc_townsquare.resolve_player_arg(ctx, member)
        if member not in town["travelers"]:
            return
        town["travelers"].remove(member)
        await self.bot.botc_townsquare.set_player_info(ctx, member, traveling=False)
        traveler_role = discord.utils.get(ctx.guild.roles, name="Traveling BOTC")
        await member.remove_roles(traveler_role)

    @commands.command(
        name="storytell", aliases=["st"], brief="Add a storyteller", usage="[<name>]"
    )
    @require_unlocked_town()
    @delete_command_message()
    async def storytell(self, ctx, *, member: discord.Member = None):
        """Set the caller or given user as a storyteller.

        Indicate another player if necessary using their *exact* name/tag.

        """
        town = self.bot.botc_townsquare.get_town(ctx)
        if member is None:
            member = ctx.message.author
        if member in town["storytellers"]:
            return
        if member in town["players"]:
            await ctx.invoke(self.unplay, member=member)
        town["storytellers"].add(member)
        await self.bot.botc_townsquare.set_storyteller_nickname(ctx, member)
        storyteller_role = discord.utils.get(ctx.guild.roles, name="Storytelling BOTC")
        await member.add_roles(storyteller_role)

    @commands.command(
        name="unstorytell", aliases=["unst"], brief="Unset storyteller(s)"
    )
    @require_unlocked_town()
    @delete_command_message()
    async def unstorytell(self, ctx):
        """Unset the existing storyteller(s)."""
        town = self.bot.botc_townsquare.get_town(ctx)
        for storyteller in list(town["storytellers"]):
            town["storytellers"].remove(storyteller)
            await self.bot.botc_townsquare.restore_name(ctx, storyteller)
            storyteller_role = discord.utils.get(
                ctx.guild.roles, name="Storytelling BOTC"
            )
            await storyteller.remove_roles(storyteller_role)

    @commands.command(
        brief="Move player to a given seat", usage="<new-seat> [<old-seat>|<name>]"
    )
    @require_unlocked_town()
    @delete_command_message()
    async def sit(
        self, ctx, seat: int, *, member: typing.Union[int, discord.Member] = None
    ):
        """Move the caller or given user's seat to the given new seat number.

        The current occupant of the given seat, and everyone between that seat and the
        old seat, will be shifted toward the old seat.

        To move someone else, use their seat number of their *exact* name/tag as the
        optional second argument.

        """
        town = self.bot.botc_townsquare.get_town(ctx)
        member = await self.bot.botc_townsquare.resolve_player_arg(ctx, member)
        order = town["player_order"]
        oldindex = order.index(member)
        newindex = seat - 1
        # puts member in the given seat while shifting the existing occupants
        # between the new seat and old toward the old seat
        order.insert(newindex, order.pop(oldindex))
        for idx, player in enumerate(order):
            if town["player_info"][player]["seat"] != idx + 1:
                await self.bot.botc_townsquare.set_player_info(
                    ctx, player, seat=idx + 1
                )

    @commands.command(brief="Shuffle seat order")
    @require_unlocked_town()
    @delete_command_message()
    async def shuffle(self, ctx):
        """Shuffle the seat order of the current players."""
        town = self.bot.botc_townsquare.get_town(ctx)
        order = town["player_order"]
        random.shuffle(order)
        for idx, player in enumerate(order):
            if town["player_info"][player]["seat"] != idx + 1:
                await self.bot.botc_townsquare.set_player_info(
                    ctx, player, seat=idx + 1
                )


class BOTCTownSquareStorytellers(
    BOTCTownSquareErrorMixin, commands.Cog, name="Storytellers"
):
    """Commands for Blood on the Clocktower voice/text storytellers.

    Once all players are ready, use the `lock` command to freeze the player list and
    seat assignments. If you need to make adjustments mid-game, use the `unlock`
    command to re-enable the game setup commands.

    After the game, use the `clear` command to erase the game state and reset the
    players' nicknames and roles.

    """

    def __init__(self, bot):
        """Initialize cog for town square storyteller commands."""
        self.bot = bot

    async def cog_check(self, ctx):
        """Check that commands come from a storyteller in a game category."""
        result = await commands.guild_only().predicate(
            ctx
        ) and await is_called_from_botc_category().predicate(ctx)
        # checking permissions will raise an exception if failed, but we then want to
        # be able to check the role instead
        try:
            await commands.has_guild_permissions(administrator=True).predicate(ctx)
        except commands.MissingPermissions:
            pass
        else:
            return result
        result = result and await commands.has_role("Storytelling BOTC").predicate(ctx)
        return result

    @commands.command(name="lock", brief="Lock the town")
    @delete_command_message()
    async def lock(self, ctx):
        """Start a game with the current players, locking the town and seat order."""
        town = self.bot.botc_townsquare.get_town(ctx)
        town["locked"] = True
        await acknowledge_command(ctx)

    @commands.command(name="unlock", brief="Unlock the town")
    @delete_command_message()
    async def unlock(self, ctx):
        """Stop (pause) a game, unlocking the town and seat order."""
        town = self.bot.botc_townsquare.get_town(ctx)
        town["locked"] = False
        await acknowledge_command(ctx)

    @commands.command(brief="End game and clear the town")
    @delete_command_message()
    async def clear(self, ctx):
        """Clear the current town, erasing game state and restoring names."""
        town = self.bot.botc_townsquare.get_town(ctx)
        player_role = discord.utils.get(ctx.guild.roles, name="Playing BOTC")
        storyteller_role = discord.utils.get(ctx.guild.roles, name="Storytelling BOTC")
        traveler_role = discord.utils.get(ctx.guild.roles, name="Traveling BOTC")
        for player in town["players"]:
            await self.bot.botc_townsquare.restore_name(ctx, player)
            await player.remove_roles(player_role)
        for storyteller in town["storytellers"]:
            await self.bot.botc_townsquare.restore_name(ctx, storyteller)
            await storyteller.remove_roles(storyteller_role)
        for traveler in town["travelers"]:
            await traveler.remove_roles(traveler_role)
        town.update(self.bot.botc_townsquare._empty_town())
        await acknowledge_command(ctx)


class BOTCTownSquarePlayers(BOTCTownSquareErrorMixin, commands.Cog, name="Players"):
    """Commands for Blood on the Clocktower voice/text players.

    During play, you can get a live sense of the state of the game by looking at the
    voice chat user list. Each player's state, including if they are dead, ghost votes
    they have, and whether they are traveling, is represented by emojis in their
    nickname.

    When you learn that your state has changed (dead / alive / used ghost vote), use
    the appropriate command (`dead` / `alive` / `voted`) in the text chat, and the
    bot will give you the appropriate emojis.

    Anyone can use `townsquare` or `ts` and the bot will respond with a summary of the
    state of the town. If you just want to know the default character-type count for
    the game, use `count`.

    To make a nomination yourself, use the `nominate` command (`nom` or `n` for short)
    followed by the seat number of the player you'd like to nominate, e.g.
    `.nominate 1`. When the vote is counted, the storyteller or a helper will record
    the number of votes as a reaction to the nomination message by using the
    `nominate votes` sub-command followed by a number.

    The `public` command is a general tool for making statements that you want to be
    more noticeable (e.g. Juggler or Gossip abilities). Whatever text you include in
    the command, as in `.public <text>`, will be repeated and attributed to you using
    the bot's megaphone.

    """

    def __init__(self, bot):
        """Initialize cog for town square player commands."""
        self.bot = bot

    async def cog_check(self, ctx):
        """Check that setup commands are called from a guild and a town category."""
        result = await commands.guild_only().predicate(
            ctx
        ) and await is_called_from_botc_category().predicate(ctx)
        return result

    @commands.command(brief="Set player to 'dead'", usage="[<seat>|<name>]")
    @delete_command_message()
    async def dead(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Set the caller or user as dead, changing their name appropriately.

        Indicate another player if necessary using either their seat number or their
        *exact* name/tag.

        """
        member = await self.bot.botc_townsquare.resolve_player_arg(ctx, member)
        await self.bot.botc_townsquare.set_player_info(
            ctx, member, dead=True, num_votes=1
        )

    @commands.command(brief="Set player to 'voted'", usage="[<seat>|<name>]")
    @delete_command_message()
    async def voted(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Set the caller or user as dead with a used ghost vote.

        Indicate another player if necessary using either their seat number or their
        *exact* name/tag.

        """
        member = await self.bot.botc_townsquare.resolve_player_arg(ctx, member)
        await self.bot.botc_townsquare.set_player_info(
            ctx, member, dead=True, num_votes=0
        )

    @commands.command(brief="Set player to 'alive'", usage="[<seat>|<name>]")
    @delete_command_message()
    async def alive(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Set the caller or user as alive, changing their name appropriately.

        Indicate another player if necessary using either their seat number or their
        *exact* name/tag.

        """
        member = await self.bot.botc_townsquare.resolve_player_arg(ctx, member)
        await self.bot.botc_townsquare.set_player_info(
            ctx, member, dead=False, num_votes=None
        )

    @commands.command(name="townsquare", aliases=["ts"], brief="Show the town square")
    @require_locked_town()
    @delete_command_message()
    async def townsquare(self, ctx):
        """Show the current town square."""
        town = self.bot.botc_townsquare.get_town(ctx)
        lines = []
        alive_count = 0
        for idx, player in enumerate(town["player_order"]):
            num = idx + 1
            digits = "".join(EMOJI_DIGITS[d] for d in f"{num}")
            fill = self.bot.botc_townsquare.player_nickname_components(ctx, player)
            s = "{digits}{dead}{votes}{traveling} {nick}".format(digits=digits, **fill)
            lines.append(s)
            if not town["player_info"][player]["dead"]:
                alive_count += 1
        min_ex = int(math.ceil(alive_count / 2))
        non_traveler_count = len(town["players"]) - len(town["travelers"])
        try:
            count_dict = BOTC_COUNT[non_traveler_count]
        except KeyError:
            pass
        else:
            lines.append("{town}/{out}/{minion}/{demon}".format(**count_dict))
        lines.append(f"**{alive_count}** players alive.")
        lines.append(f"**{min_ex}** votes to execute.")

        embed = discord.Embed(
            description="\n".join(lines), color=discord.Color.dark_magenta()
        )
        await ctx.send(content=None, embed=embed)

    @commands.command(brief="Print the count of character types")
    @require_locked_town()
    @delete_command_message()
    async def count(self, ctx):
        """Print the count of each character type in this game."""
        town = self.bot.botc_townsquare.get_town(ctx)
        non_traveler_count = len(town["players"]) - len(town["travelers"])
        try:
            count_dict = BOTC_COUNT[non_traveler_count]
        except KeyError:
            await ctx.send(
                "You don't have the players for a proper game.",
                delete_after=BOTC_MESSAGE_DELETE_DELAY,
            )
        else:
            countstr = (
                "{town} townsfolk, {out} outsider(s), {minion} minion(s),"
                " and {demon} demon"
            ).format(**count_dict)
            await ctx.send(countstr)

    @commands.group(
        invoke_without_command=True,
        aliases=["nom", "n"],
        brief="Nominate a player for execution",
        usage="( <target-player> | <nominator> <target-player> )",
    )
    @require_locked_town()
    @delete_command_message()
    async def nominate(
        self, ctx, members: commands.Greedy[typing.Union[int, discord.Member]]
    ):
        """Nominate a player for execution, or set both nominator and target.

        Indicate a player using either their seat number or their *exact* name/tag.
        With one argument, the user of the command will be taken as the nominator.

        """
        town = self.bot.botc_townsquare.get_town(ctx)
        if len(members) == 0:
            raise commands.UserInputError("Could not parse any members to nominate")
        if town["nomination"] is not None:
            msg = (
                f"A nomination is already in progress."
                f" [`{ctx.prefix}nominate votes <#>`]"
            )
            return await ctx.send(msg, delete_after=BOTC_MESSAGE_DELETE_DELAY)
        if len(members) > 2:
            raise commands.TooManyArguments(
                "Nominate only accepts 1 or 2 player arguments."
            )
        if len(members) == 1:
            nominator = ctx.message.author
            target = await self.bot.botc_townsquare.resolve_player_arg(ctx, members[0])
        else:
            nominator = await self.bot.botc_townsquare.resolve_player_arg(
                ctx, members[0]
            )
            target = await self.bot.botc_townsquare.resolve_player_arg(ctx, members[1])

        if target not in town["travelers"]:
            nom_type = "execution"
            nom_color = discord.Color.green()
        else:
            nom_type = "exile"
            nom_color = discord.Color.gold()

        nominator_nick = discord.utils.escape_markdown(
            self.bot.botc_townsquare.match_name_re(
                ctx.message.channel.category, nominator
            )["nick"]
        )
        target_nick = discord.utils.escape_markdown(
            self.bot.botc_townsquare.match_name_re(
                ctx.message.channel.category, target
            )["nick"]
        )
        nom_type = "execution" if target not in town["travelers"] else "exile"
        nom_str = f"**{nominator_nick}** nominates **{target_nick}** for {nom_type}."
        nom_content = nom_str + "\n||\n||"

        embed = discord.Embed(color=nom_color, description=nom_str)
        embed.set_author(name=nominator_nick, icon_url=nominator.avatar_url)
        embed.set_thumbnail(url=target.avatar_url)

        nomination = await ctx.send(content=nom_content, embed=embed)
        town["nomination"] = nomination

    @nominate.command(
        name="votes",
        aliases=["vote"],
        brief="React to nomination with # of votes",
        usage="<num-votes>",
    )
    @require_locked_town()
    @delete_command_message()
    async def nominate_votes(self, ctx, num_votes: int):
        """React to the current/previous nomination with the given number of votes."""
        if num_votes < 0 or num_votes > 20:
            raise commands.BadArgument("Number of votes must be in [0, 20].")
        town = self.bot.botc_townsquare.get_town(ctx)
        if town["nomination"] is not None:
            nom = town["nomination"]
        elif town["prev_nomination"] is not None:
            nom = town["prev_nomination"]
        else:
            return await ctx.send(
                "There has not been a nomination to vote on.",
                delete_after=BOTC_MESSAGE_DELETE_DELAY,
            )
        await nom.clear_reactions()
        digits = []
        tens = num_votes // 10
        ones = num_votes % 10
        if tens == 1:
            digits.append(EMOJI_DIGITS["10"])
        elif tens == 2:
            digits.append(EMOJI_DIGITS["*"])
        if not (ones == 0 and tens > 0):
            digits.append(EMOJI_DIGITS[f"{ones}"])
        for d in digits:
            await nom.add_reaction(d)
        # now that the nomination has a number of votes set, it should be moved to prev
        town["prev_nomination"] = nom
        town["nomination"] = None

    @nominate.command(
        name="cancel", aliases=["delete", "del"], brief="Cancel the nomination"
    )
    @require_locked_town()
    @delete_command_message()
    async def nominate_cancel(self, ctx):
        """Cancel/delete the current or previous nomination."""
        town = self.bot.botc_townsquare.get_town(ctx)
        if town["nomination"] is not None:
            await town["nomination"].delete()
            town["nomination"] = None
        elif town["prev_nomination"] is not None:
            await town["prev_nomination"].delete()
            town["prev_nomination"] = None
        else:
            await ctx.send(
                "There is no nomination to cancel.",
                delete_after=BOTC_MESSAGE_DELETE_DELAY,
            )

    @commands.command(
        name="public", aliases=["pub", "say"], brief="Make a public statement"
    )
    @require_locked_town()
    @delete_command_message()
    async def public(self, ctx, *, statement: str):
        """Make a public statement, highlighted for visibility."""
        if not statement:
            raise commands.UserInputError("Statement is empty")
        author = ctx.message.author
        author_nick = discord.utils.escape_markdown(
            self.bot.botc_townsquare.match_name_re(
                ctx.message.channel.category, author
            )["nick"]
        )
        embed = discord.Embed(description=statement, color=discord.Color.blue())
        embed.set_author(name=author_nick, icon_url=author.avatar_url)
        await ctx.send(content=None, embed=embed)


class BOTCTownSquareManage(
    BOTCTownSquareErrorMixin, commands.Cog, name="Manage Town Squares"
):
    """Commands for managing Blood on the Clocktower voice/text town square categories.

    """

    def __init__(self, bot):
        """Initialize cog for town square management commands."""
        self.bot = bot
        self.setting_keys = (
            "is_enabled",
            "dead_emoji",
            "vote_emoji",
            "novote_emoji",
            "traveling_emoji",
        )

    async def cog_check(self, ctx):
        """Check that commands come from a user with appropriate permissions."""
        # checking permissions will raise an exception if failed, so if extra checks
        # are desired make sure to catch that exception if necessary
        result = await commands.guild_only().predicate(
            ctx
        ) and await commands.has_permissions(manage_channels=True).predicate(ctx)
        return result

    @commands.group(brief="Manage a town square category")
    @delete_command_message()
    async def town(self, ctx):
        """Command group for managing a Blood on the Clocktower town square category."""
        if ctx.invoked_subcommand is None:
            # list the town settings
            lines = [
                (
                    f"Use sub-commands to manage a town square category."
                    f" [{ctx.prefix}help {ctx.command}]"
                )
            ]
            category = ctx.message.channel.category
            settings = self.bot.botc_townsquare_settings
            is_town = settings.get(category.id, "is_enabled", None)
            if is_town is not None:
                # settings exist for the town, print them
                lines += [f"Settings for {category.name}:"]
                lines += [
                    "`{key}`: {val}".format(
                        key=key, val=settings.get(category.id, key, None)
                    )
                    for key in self.setting_keys
                ]
            await ctx.send("\n".join(lines), delete_after=BOTC_MESSAGE_DELETE_DELAY)

    @town.command(brief="Enable town square commands", usage="[<category-name>]")
    async def enable(self, ctx, *, category: discord.CategoryChannel = None):
        """Enable town square commands in the current or specified category."""
        if category is None:
            category = ctx.message.channel.category
        self.bot.botc_townsquare_settings.set(category.id, "is_enabled", True)
        await acknowledge_command(ctx)

    @town.command(brief="Disable town square commands", usage="[<category-name>]")
    async def disable(self, ctx, *, category: discord.CategoryChannel = None):
        """Disable town square commands in the current or specified category."""
        if category is None:
            category = ctx.message.channel.category
        self.bot.botc_townsquare_settings.set(category.id, "is_enabled", False)
        await acknowledge_command(ctx)

    @town.command(brief="Set a town square property", usage="<key> <value>")
    async def set(self, ctx, key: str, *, value: str):
        """Set a town square property to the given value."""
        if not value:
            raise commands.UserInputError("Must pass a value to set")
        if key not in self.setting_keys:
            raise commands.UserInputError(
                f"Invalid setting key. Must be one of {self.setting_keys}."
            )
        category = ctx.message.channel.category
        try:
            val = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            val = value
        self.bot.botc_townsquare_settings.set(category.id, key, val)
        await acknowledge_command(ctx)

    @town.command(brief="Unset a town square property", usage="<key>")
    async def unset(self, ctx, key: str):
        """Unset a town square property, returning it to a default value."""
        if key not in self.setting_keys:
            raise commands.UserInputError(
                f"Invalid setting key. Must be one of {self.setting_keys}."
            )
        category = ctx.message.channel.category
        self.bot.botc_townsquare_settings.unset(category.id, key)
        await acknowledge_command(ctx)


def setup(bot):
    """Set up the Blood on the Clocktower extension."""
    # set up persistent botc town square category settings
    bot.botc_townsquare_settings = DiscordIDSettings(
        bot, "botc_townsquare", BOTC_CATEGORY_DEFAULT_SETTINGS
    )
    # set up town square object
    bot.botc_townsquare = BOTCTownSquare(bot)

    bot.add_cog(BOTCTownSquareSetup(bot))
    bot.add_cog(BOTCTownSquareStorytellers(bot))
    bot.add_cog(BOTCTownSquarePlayers(bot))
    bot.add_cog(BOTCTownSquareManage(bot))


def teardown(bot):
    """Tear down the Blood on the Clocktower extension."""
    # tear down persistent botc town square category settings
    bot.botc_townsquare_settings.teardown()
    # tear down town square object
    bot.botc_townsquare.teardown()
