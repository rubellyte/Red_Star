# Miscellaneous utility functions and classes found here.
import collections
import re
import asyncio
from functools import reduce


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
    funcs = (lambda x: x.id == search, lambda x: x.mention == search, lambda x: str(x).lower() == search.lower(),
             lambda x: x.display_name.lower() == search.lower(), lambda x: x.name.lower() == search.lower())
    final = []
    for func in funcs:
        found = tuple(filter(func, guild.members))
        if found:
            if return_all:
                final += found
            else:
                return found[0]
    return final


async def respond(msg, response, **kwargs):
    """
    Convenience function to respond to a given message. Replaces certain
    patterns with data from the message.
    :param msg: The message to respond to.
    :param response: The text to respond with.
    :return discord.Message: The Message sent.
    """
    text = None
    if response:
        text = sub_user_data(msg.author, response)
        if len(text) > 2000:
            # shoulda split it first
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


def process_args(args):
    """
    Goes through the presented result of data.content.split() and stitches anything between !" and " into one argument,
    allowing arguments with spaces and " in them like '!editrole !"my role" name=!"new name heck" color=FFFFFF'
    """
    newargs = []
    t_list = []
    t_cap = False
    for arg in args[::-1]:
        if t_cap:
            t_list.append(arg)
            if arg.startswith('!"') or arg.find('=!"') > -1:
                t_cap = False
                # stitch together the bits in reverse order with spaces between them, remove !" and trailing "
                newargs.append(str(reduce(lambda a, x: a + " " + x, t_list[::-1])).replace('!"', "", 1)[0:-1])
                t_list = []
        else:
            if arg.endswith('"'):
                if arg.find('!"') > -1:
                    newargs.append(arg.replace("!\"", "", 1)[0:-1])
                else:
                    t_cap = True
                    t_list.append(arg)
            else:
                newargs.append(arg)
    if len(t_list) > 0:
        raise SyntaxError
    return newargs[::-1]


def ordinal(n):
    """
    Black magic that turns numbers into ordinal representation (1 -> 1st)
    :param n: number to be converted
    :return: string with ordinal number
    """
    return "%d%s" % (n, "tsnrhtdd"[((n//10) % 10 != 1)*(n % 10 < 4)*n % 10::4])


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


class Command:
    """
    Defines a decorator that encapsulates a chat command. Provides a common
    interface for all commands, including roles, documentation, usage syntax,
    and aliases.
    """

    def __init__(self, name, *aliases, perms=set(), doc=None, syntax=None, priority=0, delcall=False,
                 run_anywhere=False, category="other"):
        if syntax is None:
            syntax = ()
        if isinstance(syntax, str):
            syntax = (syntax,)
        if doc is None:
            doc = ""
        self.name = name
        if isinstance(perms, str):
            perms = {perms}
        self.perms = perms
        self.syntax = syntax
        self.human_syntax = " ".join(syntax)
        self.doc = doc
        self.aliases = aliases
        self.priority = priority
        self.delcall = delcall
        self.run_anywhere = run_anywhere
        self.category = category

    def __call__(self, f):
        """
        Whenever a command is called, its handling gets done here.

        :param f: The function the Command decorator is wrapping.
        :return: The now-wrapped command, with all the trappings.
        """

        def wrapped(s, msg):
            user_perms = msg.author.permissions_in(msg.channel)
            user_perms = {x for x, y in user_perms if y}
            try:
                if not user_perms >= self.perms:
                    raise PermissionError
                return asyncio.ensure_future(f(s, msg))
            except PermissionError:
                return asyncio.ensure_future(respond(msg, "**NEGATIVE. INSUFFICIENT PERMISSION: <usernick>.**"))

        wrapped._command = True
        wrapped._aliases = self.aliases
        wrapped.__doc__ = self.doc
        wrapped.name = self.name
        wrapped.perms = self.perms
        wrapped.syntax = self.human_syntax
        wrapped.priority = self.priority
        wrapped.delcall = self.delcall
        wrapped.run_anywhere = self.run_anywhere
        wrapped.category = self.category
        return wrapped
