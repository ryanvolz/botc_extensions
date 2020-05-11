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
"""Components for Blood on the Clocktower voice/text game setup cog."""

import functools
import random
import typing

import discord
from discord.ext import commands

from . import townsquare_common
from ..utils.commands import delete_command_message


def require_unlocked_town():
    """Return command decorator that raises an error if the town is locked."""

    def decorator(command):
        @functools.wraps(command)
        async def wrapper(self, ctx, *args, **kwargs):
            town = self.bot.botc_townsquare.get_town(ctx.message.channel.category)
            if town["locked"]:
                raise townsquare_common.BOTCTownSquareErrors.TownLocked(
                    "Command requires an unlocked town."
                )
            return await command(self, ctx, *args, **kwargs)

        return wrapper

    return decorator


class BOTCTownSquareSetup(
    townsquare_common.BOTCTownSquareErrorMixin, commands.Cog, name="Setup"
):
    """Commands for Blood on the Clocktower voice/text town square game setup.

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
        ) and await townsquare_common.is_called_from_botc_category().predicate(ctx)
        return result

    @commands.command(brief="Add a player", usage="[<name>]")
    @require_unlocked_town()
    @delete_command_message()
    async def play(self, ctx, *, member: discord.Member = None):
        """Set the caller or given user as a player.

        Indicate another player if necessary using their *exact* name/tag.

        """
        ts = self.bot.botc_townsquare
        town = ts.get_town(ctx.message.channel.category)
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
        await ts.set_player_info(ctx, member, seat=number)
        role_id = town["role_ids"]["player"]
        if role_id is not None:
            role = ctx.guild.get_role(role_id)
            await member.add_roles(role)

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
        ts = self.bot.botc_townsquare
        town = ts.get_town(ctx.message.channel.category)
        member = await ts.resolve_member_arg(ctx, member)
        if member in town["travelers"]:
            await ctx.invoke(self.untravel, member=member)
        if member in town["players"]:
            town["players"].remove(member)
            town["player_order"].remove(member)
        await ts.restore_name(ctx, member)
        for idx, player in enumerate(town["player_order"]):
            if town["player_info"][player]["seat"] != idx + 1:
                await ts.set_player_info(ctx, player, seat=idx + 1)
        role_id = town["role_ids"]["player"]
        if role_id is not None:
            role = ctx.guild.get_role(role_id)
            await member.remove_roles(role)

    @commands.command(brief="Set player as a traveler", usage="[<seat>|<name>]")
    @require_unlocked_town()
    @delete_command_message()
    async def travel(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Set the caller or given user as a traveler.

        Indicate another player if necessary using either their seat number (if already
        a player) or their *exact* name/tag.

        """
        ts = self.bot.botc_townsquare
        town = ts.get_town(ctx.message.channel.category)
        member = await ts.resolve_member_arg(ctx, member)
        if member not in town["players"]:
            await ctx.invoke(self.play, member=member)
        town["travelers"].add(member)
        await ts.set_player_info(ctx, member, traveling=True)
        role_id = town["role_ids"]["traveler"]
        if role_id is not None:
            role = ctx.guild.get_role(role_id)
            await member.add_roles(role)

    @commands.command(brief="Unset player as a traveler", usage="[<seat>|<name>]")
    @require_unlocked_town()
    @delete_command_message()
    async def untravel(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Unset the caller or given user as a traveler.

        Indicate another player if necessary using either their seat number or their
        *exact* name/tag.

        """
        ts = self.bot.botc_townsquare
        town = ts.get_town(ctx.message.channel.category)
        member = await ts.resolve_player_arg(ctx, member)
        if member not in town["travelers"]:
            return
        town["travelers"].remove(member)
        await ts.set_player_info(ctx, member, traveling=False)
        role_id = town["role_ids"]["traveler"]
        if role_id is not None:
            role = ctx.guild.get_role(role_id)
            await member.remove_roles(role)

    @commands.command(
        name="storytell", aliases=["st"], brief="Add a storyteller", usage="[<name>]"
    )
    @require_unlocked_town()
    @delete_command_message()
    async def storytell(self, ctx, *, member: discord.Member = None):
        """Set the caller or given user as a storyteller.

        Indicate another player if necessary using their *exact* name/tag.

        """
        ts = self.bot.botc_townsquare
        town = ts.get_town(ctx.message.channel.category)
        if member is None:
            member = ctx.message.author
        if member in town["storytellers"]:
            return
        if member in town["players"]:
            await ctx.invoke(self.unplay, member=member)
        town["storytellers"].add(member)
        await ts.set_storyteller_nickname(ctx, member)
        role_id = town["role_ids"]["storyteller"]
        if role_id is not None:
            role = ctx.guild.get_role(role_id)
            await member.add_roles(role)

    @commands.command(
        name="unstorytell", aliases=["unst"], brief="Unset storyteller(s)"
    )
    @require_unlocked_town()
    @delete_command_message()
    async def unstorytell(self, ctx):
        """Unset the existing storyteller(s)."""
        ts = self.bot.botc_townsquare
        town = ts.get_town(ctx.message.channel.category)
        for storyteller in list(town["storytellers"]):
            town["storytellers"].remove(storyteller)
            await ts.restore_name(ctx, storyteller)
            role_id = town["role_ids"]["storyteller"]
            if role_id is not None:
                role = ctx.guild.get_role(role_id)
                await storyteller.remove_roles(role)

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
        ts = self.bot.botc_townsquare
        town = ts.get_town(ctx.message.channel.category)
        member = await ts.resolve_player_arg(ctx, member)
        order = town["player_order"]
        oldindex = order.index(member)
        newindex = seat - 1
        # puts member in the given seat while shifting the existing occupants
        # between the new seat and old toward the old seat
        order.insert(newindex, order.pop(oldindex))
        for idx, player in enumerate(order):
            if town["player_info"][player]["seat"] != idx + 1:
                await ts.set_player_info(ctx, player, seat=idx + 1)

    @commands.command(brief="Shuffle seat order")
    @require_unlocked_town()
    @delete_command_message()
    async def shuffle(self, ctx):
        """Shuffle the seat order of the current players."""
        ts = self.bot.botc_townsquare
        town = ts.get_town(ctx.message.channel.category)
        order = town["player_order"]
        random.shuffle(order)
        for idx, player in enumerate(order):
            if town["player_info"][player]["seat"] != idx + 1:
                await ts.set_player_info(ctx, player, seat=idx + 1)
