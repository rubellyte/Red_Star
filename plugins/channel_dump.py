from plugin_manager import BasePlugin
from rs_utils import Command, respond
from rs_errors import CommandSyntaxError
from discord import File
from io import BytesIO
import time


class DumpChannel(BasePlugin):
    name = "dump_channel"

    @Command("dump",
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
        if not await msg.channel.get_message(m_start):
            raise CommandSyntaxError(f"No message with ID {m_start}")
        if not await msg.channel.get_message(m_end):
            raise CommandSyntaxError(f"No message with ID {m_end}")

        if len(args) > 3:
            t_name = "."+args[3]+".txt"
        else:
            t_name = str(time.time())+".txt"

        flag = False

        t_list = []

        async for message in msg.channel.history():
            if message.id == m_start:
                flag = True
            if flag:
                t_list.append(f"{str(message.author)} @ {str(message.created_at)}\n{message.clean_content}\n\n")
            if message.id == m_end:
                break

        t_msg = await respond(msg, f"**AFFIRMATIVE. Processing file {t_name}.**")
        async with msg.channel.typing():
            await respond(msg, "**AFFIRMATIVE. Completed file upload.**",
                          file=File(BytesIO(bytes("".join(t_list[::-1]), encoding="utf-8")), filename=t_name))
        await t_msg.delete()
