# Miscellaneous utility functions and classes found here.
import argparse
import re
import json
from red_star.rs_errors import CommandSyntaxError
from random import randint


class JsonFileDict(dict):
    """
    Dictionary subclass that handles saving the file on edits automatically.
    Try not to instantiate this class directly; instead, use the config_manager's factory method,
    ConfigManager.get_plugin_config_file.
    :param pathlib.Path path: The path that should be saved to.
    """
    def __init__(self, path, json_save_args=None, json_load_args=None, **kwargs):
        super().__init__(**kwargs)
        self.path = path
        self.json_save_args = {} if json_save_args is None else json_save_args
        self.json_load_args = {} if json_load_args is None else json_load_args
        self.reload()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.save()

    def __delitem__(self, key):
        super().__delitem__(key)
        self.save()

    def save(self):
        with self.path.open("w", encoding="utf-8") as fd:
            json.dump(self, fd, **self.json_save_args)

    def reload(self):
        with self.path.open(encoding="utf-8") as fd:
            self.update(json.load(fd, **self.json_load_args))


class RSNamespace(argparse.Namespace):
    def __getitem__(self, key):
        try:
            return self.__getattribute__(key)
        except AttributeError:
            raise KeyError

    def __setitem__(self, key, value):
        self.__setattr__(key, value)


class RSArgumentParser(argparse.ArgumentParser):

    def __init__(self, add_help=False, ignore_unrecognized_arguments=True, **kwargs):
        self.ignore_unrecognized_arguments = ignore_unrecognized_arguments
        super().__init__(self, add_help=add_help, **kwargs)

    def exit(self, status=0, message=None):
        raise CommandSyntaxError(message)

    def error(self, message):
        raise CommandSyntaxError(message)

    def parse_args(self, args=None, namespace=None):
        args, argv = self.parse_known_args(args, namespace)
        if argv and not self.ignore_unrecognized_arguments:
            self.error(f"Unrecognized arguments: {' '.join(argv)}")
        return args

    def parse_known_args(self, args=None, namespace=None):
        if namespace is None:
            namespace = RSNamespace()
        return super().parse_known_args(args=args, namespace=namespace)


def get_guild_config(cls, gid, key):
    """
    Gets guild-specific configuration for an option, or fills it in with the default if unspecified.
    :param BasePlugin cls: The class calling the function, so it can access plugin-specific configs.
    :param str gid: The guild ID of the guild you're working with, as a str.
    :param str key: The config option you're trying to fetch.
    :return: The config option asked for.
    """
    if gid not in cls.plugin_config:
        cls.plugin_config[gid] = cls.plugin_config["default"].copy()
        cls.config_manager.save_config()
    elif key not in cls.plugin_config[gid]:
        cls.plugin_config[gid][key] = cls.plugin_config["default"][key]
        cls.config_manager.save_config()
    return cls.plugin_config[gid][key]


def sub_user_data(user, text):
    """
    Replaces certain tags in data with user info.
    :param user: The User object to get data from.
    :param text: The text string to substitute on.
    :return str: The substituted text.
    """
    rep = {
        "<username>": user.name,
        "<usernick>": user.display_name,
        "<userid>": user.id,
        "<userdiscrim>": user.discriminator,
        "<usermention>": user.mention
    }
    rep = {re.escape(k): v for k, v in rep.items()}
    pattern = re.compile("|".join(rep.keys()))
    text = pattern.sub(lambda m: rep[re.escape(m.group(0))], text)
    return text


def find_user(guild, search, return_all=False):
    """
    Convenience function to find users via several checks.
    :param guild: The discord.Guild object in which to search.
    :param search: The search string.
    :param return_all: Whether to return all users that match the criteria or just the first one.
    :return: discord.Member: The Member that matches the criteria, or none.
    """
    funcs = (lambda x: str(x.id) == search, lambda x: x.mention == search, lambda x: str(x).lower() == search.lower(),
             lambda x: x.display_name.lower() == search.lower(), lambda x: x.name.lower() == search.lower())
    final = []
    for func in funcs:
        found = tuple(filter(func, guild.members))
        if found:
            if return_all:
                final += found
            else:
                return found[0]
    if return_all:
        return final


def find_role(guild, search, return_all=False):
    """
    Convenience function to find users via several checks.
    :param guild: The discord.Guild object in which to search.
    :param search: The search string.
    :param return_all: Whether to return all roles that match the criteria or just the first one.
    :return: discord.Role: The Role that matches the criteria, or none.
    """
    funcs = (lambda x: str(x.id) == search, lambda x: x.mention == search,
             lambda x: str(x).lower() == search.lower())
    final = []
    for func in funcs:
        found = tuple(filter(func, guild.roles))
        if found:
            if return_all:
                final += found
            else:
                return found[0]
    if return_all:
        return final


