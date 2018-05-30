# Miscellaneous utility functions and classes found here.
import collections
import dbm
import re
import shelve
import json
from io import BytesIO
from pickle import Pickler, Unpickler
from rs_errors import CommandSyntaxError
import argparse


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
        """error(message: string)

        Prints a usage message incorporating the message to stderr and
        exits.

        If you override this in a subclass, it should not return -- it
        should either exit or raise an exception.
        """
        # self.print_usage(_sys.stderr)
        # args = {'prog': self.prog, 'message': message}
        # self.exit(2, _('%(prog)s: error: %(message)s\n') % args)
        raise CommandSyntaxError(message)

    def parse_args(self, args=None, namespace=None):
        args, argv = self.parse_known_args(args, namespace)
        if argv and not self.ignore_unrecognized_arguments:
            msg = 'Unrecognized arguments: %s'
            self.error(msg % ' '.join(argv))
        return args

    def parse_known_args(self, args=None, namespace=None):
        if args is None:
            raise CommandSyntaxError("No arguments. How did you even manage that.")
        else:
            # make sure that args are mutable
            args = list(args)

        # default Namespace built from parser defaults
        if namespace is None:
            namespace = RSNamespace()

        # add any action defaults that aren't present
        for action in self._actions:
            if action.dest is not argparse.SUPPRESS:
                if not hasattr(namespace, action.dest):
                    if action.default is not argparse.SUPPRESS:
                        setattr(namespace, action.dest, action.default)

        # add any parser defaults that aren't present
        for dest in self._defaults:
            if not hasattr(namespace, dest):
                setattr(namespace, dest, self._defaults[dest])

        # parse the arguments and exit if there are any errors
        try:
            namespace, args = self._parse_known_args(args, namespace)
            if hasattr(namespace, argparse._UNRECOGNIZED_ARGS_ATTR):
                args.extend(getattr(namespace, argparse._UNRECOGNIZED_ARGS_ATTR))
                delattr(namespace, argparse._UNRECOGNIZED_ARGS_ATTR)
            return namespace, args
        except argparse.ArgumentError:
            err = argparse._sys.exc_info()[1]
            self.error(str(err))

    def _parse_known_args(self, arg_strings, namespace):
        # replace arg strings that are file references
        if self.fromfile_prefix_chars is not None:
            arg_strings = self._read_args_from_files(arg_strings)

        # map all mutually exclusive arguments to the other arguments
        # they can't occur with
        action_conflicts = {}
        for mutex_group in self._mutually_exclusive_groups:
            group_actions = mutex_group._group_actions
            for i, mutex_action in enumerate(mutex_group._group_actions):
                conflicts = action_conflicts.setdefault(mutex_action, [])
                conflicts.extend(group_actions[:i])
                conflicts.extend(group_actions[i + 1:])

        # find all option indices, and determine the arg_string_pattern
        # which has an 'O' if there is an option at an index,
        # an 'A' if there is an argument, or a '-' if there is a '--'
        option_string_indices = {}
        arg_string_pattern_parts = []
        arg_strings_iter = iter(arg_strings)
        for i, arg_string in enumerate(arg_strings_iter):

            # all args after -- are non-options
            if arg_string == '--':
                arg_string_pattern_parts.append('-')
                for arg_string in arg_strings_iter:
                    arg_string_pattern_parts.append('A')

            # otherwise, add the arg to the arg strings
            # and note the index if it was an option
            else:
                option_tuple = self._parse_optional(arg_string)
                if option_tuple is None:
                    pattern = 'A'
                else:
                    option_string_indices[i] = option_tuple
                    pattern = 'O'
                arg_string_pattern_parts.append(pattern)

        # join the pieces together to form the pattern
        arg_strings_pattern = ''.join(arg_string_pattern_parts)

        # converts arg strings to the appropriate and then takes the action
        seen_actions = set()
        seen_non_default_actions = set()

        def take_action(action, argument_strings, option_string=None):
            seen_actions.add(action)
            argument_values = self._get_values(action, argument_strings)

            # error if this argument is not allowed with other previously
            # seen arguments, assuming that actions that use the default
            # value don't really count as "present"
            if argument_values is not action.default:
                seen_non_default_actions.add(action)
                for conflict_action in action_conflicts.get(action, []):
                    if conflict_action in seen_non_default_actions:
                        msg = 'not allowed with argument %s'
                        action_name = argparse._get_action_name(conflict_action)
                        raise argparse.ArgumentError(action, msg % action_name)

            # take the action if we didn't receive a SUPPRESS value
            # (e.g. from a default)
            if argument_values is not argparse.SUPPRESS:
                action(self, namespace, argument_values, option_string)

        # function to convert arg_strings into an optional action
        def consume_optional(start_index):

            # get the optional identified at this index
            option_tuple = option_string_indices[start_index]
            action, option_string, explicit_arg = option_tuple

            # identify additional optionals in the same arg string
            # (e.g. -xyz is the same as -x -y -z if no args are required)
            match_argument = self._match_argument
            action_tuples = []
            while True:

                # if we found no optional action, skip it
                if action is None:
                    extras.append(arg_strings[start_index])
                    return start_index + 1

                # if there is an explicit argument, try to match the
                # optional's string arguments to only this
                if explicit_arg is not None:
                    arg_count = match_argument(action, 'A')

                    # if the action is a single-dash option and takes no
                    # arguments, try to parse more single-dash options out
                    # of the tail of the option string
                    chars = self.prefix_chars
                    if arg_count == 0 and option_string[1] not in chars:
                        action_tuples.append((action, [], option_string))
                        char = option_string[0]
                        option_string = char + explicit_arg[0]
                        new_explicit_arg = explicit_arg[1:] or None
                        optionals_map = self._option_string_actions
                        if option_string in optionals_map:
                            action = optionals_map[option_string]
                            explicit_arg = new_explicit_arg
                        else:
                            raise argparse.ArgumentError(action, 'ignored explicit argument %r' % explicit_arg)

                    # if the action expect exactly one argument, we've
                    # successfully matched the option; exit the loop
                    elif arg_count == 1:
                        stop = start_index + 1
                        args = [explicit_arg]
                        action_tuples.append((action, args, option_string))
                        break

                    # error if a double-dash option did not use the
                    # explicit argument
                    else:
                        raise argparse.ArgumentError(action, 'ignored explicit argument %r' % explicit_arg)

                # if there is no explicit argument, try to match the
                # optional's string arguments with the following strings
                # if successful, exit the loop
                else:
                    start = start_index + 1
                    selected_patterns = arg_strings_pattern[start:]
                    arg_count = match_argument(action, selected_patterns)
                    stop = start + arg_count
                    args = arg_strings[start:stop]
                    action_tuples.append((action, args, option_string))
                    break

            # add the Optional to the list and return the index at which
            # the Optional's string args stopped
            assert action_tuples
            for action, args, option_string in action_tuples:
                take_action(action, args, option_string)
            return stop

        # the list of Positionals left to be parsed; this is modified
        # by consume_positionals()
        positionals = self._get_positional_actions()

        # function to convert arg_strings into positional actions
        def consume_positionals(start_index):
            # match as many Positionals as possible
            match_partial = self._match_arguments_partial
            selected_pattern = arg_strings_pattern[start_index:]
            arg_counts = match_partial(positionals, selected_pattern)

            # slice off the appropriate arg strings for each Positional
            # and add the Positional and its args to the list
            for action, arg_count in zip(positionals, arg_counts):
                args = arg_strings[start_index: start_index + arg_count]
                start_index += arg_count
                take_action(action, args)

            # slice off the Positionals that we just parsed and return the
            # index at which the Positionals' string args stopped
            positionals[:] = positionals[len(arg_counts):]
            return start_index

        # consume Positionals and Optionals alternately, until we have
        # passed the last option string
        extras = []
        start_index = 0
        if option_string_indices:
            max_option_string_index = max(option_string_indices)
        else:
            max_option_string_index = -1
        while start_index <= max_option_string_index:

            # consume any Positionals preceding the next option
            next_option_string_index = min([
                index
                for index in option_string_indices
                if index >= start_index])
            if start_index != next_option_string_index:
                positionals_end_index = consume_positionals(start_index)

                # only try to parse the next optional if we didn't consume
                # the option string during the positionals parsing
                if positionals_end_index > start_index:
                    start_index = positionals_end_index
                    continue
                else:
                    start_index = positionals_end_index

            # if we consumed all the positionals we could and we're not
            # at the index of an option string, there were extra arguments
            if start_index not in option_string_indices:
                strings = arg_strings[start_index:next_option_string_index]
                extras.extend(strings)
                start_index = next_option_string_index

            # consume the next optional and any arguments for it
            start_index = consume_optional(start_index)

        # consume any positionals following the last Optional
        stop_index = consume_positionals(start_index)

        # if we didn't consume all the argument strings, there were extras
        extras.extend(arg_strings[stop_index:])

        # make sure all required actions were present and also convert
        # action defaults which were not given as arguments
        required_actions = []
        for action in self._actions:
            if action not in seen_actions:
                if action.required:
                    required_actions.append(argparse._get_action_name(action))
                else:
                    # Convert action default now instead of doing it before
                    # parsing arguments to avoid calling convert functions
                    # twice (which may fail) if the argument was given, but
                    # only if it was defined already in the namespace
                    if (action.default is not None and
                        isinstance(action.default, str) and
                        hasattr(namespace, action.dest) and
                        action.default is getattr(namespace, action.dest)):
                        setattr(namespace, action.dest,
                                self._get_value(action, action.default))

        if required_actions:
            self.error('Missing arguments: %s.' % ', '.join(required_actions))

        # make sure all required groups had one option present
        for group in self._mutually_exclusive_groups:
            if group.required:
                for action in group._group_actions:
                    if action in seen_non_default_actions:
                        break

                # if no actions were used, report the error
                else:
                    names = [argparse._get_action_name(action)
                             for action in group._group_actions
                             if action.help is not argparse.SUPPRESS]
                    self.error('one of the arguments %s is required' % ' '.join(names))

        # return the updated namespace and the extra arguments
        return namespace, extras


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
