from plugin_manager import BasePlugin
from rs_errors import CommandSyntaxError, UserPermissionError
from rs_utils import respond
from command_dispatcher import Command
import shlex
from discord import Embed, Message


class Voting(BasePlugin):
    name = "voting"

    polls = {}  # dict of lists of polls {gid:{msg.id:Poll}}

    class Poll:

        _abc = "abcdefghijklmnopqrst"
        _emo = "🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹"
        _a_e = dict(zip(_abc, _emo))
        _e_a = dict(zip(_emo, _abc))

        message = None  # message that contains the voting options
        id = 0  # message.id, for speed
        hid = ""  # human-readable ID
        votes = None  # dict of lists of options voted for - member.id : ["a", "b", "c"]
        vote_count = None  # dict of vote numbers
        vote_limit = 0  # 0 for no limit
        query = ""  # the question
        options = None  # dict of strings to vote for {"a":"thing", "b":"other thing"} limit 20 (by the reaction limit)
        active = False
        over = False

        def __init__(self, msg, hid=None, vote_limit=1):
            """
            :type msg:discord.Message
            :param msg:
            :param hid:
            """
            self.message = msg
            self.id = msg.id
            self.hid = hid if hid else str(msg.id)
            self.votes = {}
            self.vote_count = {}
            self.vote_limit = vote_limit
            self.options = {}

        def setquery(self, query):
            """
            :type query:str
            :param query: string of the voting question/query
            """
            self.query = query

        async def addoption(self, option):
            if len(self.options) < 20:
                self.vote_count[self._abc[len(self.options)]] = 0
                await self.message.add_reaction(self._emo[len(self.options)])
                self.options[self._abc[len(self.options)]] = option

        async def update(self):
            await self.message.edit(content="", embed=self._buildembed())

        def _buildembed(self):
            t_embed = Embed(type="rich", colour=16711680)
            t_embed.title = f"\"{self.hid}\""
            t_embed.description = self.query
            for k, v in self.options.items():
                t_embed.add_field(name=f"{self._a_e[k]}", value=f"{v} : {self.vote_count[k]}")
            return t_embed

        async def p_add(self, reaction, user):
            if type(reaction.emoji) == str and self.active:
                if reaction.emoji not in self._emo or not await self.vote(self._e_a[reaction.emoji], user):
                    await reaction.message.remove_reaction(reaction.emoji, user)

        async def p_remove(self, reaction, user):
            if type(reaction.emoji) == str and reaction.emoji in self._emo and self.active:
                await self.vote(self._e_a[reaction.emoji], user, False)

        async def vote(self, option, user, up=True):
            if user.id not in self.votes:
                self.votes[user.id] = set()
            if up:
                if option not in self.votes[user.id]:
                    if len(self.votes[user.id]) < self.vote_limit or self.vote_limit == 0:
                        self.votes[user.id].add(option)
                        self.vote_count[option] += 1
                        await self.update()
                        return True
                    else:
                        return False
            elif option in self.votes[user.id]:
                self.votes[user.id].remove(option)
                self.vote_count[option] -= 1
                await self.update()
                return True

    @Command("StartVote",
             syntax="[Vote ID] [Vote Query] [Vote Questions, up to 20]",
             run_anywhere=True)
    async def _startvote(self, msg: Message):
        """
        Generates a vote, posts a vote embed.
        :type msg: discord.Message
        :param msg:
        :return:
        """
        args = shlex.split(msg.clean_content)
        gid = str(msg.guild.id)
        if gid not in self.polls:
            self.polls[gid] = {}

        if len(args) == 1:
            t_poll = self.Poll(await respond(msg, "**Generating poll message.**"))
            # self.polls[gid].append(self.Poll(await respond(msg, "**Generating poll message.**")))
        else:
            t_poll = self.Poll(await respond(msg, "**Generating poll message.**"), args[1].lower())
            # self.polls[gid].append(self.Poll(await respond(msg, "**Generating poll message.**"), args[1].lower()))
        if len(args) > 2:
            t_poll.setquery(args[2])
        for arg in args[3:]:
            await t_poll.addoption(arg)
        await t_poll.update()
        t_poll.active = True
        self.polls[gid][t_poll.message.id] = t_poll

    @Command("EndVote", run_anywhere=True)
    async def _endvote(self, msg: Message):
        args = shlex.split(msg.clean_content)
        gid = str(msg.guild.id)

        if gid not in self.polls:
            await respond(msg, "**WARNING: No polls active in current server.**")
            return
        elif len(args) > 1:
            candidates = [(k, c) for k, c in self.polls[gid].items()
                          if c.hid == args[1].lower() or str(c.id) == args[1]]
            results = []
            for k, c in candidates:
                max_votes = sorted(c.vote_count.items(), key=lambda x: x[1]).pop()[1]
                winners = '\n'.join(c.options[k] for k, v in c.vote_count.items() if v == max_votes)
                results.append(f'Query: {c.query}. With {max_votes} votes, leading results:\n{winners}')
                del self.polls[gid][k]
            results = '\n\n'.join(results)
            await respond(msg,
                          f"**AFFIRMATIVE. ANALYSIS: {len(candidates)} polls terminated with results:**```{results}```")
        else:
            raise CommandSyntaxError("WARNING: Poll HID or ID required")

    @Command("Vote", "UpVote", "DownVote", run_anywhere=True, delcall=True)
    async def _vote(self, msg: Message):
        args = shlex.split(msg.clean_content)
        gid = str(msg.guild.id)

        if gid in self.polls:
            candidates = [k for k, c in self.polls[gid].items() if c.hid == args[1].lower()]
            if len(candidates) > 1:
                raise CommandSyntaxError("**WARNING: More than one poll with same HID**")
            else:
                up = not args[0].lower().endswith('downvote')
                p = self.polls[gid][candidates[0]]
                if len(args[2]) == 1 and args[2].lower() in "abcdefghijklmnopqrst":
                    result = await p.vote(args[2].lower(), msg.author, up)
                    if not result:
                        raise CommandSyntaxError("Out of votes")
                else:
                    raise CommandSyntaxError(f"Incorrect voting option {args[2]}")

    async def on_reaction_add(self, reaction, user):
        """
        :type reaction:discord.Reaction
        :param reaction:
        :param user:
        :return:
        """
        gid = str(reaction.message.guild.id)
        if gid in self.polls and reaction.message.id in self.polls[gid]:
            await self.polls[gid][reaction.message.id].p_add(reaction, user)

    async def on_reaction_remove(self, reaction, user):
        """
        :type reaction:discord.Reaction
        :param reaction:
        :param user:
        :return:
        """
        gid = str(reaction.message.guild.id)
        if gid in self.polls and reaction.message.id in self.polls[gid]:
            await self.polls[gid][reaction.message.id].p_remove(reaction, user)
