from __future__ import annotations
from red_star.command_dispatcher import Command
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import CommandSyntaxError
from red_star.rs_utils import respond, decode_json, split_message, verify_embed
from urllib.parse import urlparse
from urllib.request import urlopen
from urllib.error import URLError
import mimetypes
import re
import json
import discord
from io import BytesIO


def verify_document(doc: list):
    """
    A helper function to verify entire documents.
    Verifies that messages are of correct length, embeds are valid and file links are non-mangled.
    :param doc:
    :return:
    """
    result = []
    for i, msg in enumerate(doc):
        if isinstance(msg, str):
            if len(msg) > 2000:
                raise ValueError(f"Message {i+1} is too long. (Limit 2000)")
            result.append(msg)
        else:
            try:
                _msg = dict()
                if 'content' in msg:
                    if len(str(msg['content'])) > 2000:
                        raise ValueError(f"Message {i+1} is too long. (Limit 2000)")
                    _msg['content'] = str(msg['content'])
                if 'embed' in msg:
                    try:
                        _msg['embed'] = verify_embed(doc[i]['embed'])
                    except ValueError as e:
                        raise ValueError(f"Message {i+1} invalid embed: {e}")

                if 'file' in msg:
                    url = urlparse(msg['file'])
                    if not (url.scheme and url.netloc and url.path):
                        raise ValueError(f"Message {i+1} invalid attach url.")
                    _msg['file'] = msg['file']
                result.append(_msg)
            except TypeError:
                raise ValueError(f"Message {i+1} not an object or string.")
    return result


def verify_links(doc: list, max_size: int):
    """
    A secondary helper functions for the purpose of checking all the links for both existing and being within limit.
    :param doc: document, a list of messages or dicts
    :param max_size: maximum size of a file in octets
    :return:
    """
    for i, msg in enumerate(doc):
        try:
            _file = urlopen(msg['file'])
            if int(_file.info()['Content-Length']) > max_size:
                raise ValueError(f"Message {i+1} attached file too big.")
        except (TypeError, KeyError):
            continue
        except ValueError as e:
            raise ValueError(e)
        except Exception as e:
            raise ValueError(f"Message {i+1} dead attachment link: {e}.")