async def respond(msg, response=None, allow_mention_everyone=False, **kwargs):
    """
    Convenience function to respond to a given message. Replaces certain
    patterns with data from the message.
    :param msg: The message to respond to.
    :param response: The text to respond with.
    :param allow_mention_everyone: If True, disables the automatic @everyone and @here filtering. Defaults to False.
    :return discord.Message: The Message sent.
    """
    text = None
    if response:
        text = sub_user_data(msg.author, response)
        if not allow_mention_everyone:  # Filter these out just in case we miss it somehow
            text = text.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
        if len(text) > 2000:
            # should've split it first
            # this is just a last-ditch error check
            text = text[:2000]
    elif not kwargs:
        # It's empty, raise an error.
        raise SyntaxError
    m = await msg.channel.send(text, **kwargs)
    return m


def split_message(message_str, splitter=None, max_len=2000):
    """
    Split message into 2000-character blocks, optionally on specific character.
    :param message_str: The message to split
    :param splitter: Optional, the string to split on. Default None.
    :param max_len: The maximum length of the message blocks. Default 2000.
    """
    msgs = []
    searchpoint = 0
    if splitter:
        while len(message_str) - searchpoint > max_len:
            searchstr = message_str[searchpoint:searchpoint + max_len]
            point = searchstr.rfind(splitter)
            if point >= 0:
                point += 1
                msgs.append(message_str[searchpoint:searchpoint + point])
                searchpoint += point
            else:
                msgs.append(message_str[searchpoint:searchpoint + max_len])
                searchpoint += max_len
        msgs.append(message_str[searchpoint:])
    else:
        for x in range(0, len(message_str), max_len):
            msgs.append(message_str[x:x + max_len])
    return msgs


async def split_output(message, title, items, *, header="```\n", footer="```", f=lambda x: str(x)+"\n"):
    """
    :type title: str
    :type header: str
    :type footer: str
    :param message: a discord.Message object to respond to
    :param title: a title string, appended before the list
    :param items: a list of items to iterate over
    :param header: a header string, put between title and items
    :param footer: a footer string, capping up the lists
    :param f: a function to run on the items. Must take one argument (the item) and return a string
    :return:
    """
    t_str = title + header
    t_l = len(footer)
    for i in items:
        t_s = f(i)
        if len(t_str+t_s) > 2000-t_l:
            await respond(message, t_str+footer)
            t_str = header+t_s
        else:
            t_str += t_s
    await respond(message, t_str+footer)


