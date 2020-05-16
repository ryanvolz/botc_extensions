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
"""Components for Blood on the Clocktower voice/text players cog."""

import functools
import math
import typing

import discord
from discord.ext import commands

from . import common
from ...utils.commands import delete_command_message

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


def require_locked_town():
    """Return command decorator that raises an error if the town is lunocked."""

    def decorator(command):
        @functools.wraps(command)
        async def wrapper(self, ctx, *args, **kwargs):
            town = self.bot.botc_townsquare.get_town(ctx.message.channel.category)
            if not town["locked"]:
                raise common.BOTCTownSquareErrors.TownUnlocked(
                    "Command requires a locked town."
                )
            return await command(self, ctx, *args, **kwargs)

        return wrapper

    return decorator


class BOTCTownSquarePlayers(
    common.BOTCTownSquareErrorMixin, commands.Cog, name="Players"
):
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
        ) and await common.is_called_from_botc_category().predicate(ctx)
        return result

    @commands.command(brief="Set player to 'dead'", usage="[<seat>|<name>]")
    @delete_command_message()
    async def dead(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Set the caller or user as dead, changing their name appropriately.

        Indicate another player if necessary using either their seat number or their
        *exact* name/tag.

        """
        ts = self.bot.botc_townsquare
        member = await ts.resolve_player_arg(ctx, member)
        await ts.set_player_info(ctx, member, dead=True, num_votes=1)

    @commands.command(brief="Set player to 'voted'", usage="[<seat>|<name>]")
    @delete_command_message()
    async def voted(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Set the caller or user as dead with a used ghost vote.

        Indicate another player if necessary using either their seat number or their
        *exact* name/tag.

        """
        ts = self.bot.botc_townsquare
        member = await ts.resolve_player_arg(ctx, member)
        await ts.set_player_info(ctx, member, dead=True, num_votes=0)

    @commands.command(brief="Set player to 'alive'", usage="[<seat>|<name>]")
    @delete_command_message()
    async def alive(self, ctx, *, member: typing.Union[int, discord.Member] = None):
        """Set the caller or user as alive, changing their name appropriately.

        Indicate another player if necessary using either their seat number or their
        *exact* name/tag.

        """
        ts = self.bot.botc_townsquare
        member = await ts.resolve_player_arg(ctx, member)
        await ts.set_player_info(ctx, member, dead=False, num_votes=None)

    @commands.command(name="townsquare", aliases=["ts"], brief="Show the town square")
    @require_locked_town()
    @delete_command_message()
    async def townsquare(self, ctx):
        """Show the current town square."""
        town = self.bot.botc_townsquare.get_town(ctx.message.channel.category)
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
        town = self.bot.botc_townsquare.get_town(ctx.message.channel.category)
        non_traveler_count = len(town["players"]) - len(town["travelers"])
        try:
            count_dict = BOTC_COUNT[non_traveler_count]
        except KeyError:
            await ctx.send(
                "You don't have the players for a proper game.",
                delete_after=common.BOTC_MESSAGE_DELETE_DELAY,
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
        ts = self.bot.botc_townsquare
        category = ctx.message.channel.category
        town = ts.get_town(category)
        if len(members) == 0:
            raise commands.UserInputError("Could not parse any members to nominate")
        if town["nomination"] is not None:
            msg = (
                f"A nomination is already in progress."
                f" [`{ctx.prefix}nominate votes <#>`]"
            )
            return await ctx.send(msg, delete_after=common.BOTC_MESSAGE_DELETE_DELAY)
        if len(members) > 2:
            raise commands.TooManyArguments(
                "Nominate only accepts 1 or 2 player arguments."
            )
        if len(members) == 1:
            nominator = ctx.message.author
            target = await ts.resolve_player_arg(ctx, members[0])
        else:
            nominator = await ts.resolve_player_arg(ctx, members[0])
            target = await ts.resolve_player_arg(ctx, members[1])

        if target not in town["travelers"]:
            nom_type = "execution"
            nom_color = discord.Color.green()
        else:
            nom_type = "exile"
            nom_color = discord.Color.gold()

        nominator_nick = discord.utils.escape_markdown(
            ts.match_name_re(category, nominator)["nick"]
        )
        target_nick = discord.utils.escape_markdown(
            ts.match_name_re(category, target)["nick"]
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
        town = self.bot.botc_townsquare.get_town(ctx.message.channel.category)
        if town["nomination"] is not None:
            nom = town["nomination"]
        elif town["prev_nomination"] is not None:
            nom = town["prev_nomination"]
        else:
            return await ctx.send(
                "There has not been a nomination to vote on.",
                delete_after=common.BOTC_MESSAGE_DELETE_DELAY,
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
        town = self.bot.botc_townsquare.get_town(ctx.message.channel.category)
        if town["nomination"] is not None:
            await town["nomination"].delete()
            town["nomination"] = None
        elif town["prev_nomination"] is not None:
            await town["prev_nomination"].delete()
            town["prev_nomination"] = None
        else:
            await ctx.send(
                "There is no nomination to cancel.",
                delete_after=common.BOTC_MESSAGE_DELETE_DELAY,
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

    @commands.command(brief="Go to a voice channel", usage="[sidebar-num|name]")
    @delete_command_message(delay=0)
    async def go(self, ctx, *, vchan: typing.Union[int, discord.VoiceChannel] = None):
        """Go to a specified voice channel/sidebar in the current town category.

        Specify a number to go to the voice channel at that position (starting from 0)
        in the category list, or pass the tag/name for the voice channel. If no
        argument is specified, move to the top voice channel (e.g. Town Square).

        If the Town Square is the top voice channel and the sidebar voice channels are
        numbered after that, the sidebar number can be used as the argument.

        """
        voice_channels = ctx.message.channel.category.voice_channels
        if vchan is None:
            try:
                vchan = voice_channels[0]
            except IndexError:
                raise common.BOTCTownSquareErrors.BadSidebarArgument(
                    "No voice channels exist in the category"
                )
        elif isinstance(vchan, discord.VoiceChannel):
            # otherwise vchan is either a discord.VoiceChannel...
            pass
        else:
            # or an int, representing a voice channel (sidebar) number in the category
            try:
                # assume town square is the 0th voice channel, so sidebar numbers can
                # be indexed directly without modification
                vchan = voice_channels[vchan]
            except IndexError:
                raise common.BOTCTownSquareErrors.BadSidebarArgument(
                    "Voice channel number is invalid"
                )
        # move author to the requested voice channel
        try:
            await ctx.message.author.move_to(vchan)
        except discord.HTTPException:
            await ctx.send(
                "Bring yourself back online first. [connect to voice]",
                delete_after=common.BOTC_MESSAGE_DELETE_DELAY,
            )
