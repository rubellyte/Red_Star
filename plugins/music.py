from plugin_manager import BasePlugin
from utils import Command, respond, process_args
import discord


class MusicPlayer(BasePlugin):
    name = "music_player"

    def activate(self):
        self.vc = False
        self.player = False
        pass

    @Command("joinvc",
             category="voice",
             syntax="",
             doc="")
    async def _joinvc(self, data):
        # 180013430734848001
        self.vc = await self.client.join_voice_channel(data.author.voice.voice_channel)
        await respond(self.client, data, f"**AFFIRMATIVE. Connected to: {data.author.voice.voice_channel}.**")

    @Command("playvc",
             category="voice",
             syntax="",
             doc="")
    async def _playvc(self, data):
        args = process_args(data.content.split())
        if len(args) > 1:
            for voice in self.client.voice_clients:
                if not self.player:
                    self.player = await voice.create_ytdl_player(args[1])
                    self.player.start()
                else:
                    self.player.stop()
                    self.player = await voice.create_ytdl_player(args[1])
                    self.player.start()
                break
        else:
            raise SyntaxError

    @Command("startvc",
             category="voice",
             syntax="",
             doc="")
    async def _startvc(self, data):
        if self.player:
            self.player.start()

    @Command("stopvc",
             category="voice",
             syntax="",
             doc="")
    async def _stopvc(self, data):
        if self.player:
            self.player.stop()