def ordinal(n):
    """
    Black magic that turns numbers into ordinal representation (1 -> 1st)
    :param n: number to be converted
    :return: string with ordinal number
    """
    return "%d%s" % (n, "tsnrhtdd"[((n//10) % 10 != 1)*(n % 10 < 4)*n % 10::4])


def decode_json(t_bytes):
    try:
        try:
            t_string = t_bytes.decode()
        except UnicodeDecodeError:
            try:
                t_string = t_bytes.decode(encoding="windows-1252")
            except UnicodeDecodeError:
                try:
                    t_string = t_bytes.decode(encoding="windows-1250")
                except UnicodeDecodeError:
                    raise ValueError("Unable to parse file encoding. Please use UTF-8")
        else:
            if t_string[0] != "{":
                t_string = t_bytes.decode(encoding="utf-8-sig")
        t_data = json.loads(t_string)
    except json.decoder.JSONDecodeError as e:
        raise ValueError(f"Not a valid JSON file: {e}")
    return t_data


def p_time(seconds):
    """
    Pretty time display function
    :param seconds: time in seconds
    :return: time in weeks, days and h:mm:ss
    """
    minute = 60
    hour = minute*60
    day = hour*24
    week = day*7

    t_w, t_d = divmod(int(seconds), week)
    t_d, t_h = divmod(t_d, day)
    t_h, t_m = divmod(t_h, hour)
    t_m, t_s = divmod(t_m, minute)

    t_string = []
    if t_w > 1:
        t_string.append(f"{t_w} weeks")
    elif t_w == 1:
        t_string.append("1 week")

    if t_d > 1:
        t_string.append(f"{t_d} days")
    elif t_d == 1:
        t_string.append("1 day")

    if t_h > 0:
        if t_m == t_s == 0:
            if t_h > 1:
                t_string.append(f"{t_h} hours")
            else:
                t_string.append("1 hour")
        else:
            t_string.append(f"{t_h}:{t_m:02d}:{t_s:02d}")
    elif t_m > 0:
        if t_s == 0:
            if t_m > 1:
                t_string.append(f"{t_m} minutes")
            else:
                t_string.append("1 minute")
        else:
            t_string.append(f"{t_m}:{t_s:02d}")
    elif t_s > 1:
        t_string.append(f"{t_s:02d} seconds")
    elif t_s == 1:
        t_string.append("1 second")

    return ", ".join(t_string)


def is_positive(string):
    """
    Returns True if the string is a positive word and False if the string is a negative word
    :type string: str
    :param string: string to be judged
    :return: boolean
    """
    if string.lower() in ["off", "disable", "no", "negative", "false"]:
        return False
    elif string.lower() in ["on", "enable", "yes", "affirmative", "true"]:
        return True
    else:
        raise CommandSyntaxError(f"{string} is not valid positive/negative input. "
                                 f"Allowed inputs: off/disable/no/negative/false, "
                                 "on/enable/yes/affirmatie/true.")


def parse_roll(dicestr, roll=None):
    dice_data = re.search(r"^(\d*)d(\d+|f)([ad]?)", dicestr)
    if dice_data:
        # checking for optional dice number
        if dice_data.group(1):
            num_dice = min(max(int(dice_data.group(1)), 1), 10000)
        else:
            num_dice = 1
        # support for fate dice. And probably some other kind of dice? Added roll_function to keep it streamlined
        if dice_data.group(2) != 'f':
            def roll_function(): return randint(1, min(max(int(dice_data.group(2)), 2), 10000))
        else:
            def roll_function(): return randint(1, 3) - 2
        t_adv = dice_data.group(3)
        dice_set_a = [roll_function() for _ in range(num_dice)]
        dice_set_b = [roll_function() for _ in range(num_dice)]
        if t_adv == "a":
            rolled_dice = dice_set_a if sum(dice_set_a) >= sum(dice_set_b) else dice_set_b
        elif t_adv == "d":
            rolled_dice = dice_set_a if sum(dice_set_a) < sum(dice_set_b) else dice_set_b
        else:
            rolled_dice = dice_set_a
        if roll is not None:
            roll.append(f"{dice_data.string:5} - {sum(rolled_dice):2d} {rolled_dice} ")
        return rolled_dice
    else:
        try:
            return int(dicestr)
        except ValueError:
            return dicestr


def parse_tokens(tokens, roll=None):
    """
    Function that runs over a list and processes tokens.
    Runs repeatedly to support nested :dn expressions like d6:d6:d6 and 1:d6+1
    No need to sanitize tokens inside here since the initial rollstring parse only grabs what fits the regexp.
    :param tokens:
    :param roll:
    :return:
    """
    t_tokens = [sum(t) if type(t) == list else t for t in tokens]

    # improved :dn support to allow repeated parsing (since the regex nature of :dn makes it hard to prioritize
    rerun = True
    while rerun:
        rerun = False
        for i in range(len(t_tokens))[::-1]:
            try:
                if t_tokens[i] == '*':
                    t_tokens[i - 1:i + 2] = [t_tokens[i - 1] * t_tokens[i + 1]]
                elif t_tokens[i] == "/":
                    t_tokens[i - 1:i + 2] = [t_tokens[i - 1] / t_tokens[i + 1]]
                elif t_tokens[i] == "+":
                    t_tokens[i - 1:i + 2] = [t_tokens[i - 1] + t_tokens[i + 1]]
                elif t_tokens[i] == "-":
                    if type(t_tokens[i-1]) in [int, float]:  # it may just be denoting the number to be negative
                        t_tokens[i - 1:i + 2] = [t_tokens[i - 1] - t_tokens[i + 1]]
                    else:
                        t_tokens[i:i+2] = [-t_tokens[i+1]]
                elif type(t_tokens[i]) == str and re.match(':d[\df]+', t_tokens[i]):
                    if type(t_tokens[i-1]) == int:
                        t_tokens[i-1:i+1] = [sum(parse_roll(f"{t_tokens[i-1]}{t_tokens[i][1:]}", roll=roll))]
                    else:
                        rerun = True
            except IndexError:
                del t_tokens[i]
            except TypeError:
                rerun = True

    return t_tokens


def parse_roll_string(string):
    """
    Function to parse the roll notation string.
    Splits the string into tokens with initial conversion of dice into results, then iterates over it.
    To support brackets, the function finds all the opening brackets and evaluates the tokens until the closest
    closing bracket, starting from the furthest opening bracket down the line.
    :param string:
    :return:
    """
    args = re.sub(r"\)([\dd])", ")*\1", string)
    rolled_dice = []
    tokens = list(map(lambda x: parse_roll(x, roll=rolled_dice),
                      re.findall(r':d[\df]+|\d*d[\df]+[ad]?|[+\-*/()]|\d+', args)))
    brackets = [p for p, t in enumerate(tokens) if t == '('][::-1]
    for o_br in brackets:
        try:
            c_br = o_br + tokens[o_br:].index(')')
            if c_br-o_br == 1:
                del tokens[c_br]
                del tokens[o_br]
            else:
                r = parse_tokens(tokens[o_br+1:c_br], roll=rolled_dice)
                tokens[o_br:c_br+1] = [r[0]]

        except ValueError:
            tokens.pop(o_br)

    return parse_tokens(tokens, roll=rolled_dice), rolled_dice
