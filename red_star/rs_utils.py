# Miscellaneous utility functions and classes found here.
import argparse
import re
import json
from red_star.rs_errors import CommandSyntaxError
from urllib.parse import urlparse
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
        if not allow_mention_everyone:  # Filter these out just in case we miss it somehow
            text = response.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
        else:
            text = response
        # should've split it first
        # this is just a last-ditch error check
        text = text[:2000]
    elif not kwargs:
        # It's empty, raise an error.
        raise SyntaxError
    return await msg.channel.send(text, **kwargs)


def split_message(message_str, splitter=None, max_len=2000):
    """
    Split message into 2000-character blocks, optionally on specific character.
    :param message_str: The message to split
    :param splitter: Optional, the string to split on. Default None.
    :param max_len: The maximum length of the message blocks. Default 2000.
    """
    msgs = []
    search_point = 0
    if splitter:
        while len(message_str) - search_point > max_len:
            searchstr = message_str[search_point:search_point + max_len]
            point = searchstr.rfind(splitter)
            if point >= 0:
                point += 1
                msgs.append(message_str[search_point:search_point + point])
                search_point += point
            else:
                msgs.append(message_str[search_point:search_point + max_len])
                search_point += max_len
        msgs.append(message_str[search_point:])
    else:
        for x in range(0, len(message_str), max_len):
            msgs.append(message_str[x:x + max_len])
    return msgs


async def split_output(message, title, items, *, header="```\n", footer="```",
                       string_processor=lambda x: str(x) + "\n"):
    """
    :type title: str
    :type header: str
    :type footer: str
    :param message: a discord.Message object to respond to
    :param title: a title string, appended before the list
    :param items: a list of items to iterate over
    :param header: a header string, put between title and items
    :param footer: a footer string, capping up the lists
    :param string_processor: a function to run on the items. Must take one argument (the item) and return a string
    :return:
    """
    final_str = title + header
    footer_len = len(footer)
    for i in items:
        processed_str = string_processor(i)
        if len(final_str+processed_str) > 2000-footer_len:
            await respond(message, final_str+footer)
            final_str = header+processed_str
        else:
            final_str += processed_str
    await respond(message, final_str+footer)


