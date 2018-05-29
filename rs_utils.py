# Miscellaneous utility functions and classes found here.
import collections
import dbm
import re
import shelve
import json
from io import BytesIO
from pickle import Pickler, Unpickler
from rs_errors import CommandSyntaxError


class DotDict(dict):
    """
    Custom dictionary format that allows member access by using dot notation:
    eg - dict.key.subkey
    """

    def __init__(self, d, **kwargs):
        super().__init__(**kwargs)
        for k, v in d.items():
            if isinstance(v, collections.Mapping):
                v = DotDict(v)
            self[k] = v

    def __getattr__(self, item):
        try:
            return super().__getitem__(item)
        except KeyError as e:
            raise AttributeError(str(e)) from None

    def __setattr__(self, key, value):
        if isinstance(value, collections.Mapping):
            value = DotDict(value)
        super().__setitem__(key, value)

    __delattr__ = dict.__delitem__


class Cupboard(shelve.Shelf):
    """
    Custom Shelf implementation that only pickles values at save-time.
    Increases save/load times, decreases get/set item times.
    More suitable for use as a savable dictionary.
    """
    def __init__(self, filename, flag='c', protocol=None, keyencoding='utf-8'):
        self.db = filename
        self.flag = flag
        self.dict = {}
        with dbm.open(self.db, self.flag) as db:
            for k in db.keys():
                v = BytesIO(db[k])
                try:
                    self.dict[k] = Unpickler(v).load()
                except ModuleNotFoundError:  # Just throw it away if it won't load.
                    del db[k]
        shelve.Shelf.__init__(self, self.dict, protocol, False, keyencoding)

    def __getitem__(self, key):
        return self.dict[key.encode(self.keyencoding)]

    def __setitem__(self, key, value):
        self.dict[key.encode(self.keyencoding)] = value

    def __delitem__(self, key):
        del self.dict[key.encode(self.keyencoding)]

    def sync(self):
        with dbm.open(self.db, self.flag) as db:
            for k, v in self.dict.items():
                f = BytesIO()
                p = Pickler(f, protocol=self._protocol)
                p.dump(v)
                db[k] = f.getvalue()
            db.sync()

    def close(self):
        try:
            self.sync()
        finally:
            try:
                self.dict = shelve._ClosedDict()
            except Exception:
                self.dict = None


def dict_merge(d, u):
    """
    Given two dictionaries, update the first one with new values provided by
    the second. Works for nested dictionary sets.

    :param d: First Dictionary, to base off of.
    :param u: Second Dictionary, to provide updated values.
    :return: Dictionary. Merged dictionary with bias towards the second.
    """
    for k, v in u.items():
        if isinstance(v, collections.Mapping):
            r = dict_merge(d.get(k, {}), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d


def get_guild_config(cls, gid, key):
    """
    Gets guild-specific configuration for an option, or fills it in with the default if unspecified.
    :param BasePlugin cls: The class calling the function, so it can access plugin-specific configs.
    :param str gid: The guild ID of the guild you're working with, as a str.
    :param str key: The config option you're trying to fetch.
    :return: The config option asked for.
    """
    if gid not in cls.plugin_config:
        cls.plugin_config[gid] = DotDict(cls.plugin_config["default"])
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


async def respond(msg, response, allow_mention_everyone=False, **kwargs):
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


def split_message(message, splitter=None):
    """
    Split message into 2000-character blocks, optionally on specific character.
    :param message: The message to split
    :param splitter: Optional, the string to split on
    """
    msgs = []
    searchpoint = 0
    if splitter:
        while len(message) - searchpoint > 2000:
            searchstr = message[searchpoint:searchpoint + 2000]
            point = searchstr.rfind(splitter)
            if point >= 0:
                point += 1
                msgs.append(message[searchpoint:searchpoint + point])
                searchpoint += point
            else:
                msgs.append(message[searchpoint:searchpoint + 2000])
                searchpoint += 2000
        msgs.append(message[searchpoint:])
    else:
        for x in range(0, len(message), 2000):
            msgs.append(message[x:x + 2000])
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
        raise CommandSyntaxError("Expected positive/negative input. Allowed inputs: off/disable/no/negative/false, "
                                 "on/enable/yes/affirmatie/true.")


