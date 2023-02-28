import discord

from red_star.plugin_manager import BasePlugin
from red_star.rs_utils import respond
from red_star.command_dispatcher import Command
from red_star.rs_errors import CommandSyntaxError
from random import randint
from collections import defaultdict
from enum import Enum
import re


roll_tokens = re.compile(r"\d+(?:\.\d+)?|d(?:\d+|f)[da]?|[+\-/*()]")


class Adv(Enum):
    n = 0
    a = 1
    d = 2


def parse_roll(roll_string: str):
    rolls = []

    def rpn(string: str):
        # tokenize by only finding the valid operators
        tokens = roll_tokens.findall(string.lower())

        # turn into reverse polish notation for easier parsing
        prec = defaultdict(lambda: 3, {
            '(': 0,
            '-': 1,
            '+': 1,
            '*': 2,
            '/': 2
        })

        polish = []
        ops = []
        unary_minus_flag = True  # ugh
        new_expr_flag = False  # because people may not write right

        for token in tokens:
            try:
                try:
                    val = int(token)
                except ValueError:
                    val = float(token)

                if new_expr_flag:
                    polish.extend(ops[::-1])
                    ops = []

                polish.append(val)
                unary_minus_flag = False
                new_expr_flag = True
            except ValueError:
                new_expr_flag = False
                if token == '(':
                    ops.append(token)
                    unary_minus_flag = True
                elif token == ')':
                    while ops and ops[-1] != '(':
                        polish.append(ops.pop())
                    if ops:
                        ops.pop()
                    unary_minus_flag = False
                elif token[0] == 'd':
                    polish.append(token)
                    unary_minus_flag = False
                else:
                    # unary minuses are hard.
                    if unary_minus_flag and token == '-':
                        token = '_'
                    unary_minus_flag = token in '*/+-'

                    # as cool as it would be to have strings of data then strings of operators, this works better
                    while ops and prec[ops[-1]] >= prec[token]:
                        polish.append(ops.pop())
                    ops.append(token)

        polish.extend(ops[::-1])

        return polish

    def roll(dice: str, stack: list):
        num = min(max(round(stack.pop()), 1), 10000) if stack else 1

        if dice[-1] in 'ad':
            reroll = Adv.a if dice[-1] == 'a' else Adv.d
            side = 'f' if dice[1:-1] == 'f' else int(dice[1:-1])
        else:
            reroll = Adv.n
            side = 'f' if dice[1:] == 'f' else int(dice[1:])

        if side == 'f':
            def diceroll():
                return randint(-1, 1)
        else:
            side = min(max(side, 2), 10000)

            def diceroll():
                return randint(1, side)

        roll_a = [diceroll() for _ in range(num)]
        roll_b = [diceroll() for _ in range(num)]

        if reroll == Adv.a:
            roll_a = roll_a if sum(roll_a) > sum(roll_b) else roll_b
        elif reroll == Adv.d:
            roll_a = roll_a if sum(roll_a) < sum(roll_b) else roll_b

        rolls.append(f"{num}d{side}{'a' if reroll == Adv.a else ('d' if reroll == Adv.d else '')} - {sum(roll_a):2d}"
                     f" {roll_a}")

        stack.append(sum(roll_a))

    # evaluate using reverse polish notation rules

    polish = rpn(roll_string)
    stack = []

    u_ops = {
        '_': lambda: stack.append(-stack.pop())
    }

    b_ops = {
        '+': lambda x, y: stack.append(y + x),
        '-': lambda x, y: stack.append(y - x),
        '/': lambda x, y: stack.append(y / x),
        '*': lambda x, y: stack.append(y * x)
    }

    while polish:
        token = polish.pop(0)
        if isinstance(token, (int, float)):
            stack.append(token)
        elif len(stack) > 1 and token in b_ops:
            b_ops[token](stack.pop(), stack.pop())
        elif len(stack) > 0 and token in u_ops:
            u_ops[token]()
        elif token[0] == 'd':
            roll(token, stack)

    return stack, rolls


class DiceRoll(BasePlugin):
    name = "diceroll"
    description = "A plugin for rolling dice and dice accessories."
    version = "1.0"
    author = "GTG3000"

    @Command("Roll",
             doc="Rolls a specified amount of specified dice with specified bonus and advantage/disadvantage.\n\n"
                 "The parser can evaluate full dice expressions, including basic calculations such as addition, "
                 "subtraction, multiplication and division.\n"
                 "It is also capable of doing multiple rolls per same expression, '4df 4df' for example.\n"
                 "'dn' is treated as an unary operator, so for example '2d6 d6' will roll 2d6 and then roll that "
                 "amount of d6.",
             syntax="[number]D(die/F)[A/D][+/-bonus]",
             category="role_play",
             run_anywhere=True)
    async def _roll(self, msg: discord.Message):
        args = msg.clean_content.split(None, 1)
        if len(args) < 2:
            raise CommandSyntaxError("Requires a roll expression.")

        results, rolls = parse_roll(args[1])
        roll_args = ' '.join(roll_tokens.findall(args[1])).upper()

        results = (str(x) for x in results)

        if rolls:
            t_string = f"**ANALYSIS: {msg.author.display_name} has attempted a " \
                       f"{roll_args} roll, getting {', '.join(results)}.\n" \
                       f"ANALYSIS: Rolled dice:** ```\n"
            if len(rolls[0]) + len(t_string) <= 1996:
                for r in rolls:
                    if len(t_string) + len(r) > 1996:
                        t_string += r[:1993 - len(t_string)] + '...'
                        break
                    else:
                        t_string += r + '\n'
                t_string += '```'
            else:
                t_string += rolls[0][:1990 - len(t_string)] + '...\n```'
            await respond(msg, t_string)
        else:
            await respond(msg, f"**ANALYSIS: expression {roll_args} evaluated. Result: {', '.join(results)}**")
