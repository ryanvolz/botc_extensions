# botc_extensions
Collection of Discord bot extensions for playing Blood on the Clocktower.

These extensions depend on the utilities found in https://github.com/ryanvolz/discord_bot_utils/, which must be placed at a relative path of `../utils` to this repository folder. For example:
```
bot/
bot/lib/__init__.py
bot/lib/botc_extensions
bot/lib/utils
```

## townsquare
The purpose of this extension is to use the features of Discord itself to represent a town square to facilitate voice/text games. This means using nicknames and roles to order players and track the state of the game. It also means providing commands to make actions in the game (e.g. nominations and public statements) more visible. As of now, this extension is not intended to implement Blood on the Clocktower and its game logic; rather, it gives players and storytellers tools to make voice/text games run a little smoother.

These instructions assume that the bot is using a command prefix of `.`, i.e. `.command`.

### Extension Setup
First, you must have the "Manage Channels" permission in order to do the setup outlined in this section. The extension works by providing town square functionality in the form of commands, but those commands will only work within categories for which they have explicitly been enabled.

If you're starting fresh, use `.town create` followed by a name for the new category, e.g. `.town create Ravenswood Bluff`. This will create a category and populate it with the desired text and voice channels (town square and sidebars) for running games. If you have an existing category that you want to enable the commands in, use `.town enable` from a text channel within the category.

Additionally, town categories can be customized by setting various properties, including the emojis used to track player state and the Discord roles assigned to players/travelers/storytellers in an active game. These properties can be viewed by typing `.town`. Emojis will already be set by default, but the town Discord roles are empty by default. To create new roles particular to the town, use `.town setrole <type>` with one of the role types, either `player`, `traveler`, or `storyteller`. It's also possible to create these roles manually and assign them to the town with `.town setrole <type> <role>`.

See `.help town` for a complete list of town category management commands.

### Game Setup
If you want to play in the next game, type `.play` command in the game's text chat. This will modify your nickname to include a seat number. If you want to be a traveler in the game, use `.travel` instead.

Even though the seating is virtual, you might want to 'sit' next to someone else or have a particular number. You can use the `sit` command followed by a seat number, like `.sit 4`, to move yourself to a particular seat. The current occupant and everyone in-between will shift toward your old seat. Anyone can also use `.shuffle` to assign seats randomly.

Once everyone is ready, the storyteller will freeze the players and seat assignments using the `.lock` command. Once the town is locked, in-game commands (below) become active.

### Playing
During play, you can get a live sense of the state of the game by looking at the voice chat user list. The storyteller(s) appears at the top, and players are listed next in seat order. Each player's state, including if they are dead, ghost votes they have, and whether they are traveling, is represented by emojis in their nickname.

When you learn that you have died, type `.dead` in the text chat, and the bot will give you the appropriate emojis. If you use your dead vote, type `.voted` so that your emojis indicate that. (If you type one of these commands in error, just use the appropriate one, also including `.alive`, to return to your actual state.)

Sometimes it can be useful to get a summary of the town square in the text chat. Anyone can use `.townsquare` or `.ts` and the bot will respond with the summary. If you just want to know the default character-type count for the game, use `.count`.

Nominations are handled with the `.nominate` command (`.nom` or `.n` for short). To use it to make a nomination yourself, type the command and then the seat number of the player you'd like to nominate, e.g. `.nominate 1`. This puts a noticeable message in the chat that we can refer back to later with the number of votes received. If someone is being slow, you can also do the command for them by including the seat number of the nominator first, e.g. `.nominate 2 1`. When the vote is counted, the storyteller or a helper will record the number of votes as a reaction to the nomination message by using the `.nominate votes <num>` command specifying the number of votes.

As a general tool, there is also the `.public` command for making statements that you want to be more noticeable. This is usually used for things that the storyteller needs to see and act on, like the Juggler or Gossip abilities. Whatever text you include in the command, as in `.public <text>`, will be repeated and attributed to you using the bot's megaphone.
