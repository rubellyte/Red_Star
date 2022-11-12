from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import CommandSyntaxError, UserPermissionError
from red_star.rs_utils import respond, RSArgumentParser
from red_star.command_dispatcher import Command
import shlex
import discord


class Voting(BasePlugin):
    name = "voting"
    version = "1.0"
    author = "GTG3000"
    description = "A plugin for creating, voting in, and automatically tallying the results of polls."

    polls = {}  # dict of lists of polls {gid:{msg.id:Poll}}

    class Poll:

        _abc = "abcdefghijklmnopqrst"
        _emo = "🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹"
        _a_e = dict(zip(_abc, _emo))  # easy letter to emote conversion
        _e_a = dict(zip(_emo, _abc))  # easy emote to letter conversion

        message = None  # message that contains the voting options
        author = None  # author ID (we don't really need anything else)
        id = 0  # message.id, for speed
        hid = ""  # human-readable ID
        votes = None  # dict of lists of options voted for - member.id : ["a", "b", "c"]
        vote_count = None  # dict of vote numbers
        vote_limit = 0  # 0 for no limit
        query = ""  # the question
        options = None  # dict of strings to vote for {"a":"thing", "b":"other thing"} limit 20 (by the reaction limit)
        active = False
        allow_retracting = True

        def __init__(self, msg: discord.Message, hid: str = None, vote_limit: int = 1, author: int = None,
                     allow_retracting: bool = True):
            self.message = msg
            self.author = author
            self.id = msg.id
            self.hid = hid if hid else str(msg.id)
            self.votes = {}
            self.vote_count = {}
            self.vote_limit = vote_limit
            self.allow_retracting = allow_retracting
            self.options = {}

        def setquery(self, query: str):
            """
            :param query: string of the voting question/query
            """
            self.query = query

        async def add_option(self, option: str):
            if len(self.options) < 20:
                self.vote_count[self._abc[len(self.options)]] = 0
                await self.message.add_reaction(self._emo[len(self.options)])
                self.options[self._abc[len(self.options)]] = option

        async def update(self):
            await self.message.edit(content="", embed=self._build_embed())

        def _build_embed(self):
            t_embed = discord.Embed(type="rich", colour=16711680)
            t_embed.title = f"\"{self.hid}\""
            t_embed.description = f"{self.query}\n\nBy <@{self.author}>"
            for k, v in self.options.items():
                t_embed.add_field(name=f"{self._a_e[k]}", value=f"{v} : {self.vote_count[k]}")
            return t_embed

        async def add_reaction(self, reaction: discord.Reaction, user: discord.Member):
            if isinstance(reaction.emoji, str) and self.active:
                if reaction.emoji not in self._emo or not await self.vote(self._e_a[reaction.emoji], user):
                    await reaction.message.remove_reaction(reaction.emoji, user)

        async def remove_reaction(self, reaction: discord.Reaction, user: discord.Member):
            if isinstance(reaction.emoji, str) and reaction.emoji in self._emo and self.active:
                await self.vote(self._e_a[reaction.emoji], user, False)

        async def vote(self, option: str, user: discord.Member, up: bool = True) -> bool:
            """

            :param option: The option for which the vote is being placed.
            :param user: The user placing the vote.
            :param up: Whether this is a placement or retraction of a vote.
            :return: Whether the vote or retraction was successful.
            """
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
            elif option in self.votes[user.id] and self.allow_retracting:
                self.votes[user.id].remove(option)
                self.vote_count[option] -= 1
                await self.update()
                return True
            else:
                return False

    @Command("StartVote",
             syntax="(HID) (Query) [Questions, up to 20] [-1/--question, up to 20] [-v/vote_limit, integer, "
                    "0 for no limit] [-n/--no_retracting, to disallow removing votes]",
             doc="Starts a new vote, with provided Human-readableID, Query and Questions.\n"
                 "Use -v to allow users to vote for more than one option and -n to prevent users from changing their"
                 "mind.\nUses shlex for splitting, so multiple words can be wrapped into \"\".\n"
                 "HID is used to interact with the poll through other commands, keep it one word.",
             run_anywhere=True,
             category="voting")
    async def _startvote(self, msg: discord.Message):
        """
        Generates a vote, posts a vote embed.

        :param msg: The Message containing the command.
        """
        args = shlex.split(msg.clean_content)
        gid = str(msg.guild.id)

        if gid not in self.polls:
            self.polls[gid] = {}

        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("poll_hid")
        parser.add_argument("query")
        parser.add_argument("questions", default=[], nargs='*')
        parser.add_argument("--question", "-q", default=[], action="append")
        parser.add_argument("--vote_limit", "-v", default=1, type=int)
        parser.add_argument("--no_retracting", "-n", action="store_false")

        args = parser.parse_args(args)

        t_poll = self.Poll(await respond(msg, "**Generating poll message.**"),
                           hid=args['poll_hid'].lower(),
                           author=msg.author.id,
                           vote_limit=args['vote_limit'],
                           allow_retracting=args['no_retracting'])
        t_poll.setquery(args['query'])
        for opt in [*args['questions'], *args['question']]:
            await t_poll.add_option(opt)

        await t_poll.update()
        t_poll.active = True
        self.polls[gid][t_poll.message.id] = t_poll

    @Command("EndVote", run_anywhere=True,
             syntax="(HID)",
             doc="Ends the given vote. You must be the creator of the vote to end it.\n"
                 "Alternatively, you must have manage_messages permission or be a bot maintainer.",
             category="voting",
             optional_perms={"end_others": {"manage_messages"}})
    async def _endvote(self, msg: discord.Message):
        args = msg.clean_content.split(maxsplit=1)
        gid = str(msg.guild.id)

        if gid not in self.polls:
            await respond(msg, "**WARNING: No polls active in current server.**")
            return
        elif len(args) > 1:
            candidates = [(k, c) for k, c in self.polls[gid].items()
                          if c.hid == args[1].lower() or str(c.id) == args[1]]
            results = []
            for k, c in candidates:
                if c.author != msg.author.id and \
                        self._endvote.perms.check_optional_permissions("end_others", msg.author, msg.channel):
                    continue
                max_votes = sorted(c.vote_count.items(), key=lambda x: x[1]).pop()[1]
                winners = '\n'.join(c.options[k] for k, v in c.vote_count.items() if v == max_votes)
                results.append(f'Query: {c.query}. With {max_votes} votes, leading results:\n{winners}')
                del self.polls[gid][k]
            if not results:
                raise UserPermissionError
            results = '\n\n'.join(results)
            await respond(msg, f"**AFFIRMATIVE. ANALYSIS: {len(candidates)} polls terminated with results:**"
                               f"```{results}```")
        else:
            raise CommandSyntaxError("WARNING: Poll HID or ID required")

    @Command("Vote", "UpVote", "DownVote", run_anywhere=True, delcall=True,
             syntax="(hid) (option, single letter from a to t)",
             doc="Allows users to vote without using reactions.\n"
                 "Use \"DownVote\" variant to remove your vote, if possible.",
             category="voting")
    async def _vote(self, msg: discord.Message):
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
                        if up:
                            await respond(msg, "**NEGATIVE: Out of votes.**", delete_after=5)
                        else:
                            await respond(msg, "**NEGATIVE: Could not remove vote.**", delete_after=5)
                else:
                    raise CommandSyntaxError(f"Incorrect voting option {args[2]}")

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """
        :type reaction:discord.Reaction
        :param reaction:
        :param user:
        :return:
        """
        gid = str(reaction.message.guild.id)
        if gid in self.polls and reaction.message.id in self.polls[gid]:
            await self.polls[gid][reaction.message.id].add_reaction(reaction, user)

    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        """
        :type reaction:discord.Reaction
        :param reaction:
        :param user:
        :return:
        """
        gid = str(reaction.message.guild.id)
        if gid in self.polls and reaction.message.id in self.polls[gid]:
            await self.polls[gid][reaction.message.id].remove_reaction(reaction, user)
