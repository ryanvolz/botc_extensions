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
"""Common components for Blood on the Clocktower town square extension."""

import collections
import re

import discord
from discord.ext import commands

BOTC_MESSAGE_DELETE_DELAY = 60


def is_called_from_botc_category():
    """Check if called from a BOTC town category."""

    async def predicate(ctx):
        if ctx.guild is None:
            # don't restrict match if command is in a DM
            return True
        else:
            cat_id = ctx.message.channel.category.id
            return ctx.bot.botc_townsquare_settings.get(cat_id, "is_enabled", False)

    return commands.check(predicate)


class BOTCTownSquareErrors(object):
    class BadPlayerArgument(commands.UserInputError):
        """Bad argument intended to resolve to a player."""

        def __init__(self, message, member, *args):
            self.member = member
            super().__init__(message, *args)

    class BadSeatArgument(commands.UserInputError):
        """Bad argument intended to resolve to a player seat number."""

        pass

    class BadSidebarArgument(commands.UserInputError):
        """Bad argument intended to resolve to a voice channel (sidebar) number."""

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
            await ctx.send(
                "That seat doesn't look like anything to me.",
                delete_after=BOTC_MESSAGE_DELETE_DELAY,
            )
        elif isinstance(error, BOTCTownSquareErrors.BadSidebarArgument):
            await ctx.send(
                "That sidebar doesn't look like anything to me.",
                delete_after=BOTC_MESSAGE_DELETE_DELAY,
            )
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
        self._towns = {}

    def teardown(self):
        """Save state for the town square."""
        pass

    def _get_role_settings(self, category):
        """Get dictionary of roles from the BOTC town square category settings."""
        role_vars = ["role.player", "role.traveler", "role.storyteller"]
        role_ids = {
            k[5:]: self.bot.botc_townsquare_settings.get(category.id, k)
            for k in role_vars
        }
        return role_ids

    def _get_emoji_settings(self, category):
        """Get dictionary of emojis from the BOTC town square category settings."""
        emoji_vars = ["emoji.dead", "emoji.novote", "emoji.vote", "emoji.traveling"]
        emojis = {
            k[6:]: self.bot.botc_townsquare_settings.get(category.id, k)
            for k in emoji_vars
        }
        return emojis

    def _format_name_re(self, emojis):
        """Format BOTC name regular expression using the emoji dictionary."""
        name_re_template = (
            r"^(?:(?P<seat>_\d+)|(?P<st>!ST))?"
            r"\s*"
            r"(?P<dead>{dead})?"
            r"(?P<votes>{novote}|{vote}+)?"
            r"(?P<traveling>{traveling})?"
            r"\s*"
            r"(?P<nick>.*)"
        )
        name_re = re.compile(name_re_template.format(**emojis))
        return name_re

    def get_town(self, category):
        """Return the town dictionary for the command's category."""
        try:
            town = self._towns[category.id]
        except KeyError:
            # load town square settings into this instance at time of creation
            role_ids = self._get_role_settings(category)
            emojis = self._get_emoji_settings(category)
            name_re = self._format_name_re(emojis)
            # create an empty town
            town = dict(
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
                role_ids=role_ids,
                emojis=emojis,
                name_re=name_re,
            )
            self._towns[category.id] = town
        return town

    def del_town(self, category):
        """Delete the town dictionary for the command's category."""
        try:
            del self._towns[category.id]
        except KeyError:
            pass

    def match_name_re(self, category, member):
        """Match a display name to the name regex, extracting player state and nick."""
        town = self.get_town(category)
        name_re = town["name_re"]
        return name_re.match(member.display_name)

    def player_nickname_components(self, ctx, member):
        """Get a players' nickname components based on their data in player_info."""
        category = ctx.message.channel.category
        town = self.get_town(category)
        info = town["player_info"][member]
        emojis = town["emojis"]
        fill = dict(seat="", dead="", votes="", traveling="")
        fill["nick"] = self.match_name_re(category, member)["nick"]
        # build the info-derived fill values for the nickname string
        if info["seat"] is not None:
            fill["seat"] = f"_{info['seat']:02d}"
        if info["dead"]:
            fill["dead"] = emojis["dead"]
        if info["num_votes"] is not None:
            if info["num_votes"] == 0:
                fill["votes"] = emojis["novote"]
            else:
                fill["votes"] = info["num_votes"] * emojis["vote"]
        if info["traveling"]:
            fill["traveling"] = emojis["traveling"]
        return fill

    async def set_player_nickname(self, ctx, member):
        """Set a players' nickname based on their data in player_info."""
        fill = self.player_nickname_components(ctx, member)
        nickname = "{seat}{dead}{votes}{traveling} {nick}".format(**fill)
        try:
            await member.edit(nick=nickname)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def set_player_info(self, ctx, member, **kwargs):
        """Set new values for player info and then adjust their nickname."""
        info = self.get_town(ctx.message.channel.category)["player_info"][member]
        info.update(kwargs)
        await self.set_player_nickname(ctx, member)

    async def set_storyteller_nickname(self, ctx, member):
        """Set a member's nickname to have storyteller markings."""
        nick = self.match_name_re(ctx.message.channel.category, member)["nick"]
        name = f"!ST {nick}"
        try:
            await member.edit(nick=name)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def restore_name(self, ctx, member):
        """Restore a member's nickname after playing."""
        nick = self.match_name_re(ctx.message.channel.category, member)["nick"]
        name = f"{nick}"
        try:
            await member.edit(nick=name)
        except (discord.Forbidden, discord.HTTPException):
            pass

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
            town = self.get_town(ctx.message.channel.category)
            try:
                member = town["player_order"][member - 1]
            except IndexError:
                if member == 0 and len(town["storytellers"]) == 1:
                    member = town["storytellers"][0]
                else:
                    raise BOTCTownSquareErrors.BadSeatArgument("Seat number is invalid")
        return member

    async def resolve_player_arg(self, ctx, member):
        """Resolve member argument intended to identify a player."""
        member = await self.resolve_member_arg(ctx, member)
        # now verify that the member is a player
        if member in self.get_town(ctx.message.channel.category)["players"]:
            return member
        else:
            raise BOTCTownSquareErrors.BadPlayerArgument(
                "Member isn't a player", member
            )
