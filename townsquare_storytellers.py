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
"""Components for Blood on the Clocktower voice/text storytellers cog."""

import discord
from discord.ext import commands

from . import townsquare_common
from ..utils.commands import acknowledge_command, delete_command_message


class BOTCTownSquareStorytellers(
    townsquare_common.BOTCTownSquareErrorMixin, commands.Cog, name="Storytellers"
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
        ) and await townsquare_common.is_called_from_botc_category().predicate(ctx)
        # checking permissions will raise an exception if failed, but we then want to
        # be able to check the role instead
        try:
            await commands.has_guild_permissions(administrator=True).predicate(ctx)
        except commands.MissingPermissions:
            pass
        else:
            return result
        town = self.bot.botc_townsquare.get_town(ctx.message.channel.category)
        role_id = town["role_ids"]["storyteller"]
        if role_id is not None:
            result = result and await commands.has_role(role_id).predicate(ctx)
        return result

    @commands.command(name="lock", brief="Lock the town")
    @delete_command_message()
    async def lock(self, ctx):
        """Start a game with the current players, locking the town and seat order."""
        town = self.bot.botc_townsquare.get_town(ctx.message.channel.category)
        town["locked"] = True
        await acknowledge_command(ctx)

    @commands.command(name="unlock", brief="Unlock the town")
    @delete_command_message()
    async def unlock(self, ctx):
        """Stop (pause) a game, unlocking the town and seat order."""
        town = self.bot.botc_townsquare.get_town(ctx.message.channel.category)
        town["locked"] = False
        await acknowledge_command(ctx)

    @commands.command(brief="End game and clear the town")
    @delete_command_message()
    async def clear(self, ctx):
        """Clear the current town, erasing game state and restoring names."""
        ts = self.bot.botc_townsquare
        category = ctx.message.channel.category
        town = ts.get_town(category)

        roles = {}
        for key, role_id in town["role_ids"].items():
            if role_id is not None:
                roles[key] = ctx.guild.get_role(role_id)
            else:
                roles[key] = role_id
        for player in town["players"]:
            await ts.restore_name(ctx, player)
            if roles["player"] is not None:
                try:
                    await player.remove_roles(roles["player"])
                except (discord.Forbidden, discord.HTTPException):
                    pass
        for storyteller in town["storytellers"]:
            await ts.restore_name(ctx, storyteller)
            if roles["storyteller"] is not None:
                try:
                    await storyteller.remove_roles(roles["storyteller"])
                except (discord.Forbidden, discord.HTTPException):
                    pass
        if roles["traveler"] is not None:
            for traveler in town["travelers"]:
                try:
                    await traveler.remove_roles(roles["traveler"])
                except (discord.Forbidden, discord.HTTPException):
                    pass
        ts.del_town(category)
        await acknowledge_command(ctx)
