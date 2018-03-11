from plugin_manager import BasePlugin
from rs_utils import respond
from command_dispatcher import Command
from rs_errors import CommandSyntaxError
from discord import File
from discord.errors import NotFound
from io import BytesIO
import time


class DumpChannel(BasePlugin):
    name = "dump_channel"

    @Command("Dump",
             doc="Dumps the messages between two specified messages into a text file, inclusively.",
             syntax="(latest message ID) (earliest message ID) [filename]",
             perms={"manage_messages"},
             run_anywhere=True)
    async def _dump(self, msg):
        args = msg.content.split(" ", 3)
        if len(args) < 3:
            raise CommandSyntaxError("Wrong number of arguments.")
        try:
            m_start = int(args[1])
        except ValueError:
            raise CommandSyntaxError("First Argument is not a valid integer.")

        try:
            m_end = int(args[2])
        except ValueError:
            raise CommandSyntaxError("Second Argument is not a valid integer.")
        try:
            m_start = await msg.channel.get_message(m_start)
        except NotFound:
            raise CommandSyntaxError(f"No message with ID {m_start}")
        try:
            m_end = await msg.channel.get_message(m_end)
        except NotFound:
            raise CommandSyntaxError(f"No message with ID {m_end}")

        if len(args) > 3:
            t_name = args[3]+".txt"
        else:
            t_name = str(time.time())+".txt"

        s = "%Y-%m-%d %H:%M:%S"

        t_list = [f"{str(m_end.author)} @ {str(m_end.created_at.strftime(s))}\n{m_end.clean_content}\n\n"]

        async for msg in msg.channel.history(before=m_start, after=m_end, reverse=True, limit=None):
            t_list.append(f"{str(msg.author)} @ {str(msg.created_at.strftime(s))}\n{msg.clean_content}\n\n")

        t_list.append(f"{str(m_start.author)} @ {str(m_start.created_at.strftime(s))}\n{m_start.clean_content}")

        t_msg = await respond(msg, f"**AFFIRMATIVE. Processing file {t_name}.**")
        async with msg.channel.typing():
            await respond(msg, "**AFFIRMATIVE. Completed file upload.**",
                          file=File(BytesIO(bytes("".join(t_list), encoding="utf-8")), filename=t_name))
        await t_msg.delete()
