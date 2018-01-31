# Red Star Bot
![PyPI](https://img.shields.io/badge/Python-3.6-blue.svg)

A general-purpose Discord bot with administration and entertainment functions. Now with added **shouting.**

# Features
- Event logging, including message edits, deletions, and pins, user joins/leaves, and more
- Role administration by commands
- Message of the Day with configurable holidays and messages based on day, weekday, or month
- Bios for RP servers
- Levelling system with configurable XP by post length
- New member announcer
- Music playing
- Custom commands
- Dumping messages from channels into a text file
- Message purging by content (regex supported) and author

# Installation
- Install [Python 3.6+](https://www.python.org/)
- Install [discord.py](https://github.com/Rapptz/discord.py), rewrite branch
- For music playing:
  - Install discord.py\[voice]
  - Install [ffmpeg](http://ffmpeg.zeranoe.com/builds/) and add it to your PATH
  - Install [PyNaCl](https://github.com/pyca/pynacl)
  - Install [youtube-dl](https://github.com/rg3/youtube-dl)
- For MotD:
  - Install [schedule](https://github.com/dbader/schedule)
- Clone the `Red_Star` repository to your computer.
- [Configure](https://github.com/medeor413/Red_Star/wiki/Configuring-Red-Star) the bot.
- [Add the bot to your server.](https://github.com/medeor413/Red_Star/wiki/Adding-A-Bot)
- Run the bot by running the command `python red_star.py`.