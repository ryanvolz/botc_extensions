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
"""Components for Blood on the Clocktower voice/text town management cog."""

import ast
import typing

import discord
from discord.ext import commands

from . import common
from ...utils.commands import acknowledge_command, delete_command_message, Flag


class BOTCTownSquareManage(
    common.BOTCTownSquareErrorMixin, commands.Cog, name="Manage Towns"
):
    """Commands for managing Blood on the Clocktower voice/text town categories.

    These management commands are only available to a user with the "Manage Channels"
    permission.

    See the help for the `town` command for more information.

    """

    def __init__(self, bot):
        """Initialize cog for town management commands."""
        self.bot = bot
        self.roles = dict(
            player=dict(prefix="Playing", color=discord.Color.green()),
            traveler=dict(prefix="Traveling", color=discord.Color.gold()),
            storyteller=dict(prefix="Storytelling", color=discord.Color.magenta()),
        )
        self.emoji_keys = ("dead", "vote", "novote", "traveling")

        self.setting_keys = tuple(
            ["is_enabled"]
            + [f"role.{key}" for key in self.roles.keys()]
            + [f"emoji.{key}" for key in self.emoji_keys]
        )

    async def cog_check(self, ctx):
        """Check that commands come from a user with appropriate permissions."""
        # checking permissions will raise an exception if failed, so if extra checks
        # are desired make sure to catch that exception if necessary
        result = await commands.guild_only().predicate(
            ctx
        ) and await commands.has_permissions(manage_channels=True).predicate(ctx)
        return result

    @commands.group(brief="Manage a town category")
    @delete_command_message()
    async def town(self, ctx):
        """Command group for managing a Blood on the Clocktower town category.

        Use `town` without a sub-command to get a list of the town category properties.

        If you're starting fresh, use the `town create` command followed by a name for
        the new category, e.g. `.town create Ravenswood Bluff`. This will create a
        category and populate it with the desired text and voice channels (town square
        and sidebars) for running games. If you have an existing category that you want
        to enable the commands in, use the `town enable` command from a text channel
        within the category.

        Additionally, town categories can be customized by setting various properties,
        including the emojis used to track player state and the Discord roles assigned
        to players/travelers/storytellers in an active game. These properties can be
        viewed by using the `town` command. Emojis will already be set by default, but
        the town Discord roles are empty by default. To create new roles particular to
        the town, use `.town setrole <type>` with one of the role types, either
        `player`, `traveler`, or `storyteller`. It's also possible to create these
        roles manually and assign them to the town with `.town setrole <type> <role>`.

        """
        if ctx.invoked_subcommand is None:
            # list the town settings
            lines = [
                (
                    f"Use sub-commands to manage a town category."
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
            await ctx.send(
                "\n".join(lines), delete_after=common.BOTC_MESSAGE_DELETE_DELAY
            )

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

    @town.command(
        brief="Create a town square category", usage="[private] <category-name>"
    )
    async def create(self, ctx, flags: commands.Greedy[Flag("private")], *, name: str):
        """Create and populate a town square category with the given name.

        Use "private" immediately after the command and before the category name to
        create a category that is not viewable by default.

        """
        if "private" in flags:
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(
                    read_messages=False, connect=False
                ),
                ctx.guild.me: discord.PermissionOverwrite(
                    read_messages=True, connect=True
                ),
            }
        else:
            overwrites = {}
        reason = "By user request through BOTC townsquare extension"
        category = await ctx.guild.create_category(
            name=name, overwrites=overwrites, reason=reason
        )
        # text chat channel
        await ctx.guild.create_text_channel(
            name=name.replace(" ", "-").lower(), category=category, reason=reason
        )
        # voice town square and sidebars
        await ctx.guild.create_voice_channel(
            name="Town Square", category=category, reason=reason
        )
        # voice sidebars
        for n in range(1, 8):
            await ctx.guild.create_voice_channel(
                name=f"Sidebar {n}", category=category, reason=reason
            )
        # storyteller sidebar
        await ctx.guild.create_voice_channel(
            name="Storyteller Sidebar", category=category, reason=reason
        )
        # enable the category for townsquare commands
        self.bot.botc_townsquare_settings.set(category.id, "is_enabled", True)
        await acknowledge_command(ctx)

    @town.command(brief="Set an emoji property", usage="<emoji-key> <emoji>")
    async def setemoji(self, ctx, key: str, *, emoji: typing.Union[discord.Emoji, str]):
        """Set a town square emoji property to the given emoji."""
        if key not in self.emoji_keys:
            raise commands.UserInputError(
                f"Invalid emoji setting key. Must be one of {self.emoji_keys}."
            )
        if isinstance(emoji, discord.Emoji):
            raise commands.UserInputError(
                "Cannot use custom Discord emojis in nickname."
            )
        category = ctx.message.channel.category
        self.bot.botc_townsquare_settings.set(category.id, f"emoji.{key}", str(emoji))
        await acknowledge_command(ctx)

    @town.command(brief="Unset an emoji property", usage="<emoji-key>")
    async def unsetemoji(self, ctx, key: str):
        """Unset a town square emoji property, returning it to a default value."""
        if key not in self.emoji_keys:
            raise commands.UserInputError(
                f"Invalid emoji setting key. Must be one of {self.emoji_keys}."
            )
        category = ctx.message.channel.category
        self.bot.botc_townsquare_settings.unset(category.id, f"emoji.{key}")
        await acknowledge_command(ctx)

    @town.command(brief="Set/create a role property", usage="<role-key> <role>")
    async def setrole(self, ctx, key: str, *, role: discord.Role = None):
        """Set a town square role property as given, or create a new role and set it."""
        if key not in self.roles:
            raise commands.UserInputError(
                f"Invalid role setting key. Must be one of {self.roles.keys()}."
            )
        category = ctx.message.channel.category
        if role is None:
            # create a new role for the category
            role_dict = self.roles[key]
            name = f"{role_dict['prefix']} {category.name}"
            try:
                role = await ctx.guild.create_role(
                    name=name,
                    color=role_dict["color"],
                    hoist=False,
                    mentionable=True,
                    reason="By user request through BOTC townsquare extension",
                )
            except Exception:
                # couldn't create role, see if it already exists
                role = discord.utils.get(ctx.guild.roles, name=name)
                if role is None:
                    raise
        self.bot.botc_townsquare_settings.set(category.id, f"role.{key}", role.id)
        await acknowledge_command(ctx)

    @town.command(brief="Unset a role property", usage="<role-key>")
    async def unsetrole(self, ctx, key: str):
        """Unset a town square role property, returning it to a default value."""
        if key not in self.roles:
            raise commands.UserInputError(
                f"Invalid role setting key. Must be one of {self.roles.keys()}."
            )
        category = ctx.message.channel.category
        self.bot.botc_townsquare_settings.unset(category.id, f"role.{key}")
        await acknowledge_command(ctx)

    @town.command(brief="Set a town square property", usage="<key> <value>")
    async def set(self, ctx, key: str, *, value: str):
        """Set a town square property to the given value.

        This is a low-level command. Be careful what values you pass, because it can
        easily break!

        """
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