def ordinal(n):
    """
    Black magic that turns numbers into ordinal representation (1 -> 1st)
    :param n: number to be converted
    :return: string with ordinal number
    """
    return "%d%s" % (n, "tsnrhtdd"[((n//10) % 10 != 1)*(n % 10 < 4)*n % 10::4])


def decode_json(data):
    try:
        try:
            json_str = data.decode()
        except UnicodeDecodeError:
            try:
                json_str = data.decode(encoding="windows-1252")
            except UnicodeDecodeError:
                try:
                    json_str = data.decode(encoding="windows-1250")
                except UnicodeDecodeError:
                    raise ValueError("Unable to parse file encoding. Please use UTF-8")
        else:
            if json_str[0] != "{":
                json_str = data.decode(encoding="utf-8-sig")
        json_object = json.loads(json_str)
    except json.decoder.JSONDecodeError as e:
        raise ValueError(f"Not a valid JSON file: {e}")
    return json_object


def pretty_time(seconds):
    """
    Pretty time display function
    :param seconds: time in seconds
    :return: time in weeks, days and h:mm:ss
    """
    MINUTE_SECONDS = 60
    HOUR_SECONDS = 3600
    DAY_SECONDS = 86400
    WEEK_SECONDS = 604800

    weeks, days = divmod(int(seconds), WEEK_SECONDS)
    days, hours = divmod(days, DAY_SECONDS)
    hours, minutes = divmod(hours, HOUR_SECONDS)
    minutes, seconds = divmod(minutes, MINUTE_SECONDS)

    result_list = []
    if weeks > 1:
        result_list.append(f"{weeks} weeks")
    elif weeks == 1:
        result_list.append("1 week")

    if days > 1:
        result_list.append(f"{days} days")
    elif days == 1:
        result_list.append("1 day_seconds")

    if hours > 0:
        if minutes == seconds == 0:
            if hours > 1:
                result_list.append(f"{hours} hours")
            else:
                result_list.append("1 hour")
        else:
            result_list.append(f"{hours}:{minutes:02d}:{seconds:02d}")
    elif minutes > 0:
        if seconds == 0:
            if minutes > 1:
                result_list.append(f"{minutes} minutes")
            else:
                result_list.append("1 minute")
        else:
            result_list.append(f"{minutes}:{seconds:02d}")
    elif seconds > 1:
        result_list.append(f"{seconds:02d} seconds")
    elif seconds == 1:
        result_list.append("1 second")

    return ", ".join(result_list)


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


def parse_roll(dice_str, roll=None):
    dice_data = re.search(r"^(\d*)d(\d+|f)([ad]?)", dice_str)
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
        advantage = dice_data.group(3)
        dice_set_a = [roll_function() for _ in range(num_dice)]
        dice_set_b = [roll_function() for _ in range(num_dice)]
        if advantage == "a":
            rolled_dice = dice_set_a if sum(dice_set_a) >= sum(dice_set_b) else dice_set_b
        elif advantage == "d":
            rolled_dice = dice_set_a if sum(dice_set_a) < sum(dice_set_b) else dice_set_b
        else:
            rolled_dice = dice_set_a
        if roll is not None:
            roll.append(f"{dice_data.string:5} - {sum(rolled_dice):2d} {rolled_dice} ")
        return rolled_dice
    else:
        try:
            return int(dice_str)
        except ValueError:
            return dice_str


def parse_tokens(tokens, roll=None):
    """
    Function that runs over a list and processes tokens.
    Runs repeatedly to support nested :dn expressions like d6:d6:d6 and 1:d6+1
    No need to sanitize tokens inside here since the initial rollstring parse only grabs what fits the regexp.
    :param tokens:
    :param roll:
    :return:
    """
    tokens = [sum(t) if type(t) == list else t for t in tokens]

    # improved :dn support to allow repeated parsing (since the regex nature of :dn makes it hard to prioritize
    rerun = True
    while rerun:
        rerun = False
        for i in range(len(tokens))[::-1]:
            try:
                if tokens[i] == '*':
                    tokens[i - 1:i + 2] = [tokens[i - 1] * tokens[i + 1]]
                elif tokens[i] == "/":
                    tokens[i - 1:i + 2] = [tokens[i - 1] / tokens[i + 1]]
                elif tokens[i] == "+":
                    tokens[i - 1:i + 2] = [tokens[i - 1] + tokens[i + 1]]
                elif tokens[i] == "-":
                    if type(tokens[i-1]) in [int, float]:  # it may just be denoting the number to be negative
                        tokens[i - 1:i + 2] = [tokens[i - 1] - tokens[i + 1]]
                    else:
                        tokens[i:i+2] = [-tokens[i+1]]
                elif type(tokens[i]) == str and re.match(':d[\df]+', tokens[i]):
                    if type(tokens[i-1]) == int:
                        tokens[i-1:i+1] = [sum(parse_roll(f"{tokens[i-1]}{tokens[i][1:]}", roll=roll))]
                    else:
                        rerun = True
            except IndexError:
                del tokens[i]
            except TypeError:
                rerun = True

    return tokens


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
    for open_bracket in brackets:
        try:
            close_bracket = open_bracket + tokens[open_bracket:].index(')')
            if close_bracket - open_bracket == 1:
                del tokens[close_bracket]
                del tokens[open_bracket]
            else:
                r = parse_tokens(tokens[open_bracket + 1:close_bracket], roll=rolled_dice)
                tokens[open_bracket:close_bracket + 1] = [r[0]]

        except ValueError:
            tokens.pop(open_bracket)

    return parse_tokens(tokens, roll=rolled_dice), rolled_dice


def verify_embed(embed: dict):
    """
    A big ugly function to verify the embed dict as best as we can.
    Made even uglier by the verbosity I choose to include in the verification.
    :param embed:
    :return:
    """

    class EmbedDict(dict):
        # A simple class that allows the output of this command to be used in place of discord.py Embed class for
        # channel.send() purposes.
        def to_dict(self):
            return self

    def option(res: dict, key: str, target: dict, scheme: (dict, int, None)):
        """
        Verification function.
        Scheme can be a length for text fields or None for url verification.
        Otherwise, it may be a dict of fields with either lengths or None for urls.
        URLs are limited to 2048 symbols by default.
        :param res: "result" dict to put the values into
        :param key: Key to be verified
        :param target: The "embed" dict to pull values from
        :param scheme: Verification scheme
        :return: No returns, the result is added to res parameter. To prevent adding empty fields.
        """
        _len = 0
        if key in target:
            if isinstance(scheme, dict):
                res[key] = {}
                for field in scheme:
                    if field not in target[key]:
                        continue
                    if scheme[field]:
                        if len(target[key][field]) > scheme[field]:
                            raise ValueError(f"{key}[{field}] too long. (limit {scheme[field]})")
                        _len += len(target[key][field])
                    else:
                        # verify URL
                        if len(target[key][field]) > 2048:
                            raise ValueError(f"{key}[{field}] tool long. (limit 2048)")
                        url = urlparse(target[key][field])
                        if not (url.scheme and url.netloc and url.path):
                            raise ValueError(f"{key}[{field}] invalid url.")
                    res[key][field] = target[key][field]
            else:
                if scheme:
                    if len(target[key]) > scheme:
                        raise ValueError(f"{key} too long. (limit {scheme})")
                    _len += len(target[key])
                else:
                    if len(target[key]) > 2048:
                        raise ValueError(f"{key} too long. (limit 2048)")
                    url = urlparse(target[key])
                    if not (url.scheme and url.netloc and url.path):
                        raise ValueError(f"{key} invalid url.")
                res[key] = target[key]
        return _len

    result = EmbedDict(type='rich')
    _len = 0

    _len += option(result, 'title', embed, 256)
    _len += option(result, 'description', embed, 2048)
    _len += option(result, 'url', embed, None)
    _len += option(result, 'image', embed, {"url": None})
    _len += option(result, 'thumbnail', embed, {"url": None})
    _len += option(result, 'footer', embed, {"text": 2048, "icon_url": None})
    _len += option(result, 'author', embed, {"name": 256, "url": None, "icon_url": None})

    if 'color' in embed:
        try:
            result['color'] = int(embed['color'], 0)
        except TypeError:
            try:
                result['color'] = int(embed['color'])
            except ValueError:
                raise ValueError("Invalid color value.")

    if 'fields' in embed:
        result['fields'] = []
        for i, field in enumerate(embed['fields']):
            if not isinstance(field.get('inline', False), bool):
                raise ValueError(f"Field {i+1}, \"inline\" must be true or false.")
            if len(str(field['name'])) > 256:
                raise ValueError(f"Field {i+1} \"name\" too long. (Limit 256)")
            if len(str(field['value'])) > 1024:
                raise ValueError(f"Field {i+1} \"value\" too long. (Limit 1024)")
            _len += len(str(field['name'])) + len(str(field['value']))
            result['fields'].append({
                                        'name': str(field['name']), 'value': str(field['value']),
                                        'inline': field.get('inline', False)
                                    })

    if _len > 6000:
        raise ValueError("Embed size exceed maximum size of 6000.")

    return result
