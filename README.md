# Red Star Bot
![Python](https://img.shields.io/badge/Python-3.7-blue.svg) [![PyPI](https://img.shields.io/pypi/v/red-star.svg)](https://pypi.org/project/red-star/)

<img src="https://raw.githubusercontent.com/medeor413/Red_Star/master/default_avatar.png" width="150">

A configurable, extensible Discord bot with administration and entertainment plugins included. Now with added shouting.

# Features
- Flexible music playing with [youtube-dl](https://github.com/rg3/youtube-dl), including queues, playlist support, vote-skipping, and more,
- Powerful custom commands based on our own Lisp dialect, [RSLisp](https://github.com/medeor413/Red_Star/wiki/Custom-Commands),
- Event logging, including message edits, deletions, and pins, user joins/leaves, and more,
- Powerful message purging by content (regex supported), author, and more,
- Message of the Day plugins with configurable holidays and messages based on day, weekday, or month,
- Voting plugin for making, responding to, and counting the results of polls,
- Reminder plugin with times, delays, and recurring reminders,
- New member announcer with easily configurable messages,
- Easy role administration for mobile users via commands,
- And more, with extra plugins available [here](https://github.com/medeor413/Red_Star_Plugins).

# Installation
## With pip
Simply run `pip install red-star`, and Red Star and all its dependencies will be automatically installed.
You can then run Red Star by simply running `python -m red_star` or `red_star` (if Scripts is in your PATH).

## From source
### Installing
Running `pip install -e .` inside the Red Star folder will install Red Star and all its dependencies automatically.
This will allow you to run Red Star in the same way as above.
### Running portably
Alternatively, one can run Red Star portably by simply navigating to the source directory and running `python red_star.py -p`.
This will tell Red Star to keep its loose files inside the source directory, instead of placing them in your user folder.

# Usage
Starting the bot is already covered above; simply invoke `red_star`, `python -m red_star`, or `python red_star.py` to run the bot.
On first run, a default configuration file will be copied to `~/.red_star` (`C:\Users\username\.red_star` on Windows) that must be edited before use.
## Command-line Arguments
- `-[-p]ortable`: Tells the bot to run in portable mode, keeping all of its loose files in its source directory.
Useful if you don't want to clutter your user folder, or install the bot with `pip`.
- `-[-d]irectory`: Allows the user to specify a custom directory to place loose files. Cannot be used with `-p`.
- `-[-l]ogfile`: Allows the user to specify a different name for the log file than the default.
- `-[-v]erbose`: Tells the bot to output debug information while running. Can be called up to three times, increasing verbosity each time.
## Documentation
See [our wiki](https://github.com/medeor413/Red_Star/wiki) for additional documentation, including 
[Command Reference](https://github.com/medeor413/Red_Star/wiki/Command-Reference), [Configuring Red Star](https://github.com/medeor413/Red_Star/wiki/Configuring-Red-Star),
and [Adding A Bot to a Server](https://github.com/medeor413/Red_Star/wiki/Adding-A-Bot).