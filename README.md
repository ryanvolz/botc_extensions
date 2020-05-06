# botc_extensions
Collection of Discord bot extensions for playing Blood on the Clocktower.

## townsquare

### Setup
If you want to play in the next game, type `.play` in the game's text chat. This will modify your nickname to include a seat number. If you want to be a traveler in the game, type `.travel` instead.

Even though the seating is virtual, you might want to 'sit' next to someone else or have a particular number. You can use the `.sit` command followed by a seat number, like `.sit 4`, to move yourself to a particular seat. The current occupant and everyone in-between will shift toward your old seat. Anyone can also use the `.shuffle` command to assign seats randomly.

Once everyone is ready, the storyteller will freeze the players and seat assignments using the `.lock` command. Once the town is locked, in-game commands (below) become active.

### Playing
During play, you can get a live sense of the state of the game by looking at the voice chat user list. The storyteller(s) appears at the top, and players are listed next in seat order. Each player's state, including if they are dead, ghost votes they have, and whether they are traveling, is represented by emojis in their nickname.

When you learn that you have died, type `.dead` in the text chat, and the bot will give you the appropriate emojis. If you use your dead vote, type `.voted` so that your emojis indicate that. (If you type one of these commands in error, just use the appropriate one, including `.alive`, to return to your actual state.)

Sometimes it can be useful to get a summary of the town square in the text chat. Anyone can type `.townsquare` or `.ts` and the bot will respond with the summary. If you just want to know the default character-type count for the game, use `.count`.

Nominations are handled with the `.nominate` command (`.nom` or `.n` for short). To use it to make a nomination yourself, type the command and then the seat number of the player you'd like to nominate, e.g. `.nominate 1`. This puts a noticeable message in the chat that we can refer back to later with the number of votes received. If someone is being slow, you can also do the command for them by including the seat number of the nominator first, e.g. `.nominate 2 1`. When the vote is counted, the storyteller or a helper will record the number of votes as a reaction to the nomination message by using the `.nom votes <#>` command.

As a general tool, there is also the `.public` command for making statements that you want to be more noticeable. This is usually used for things that the storyteller needs to see and act on, like the Juggler or Gossip abilities. Whatever text you include in the command, as in `.public <text>`, will be repeated and attributed to you using the bot's megaphone.