class ChannelPrint(BasePlugin):
    name = "channel_print"
    version = "1.0"
    author = "GTG3000"
    description = "A plugin that allows printing of prepared multi-message data."

    default_global_config = {
        "max_filesize": 1024 * 1024 * 8  # max 8 mb
    }
    log_events = {"print_event"}

    async def activate(self):
        self._port_old_storage()
        self.storage.setdefault("documents", {})

    def _port_old_storage(self):
        old_storage_path = self.config_manager.config_path / "walls.json"
        if old_storage_path.exists():
            with old_storage_path.open(encoding="utf-8") as fp:
                old_storage = json.load(fp)
            for guild_id, walls in old_storage.items():
                try:
                    new_storage = self.config_manager.storage_files[guild_id][self.name]
                except KeyError:
                    self.logger.warn(f"Server with ID {guild_id} not found! Is the bot still in this server?\n"
                                     f"Skipping conversion of this server's channel print document storage...")
                    continue
                new_storage.contents["documents"] = walls
                new_storage.save()
                new_storage.load()
            old_storage_path = old_storage_path.replace(old_storage_path.with_suffix(".json.old"))
            self.logger.info(f"Old channel print document storage converted to new format. "
                             f"Old data now located at {old_storage_path} - you may delete this file.")

    def storage_save_args(self):
        return {'indent': 2, 'ensure_ascii': False}

    @Command("Print", "PrintForce",
             doc="Prints out the specified document from the storage, allowing to dump large amounts of information "
                 "into a channel, for example for purposes of a rules channel.\n"
                 "Document can be specified from the saved ones, or uploaded with the command.\n"
                 "Use \"PrintForce\" alias to force printing despite broken attachment links.",
             syntax="(document)",
             perms={"manage_messages"},
             category="channel_print",
             run_anywhere=True,
             delcall=True)
    async def _print(self, msg: discord.Message):
        cmd, *args = msg.clean_content.split(None, 1)

        if msg.attachments:
            _file = BytesIO()

            await msg.attachments[0].save(_file)
            try:
                wall = decode_json(_file.getvalue())
            except json.JSONDecodeError as e:
                raise CommandSyntaxError(f"Not a valid JSON file: {e}")
            except ValueError as e:
                self.logger.exception("Could not decode uploaded document file!", exc_info=True)
                raise CommandSyntaxError(e)
        else:
            try:
                wall = args[0]
            except IndexError:
                raise CommandSyntaxError

            if wall not in self.storage["documents"]:
                raise CommandSyntaxError("No such document.")
            wall = self.storage["documents"][wall]

        try:
            wall = verify_document(wall)
            if not cmd.lower().endswith("force"):
                verify_links(wall, self.global_plugin_config['max_filesize'])
        except ValueError as e:
            raise CommandSyntaxError(e)

        for post in wall:
            if isinstance(post, str):
                await respond(msg, post)
            else:
                _file = None
                if 'file' in post:
                    try:
                        _file = urlopen(post['file'])
                        if int(_file.info()['Content-Length']) > self.global_plugin_config['max_filesize']:
                            raise ValueError("File too big.")
                        ext = mimetypes.guess_extension(_file.info()['Content-Type'])
                        _file = discord.File(_file, filename="wallfile" + ext)
                    except (URLError, TypeError, ValueError) as e:
                        self.logger.info(f"Attachment file error in {msg.guild}:\n{e}")
                        await self.plugin_manager.hook_event("on_log_event",
                                                             f"**WARNING: Error occured during printout:**\n{e}",
                                                             log_type="print_event")
                        _file = None  # Just fail silently if the request doesn't work out
                if _file or 'embed' in post or 'content' in post:
                    await respond(msg,
                                  post.get('content', None),
                                  embed=post['embed'] if 'embed' in post else None,
                                  file=_file)

    @Command("DeletePrint", "PrintDelete",
             doc="Deletes the specified document.",
             syntax="(document)",
             perms={"manage_messages"},
             category="channel_print")
    async def _deleteprint(self, msg: discord.Message):
        try:
            name = msg.clean_content.split(None, 2)[1].lower()
            del self.storage["documents"][name]
            self.storage_file.save()
            await respond(msg, "**AFFIRMATIVE. Document deleted.**")
        except IndexError:
            raise CommandSyntaxError("Document name required.")
        except KeyError:
            raise CommandSyntaxError("No document found.")

    @Command("ListPrint", "PrintList",
             doc="Lists all available documents.",
             perms={"manage_messages"},
             category="channel_print")
    async def _listprint(self, msg: discord.Message):
        walls = "\n".join(self.storage["documents"].keys())
        final_msg = f"**ANALYSIS: Following documents are available:**```\n{walls}```"
        for split_msg in split_message(final_msg):
            await respond(msg, split_msg)

    @Command("DumpPrint", "PrintDump",
             doc="Uploads the specified document in a json file format.",
             syntax="(document)",
             perms={"manage_messages"},
             category="channel_print")
    async def _dumpprint(self, msg: discord.Message):
        try:
            name = msg.clean_content.split(None, 2)[1].lower()
            dump_data = bytes(json.dumps(self.storage["documents"][name], indent=2, ensure_ascii=False),
                              encoding="utf8")
            await respond(msg, "**AFFIRMATIVE. Uploading file.**",
                          file=discord.File(BytesIO(dump_data), filename=name+'.json'))
        except IndexError:
            raise CommandSyntaxError("Document name required.")
        except KeyError:
            raise CommandSyntaxError("No document found.")

    @Command("UploadPrint", "PrintUpload",
             doc="Allows you to upload a document, in a JSON file format or a JSON code block.",
             syntax="(document_id) (code block or attached file)",
             perms={"manage_messages"},
             category="channel_print")
    async def _uploadprint(self, msg: discord.Message):
        try:
            name = msg.clean_content.split(None, 2)[1].lower()
        except IndexError:
            raise CommandSyntaxError("Document name required.")

        if msg.attachments:
            _file = BytesIO()

            await msg.attachments[0].save(_file)
            try:
                data = decode_json(_file.getvalue())
            except ValueError as e:
                self.logger.exception("Could not decode uploaded document file!", exc_info=True)
                raise CommandSyntaxError(e)
            except Exception as e:
                raise CommandSyntaxError(f"Not a valid JSON file: {e}")
        else:
            try:
                data = re.match(r"```.*?(?P<json>\[.+]).*?```", msg.clean_content.split(None, 2)[2], re.DOTALL)['json']
                data = json.loads(data)
            except IndexError:
                raise CommandSyntaxError("JSON code block required.")
            except TypeError:
                raise CommandSyntaxError("Invalid JSON template. The root must be a list.")
            except Exception as e:
                raise CommandSyntaxError(f"Not a valid JSON file: {e}")

        try:
            data = verify_document(data)
        except ValueError as e:
            raise CommandSyntaxError(e)

        self.storage["documents"][name] = data
        self.storage_file.save()

        await respond(msg, f"**AFFIRMATIVE. Document {name} available for printout.**")

    @Command("PrintReload",
             doc="Reloads all documents from list. You probably shouldn't be using this too often.",
             bot_maintainers_only=True,
             category="channel_print")
    async def _printreload(self, msg: discord.Message):
        self.storage.load()
        await respond(msg, "**AFFIRMATIVE. Printout documents reloaded.**")
