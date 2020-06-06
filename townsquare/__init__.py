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
"""Discord extension for facilitating Blood on the Clocktower voice/text games."""

from .common import BOTCTownSquare
from .manage import BOTCTownSquareManage
from .players import BOTCTownSquarePlayers
from .setup import BOTCTownSquareSetup
from .storytellers import BOTCTownSquareStorytellers
from ...utils.persistent_settings import DiscordIDSettings

BOTC_CATEGORY_DEFAULT_SETTINGS = {
    "emoji.dead": "💀",
    "emoji.vote": "👻",
    "emoji.novote": "🚫",
    "emoji.traveling": "🚁",
    "emoji.storytelling": "📕",
}


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
