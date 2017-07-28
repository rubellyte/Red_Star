# Miscellaneous utility functions and classes found here.
import collections
import re
import asyncio


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

@asyncio.coroutine
def respond(client, data, response):
    """
    Convenience function to respond to a given message. Replaces certain
    patterns with data from the message.
    :param data: The message to respond to.
    :param response: The text to respond with.
    :return discord.Message: The Message sent.
    """
    text = sub_user_data(data.author, response)
    m = yield from client.send_message(data.channel, text)
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


class Command:
    """
    Defines a decorator that encapsulates a chat command. Provides a common
    interface for all commands, including roles, documentation, usage syntax,
    and aliases.
    """

    def __init__(self, name, *aliases, perms=set(), doc=None,
                 syntax=None, priority=0, delcall=False):
        if syntax is None:
            syntax = ()
        if isinstance(syntax, str):
            syntax = (syntax,)
        if doc is None:
            doc = ""
        self.name = name
        self.perms = perms
        self.syntax = syntax
        self.human_syntax = " ".join(syntax)
        self.doc = doc
        self.aliases = aliases
        self.priority = priority
        self.delcall = delcall

    def __call__(self, f):
        """
        Whenever a command is called, its handling gets done here.

        :param f: The function the Command decorator is wrapping.
        :return: The now-wrapped command, with all the trappings.
        """
        def wrapped(s, data):
            user_perms = data.author.permissions_in(data.channel)
            try:
                for perm in self.perms:
                    if not getattr(user_perms, perm):
                        raise PermissionError
                return asyncio.ensure_future(f(s, data))
            except PermissionError:
                yield from respond(s.client, data, "You do not have permission to do that, <usernick>.")

        wrapped._command = True
        wrapped._aliases = self.aliases
        wrapped.__doc__ = self.doc
        wrapped.name = self.name
        wrapped.perms = self.perms
        wrapped.syntax = self.human_syntax
        wrapped.priority = self.priority
        wrapped.delcall = self.delcall
        return wrapped
