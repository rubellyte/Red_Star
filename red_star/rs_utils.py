# Miscellaneous utility functions and classes found here.
from __future__ import annotations
import argparse
import re
import json
from red_star.rs_errors import CommandSyntaxError
from urllib.parse import urlparse

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import discord
    from pathlib import Path
    from plugin_manager import BasePlugin

JsonValues = None | bool | str | int | float | list | dict


class JsonFileDict(dict):
    """
    Dictionary subclass that handles saving the file on edits automatically.
    Try not to instantiate this class directly; instead, use the config_manager's factory method,
    ConfigManager.get_plugin_config_file.
    :param Path path: The path that should be saved to.
    """

    def __init__(self, path: Path, json_save_args: dict = None, json_load_args: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.path = path
        self.json_save_args = {} if json_save_args is None else json_save_args
        self.json_load_args = {} if json_load_args is None else json_load_args
        self.reload()

    def __setitem__(self, key: str, value: JsonValues):
        super().__setitem__(key, value)
        self.save()

    def __delitem__(self, key: str):
        super().__delitem__(key)
        self.save()

    def save(self):
        with self.path.open("w", encoding="utf-8") as fd:
            json.dump(self, fd, **self.json_save_args)

    def reload(self):
        with self.path.open(encoding="utf-8") as fd:
            self.update(json.load(fd, **self.json_load_args))


class RSNamespace(argparse.Namespace):
    def __getitem__(self, key: str):
        try:
            return self.__getattribute__(key)
        except AttributeError:
            raise KeyError

    def __setitem__(self, key: str, value):
        self.__setattr__(key, value)


class RSArgumentParser(argparse.ArgumentParser):

    def __init__(self, add_help: bool = False, ignore_unrecognized_arguments: bool = True, **kwargs):
        self.ignore_unrecognized_arguments = ignore_unrecognized_arguments
        super().__init__(add_help=add_help, **kwargs)

    def exit(self, status: int = 0, message: str = None):
        raise CommandSyntaxError(message)

    def error(self, message: str):
        raise CommandSyntaxError(message)

    def parse_args(self, args: [str] = None, namespace: argparse.Namespace = None):
        args, argv = self.parse_known_args(args, namespace)
        if argv and not self.ignore_unrecognized_arguments:
            self.error(f"Unrecognized arguments: {' '.join(argv)}")
        return args

    def parse_known_args(self, args: [str] = None, namespace: argparse.Namespace = None):
        if namespace is None:
            namespace = RSNamespace()
        return super().parse_known_args(args=args, namespace=namespace)


def get_guild_config(cls: BasePlugin, gid: str, key: str) -> JsonValues:
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


def sub_user_data(user: discord.abc.User, text: str) -> str:
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


def find_user(guild: discord.Guild, search: str, return_all: bool = False) -> discord.Member | [discord.Member]:
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


def find_role(guild: discord.Guild, search: str, return_all: bool = False) -> discord.Role | [discord.Role]:
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


async def respond(msg: discord.Message, response: str = None, allow_mention_everyone: bool = False, **kwargs):
    """
    Convenience function to respond to a given message. Replaces certain
    patterns with data from the message. Extra kwargs will be passed through to send().
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
        raise SyntaxError("respond() called without any response arguments.")
    return await msg.channel.send(text, **kwargs)


def split_message(input_string: str, max_len: int = 2000, splitter: str = "\n"):
    """
    A helper function that takes in a text string and breaks it into pieces with a maximum size, making sure all
    markdown is properly closed in the process.
    :param input_string: The input string to be split into chunks
    :param max_len: The maximum length of a given chunk
    :param splitter: The token upon which the function should try to split the string
    :return: A list of strings with closed markdown, each within `max_len` length
    """
    final_strings = []
    open_markdown = ""
    if len(input_string) <= max_len:
        return [input_string]
    while True:
        snippet = input_string[:max_len - len(open_markdown)]
        while True:
            # Find the nearest splitter character to the maximum length
            snippet = snippet.rsplit(splitter, 1)[0] or snippet
            cut_length = len(snippet)
            snippet_marked_down = open_markdown + snippet
            # Close the markdown
            snippet_marked_down, extra_md = close_markdown(snippet_marked_down)
            # If, with markdown closed, it fits, continue. Otherwise, run the loop again.
            if len(snippet_marked_down) <= max_len:
                open_markdown = extra_md
                break
            elif len(snippet.strip().rsplit(splitter, 1)) <= 1:
                snippet = snippet[:max_len - len(snippet_marked_down)]
        final_strings.append(snippet_marked_down)
        input_string = input_string[cut_length:]  # Cut down the input string for the next iteration
        if not input_string:
            return final_strings


def close_markdown(input_string: str) -> (str, str):
    """
    A helper function that *attempts* to close markdown left open.
    :param input_string: The string you want to close markdown on.
    :return: A tuple containing the markdown-closed string, and the extra characters that were added to close it.
    """
    code_block_matches = re.findall(r"```\w+\n", input_string)
    in2 = re.sub(r"```\w+\n", "```", input_string)
    md_matches = re.findall(r"(\*\*|\*|~~|__|\|\||```|`)", in2)
    unclosed_matches = "".join({s for s in md_matches if md_matches.count(s) % 2 != 0})
    output = input_string + unclosed_matches
    if code_block_matches:
        unclosed_matches = unclosed_matches.replace("```", code_block_matches[0], 1)
    return output, unclosed_matches


def group_items(items: [str], message: str = "", header: str = '```\n', footer: str = '```',
                joiner: str = '\n') -> [str]:
    """
    Utility function to group a number of list items into sub-2000 length strings for posting through discord.
    Assumes every item is a string and is below 2000 symbols itself.
    :param items: list of strings to group.
    :param message: Optional message to include before the items.
    :param header: For discord formatting, defaults to putting everything into a code block.
    :param footer: The other part of the code block.
    :param joiner: The string to join items with. Called as joiner.join()
    :return: A list of joined strings.
    """
    result = []
    l_max = 2000 - len(header) + len(footer)
    l_join = len(joiner)
    l_temp = len(message)
    r_temp = []
    for i in items:
        if l_temp + len(i) + l_join > l_max:
            result.append(f"{header}{joiner.join(r_temp)}{footer}")
            r_temp = [i]
            l_temp = len(i) + l_join
        else:
            r_temp.append(i)
            l_temp += len(i) + l_join

    result.append(f"{header}{joiner.join(r_temp)}{footer}")
    if message:
        result[0] = message + result[0]

    return result


def ordinal(n: int) -> str:
    """
    Black magic that turns numbers into ordinal representation (1 -> 1st)
    :param n: number to be converted
    :return: string with ordinal number
    """
    return "%d%s" % (n, "tsnrhtdd"[((n // 10) % 10 != 1) * (n % 10 < 4) * n % 10::4])


def decode_json(data: bytes) -> JsonValues:
    """
    A function that tries to decode JSON files in a few common encodings that might come in from users.
    :param data: The raw bytes of the file.
    :return: A valid JSON data type parsed from the file.
    """
    try:
        try:
            json_str = data.decode("utf8")
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


def pretty_time(seconds: float) -> str:
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
        result_list.append("1 day")

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


def is_positive(string: str):
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


def verify_embed(embed: dict):
    """
    A big ugly function to verify the embed dict as best we can.
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
        total_len = 0
        if key in target:
            if isinstance(scheme, dict):
                res[key] = {}
                for field in scheme:
                    if field not in target[key]:
                        continue
                    if scheme[field]:
                        if len(target[key][field]) > scheme[field]:
                            raise ValueError(f"{key}[{field}] too long. (limit {scheme[field]})")
                        total_len += len(target[key][field])
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
                    total_len += len(target[key])
                else:
                    if len(target[key]) > 2048:
                        raise ValueError(f"{key} too long. (limit 2048)")
                    url = urlparse(target[key])
                    if not (url.scheme and url.netloc and url.path):
                        raise ValueError(f"{key} invalid url.")
                res[key] = target[key]
        return total_len

    result = EmbedDict(type='rich')
    embed_len = 0

    embed_len += option(result, 'title', embed, 256)
    embed_len += option(result, 'description', embed, 2048)
    embed_len += option(result, 'url', embed, None)
    embed_len += option(result, 'image', embed, {"url": None})
    embed_len += option(result, 'thumbnail', embed, {"url": None})
    embed_len += option(result, 'footer', embed, {"text": 2048, "icon_url": None})
    embed_len += option(result, 'author', embed, {"name": 256, "url": None, "icon_url": None})

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
            embed_len += len(str(field['name'])) + len(str(field['value']))
            result['fields'].append({
                'name': str(field['name']), 'value': str(field['value']),
                'inline': field.get('inline', False)
            })

    if embed_len > 6000:
        raise ValueError("Embed size exceed maximum size of 6000.")

    return result
