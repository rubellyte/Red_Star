# Python Lisp parser

import math
import operator as op
import re
import random
import datetime
from time import time
from collections import OrderedDict
from rs_errors import CustomCommandSyntaxError, CommandSyntaxError
from rs_utils import is_positive
from functools import reduce

Symbol = str
Number = (int, float)
List = list

_args = 'args'
_quote = 'quote'
_if = 'if'
_set = ':='
_define = 'define'
_def = 'def'
_lambda = 'lambda'
_begin = 'do'
_unquote = 'unquote'
_checkexpect = 'check-expect'
_checkwithin = 'check-within'
_member = 'member?'
_struct = 'struct'
_access = '>>'
_while = 'while'
_print = 'print'
_try = 'try'

escapes = (("\\\\", "\uff00", "\\"), ("\\\"", "\uff01", "\""), ("\\n", "\uff02", "\n"))


def l_escape(string: str) -> str:
    for p, r, _ in escapes:
        string = string.replace(p, r)
    return string


def l_restore(string: str) -> str:
    for _, p, r in escapes:
        string = string.replace(p, r)
    return string


def tokenize(string: str) -> list:
    return re.findall(r"(?:\").*?(?:\")|\(|\)|[^()\" ]+", l_escape(string), re.DOTALL)


def parse(program: str):
    return read_from_tokens(tokenize(program))


def read_from_tokens(tokens):
    if len(tokens) == 0:
        raise CustomCommandSyntaxError('unexpected EOF while reading')
    token = tokens.pop(0)

    if re.match(r'\".*\"', token, re.DOTALL):
        return ['quote', l_restore(token[1:-1])]

    elif '(' == token:
        l = []
        while tokens[0] != ')':
            t = read_from_tokens(tokens)
            if t != '':
                l.append(t)
        tokens.pop(0)
        return l

    elif ';' == token:
        l = []
        l.append(token)
        while tokens[0] != '\n':
            l.append(read_from_tokens(tokens))
        new_line = tokens.pop(0)
        l.append(new_line)
        string = l_restore(" ".join(l))
        return ['quote', string]

    elif ')' == token:
        raise CustomCommandSyntaxError('unexpected )')
    else:
        return atom(re.sub(r"^\s+|\s+$", "", token))


def atom(token: str):
    try:
        return int(token)
    except ValueError:
        try:
            return float(token)
        except ValueError:
            try:
                return is_positive(token)
            except CommandSyntaxError:
                return token.lower()


# =============================================================================================================
# Evaluator

# A user-defined Scheme procedure.
class Procedure(object):
    def __init__(self, parms, body, env):
        self.parms, self.body, self.env = parms, body, env

    def __call__(self, *args):
        return lisp_eval(self.body, Env(self.parms, args, self.env))


class Env(dict):
    def __init__(self, parms=(), args=(), outer=None, max_runtime=0):
        self.update(zip(parms, args))
        self.outer = outer
        self.timestamp = time()
        self.max_runtime = max_runtime

    # Find the innermost Env where var appears.
    def find(self, var):
        if var in self:
            return self
        elif self.outer:
            return self.outer.find(var)
        else:
            raise CustomCommandSyntaxError(f'undefined var {var}')


def get_args(args: list) -> (list, dict):
    t_list = [*args]
    t_dict = OrderedDict()
    for n, a in [*enumerate(t_list)][::-1]:
        if type(a) == str and a.startswith(':'):
            try:
                t_dict[a[1:]] = t_list.pop(n + 1)
            except IndexError:
                raise CustomCommandSyntaxError(f"supplied argument {a} given without value")
            del t_list[n]
    return t_list, OrderedDict(reversed(t_dict.items()))


def _str(*args):
    if not args:
        return
    elif len(args) == 1:
        return str(args[0])
    else:
        try:
            return getattr(str, args[0])(*args[1:])
        except AttributeError:
            raise CustomCommandSyntaxError(f'str does not have method {args[1]}')


def eztime(*args):
    time = datetime.datetime.utcnow()

    if args:
        strf = args[0] if args[0] else "%Y-%m-%d @ %H:%M:%S"
        if len(args) > 1:
            o_time = re.match(r"(?P<h>-?\d*):(?P<m>-?\d*):(?P<s>-?\d*)", args[1])
            if o_time:
                o_time = o_time.groupdict()
                delta = datetime.timedelta(hours=int(o_time['h']) if o_time['h'] else 0,
                                           minutes=int(o_time['m']) if o_time['m'] else 0,
                                           seconds=int(o_time['s']) if o_time['s'] else 0)
            else:
                raise CustomCommandSyntaxError(f"(eztime) invalid offset string \"{args[1]}\". "
                                               f"Please use H:M:S format.")
        else:
            delta = datetime.timedelta()
        time = time + delta
        return time.strftime(strf)
    else:
        return time.strftime("%Y-%m-%d @ %H:%M:%S")


def _assert(var, vartype, *opt):
    try:
        if vartype == 'int':
            return int(var)
        elif vartype == 'float':
            return float(var)
        elif vartype == 'list':
            return list(*var)
    except (ValueError, TypeError):
        if opt:
            return opt[0]
        else:
            raise CustomCommandSyntaxError(f'assertion error: {var} is not a valid {vartype}')


def transcode(string: str, *args):
    if len(args) == 0:
        return string
    elif len(args) == 1:
        def_code = "ABCDEFGHIJKLMabcdefghijklmNOPQRSTUVWXYZnopqrstuvwxyz"
        alt_code = {
            "rot13": "NOPQRSTUVWXYZnopqrstuvwxyzABCDEFGHIJKLMabcdefghijklm",
            "circled": "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ",
            "circled_neg": "🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩",
            "fwidth": "ＡＢＣＤＥＦＧＨＩＪＫＬＭａｂｃｄｅｆｇｈｉｊｋｌｍＮＯＰＱＲＳＴＵＶＷＸＹＺｎｏｐｑｒｓｔｕｖｗｘｙｚ",
            "mbold": "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳",
            "mbolditalic": "𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛",
            "frakturbold": "𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟",
            "fraktur": "𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷",
            "scriptbold": "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃",
            "script": "𝒜𝐵𝒞𝒟𝐸𝐹𝒢𝐻𝐼𝒥𝒦𝐿𝑀𝒶𝒷𝒸𝒹𝑒𝒻𝑔𝒽𝒾𝒿𝓀𝓁𝓂𝒩𝒪𝒫𝒬𝑅𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝓃𝑜𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏",
            "sans": "𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖺𝖻𝖼𝖽𝖾𝖿𝗀𝗁𝗂𝗃𝗄𝗅𝗆𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹𝗇𝗈𝗉𝗊𝗋𝗌𝗍𝗎𝗏𝗐𝗑𝗒𝗓",
            "sansbold": "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇",
            "sansbolditalic": "𝘼𝘽𝘾𝘿𝙀𝙁𝙂𝙃𝙄𝙅𝙆𝙇𝙈𝙖𝙗𝙘𝙙𝙚𝙛𝙜𝙝𝙞𝙟𝙠𝙡𝙢𝙉𝙊𝙋𝙌𝙍𝙎𝙏𝙐𝙑𝙒𝙓𝙔𝙕𝙣𝙤𝙥𝙦𝙧𝙨𝙩𝙪𝙫𝙬𝙭𝙮𝙯",
            "sansitalic": "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻",
            "parenthesized": "⒜⒝⒞⒟⒠⒡⒢⒣⒤⒥⒦⒧⒨⒜⒝⒞⒟⒠⒡⒢⒣⒤⒥⒦⒧⒨⒩⒪⒫⒬⒭⒮⒯⒰⒱⒲⒳⒴⒵⒩⒪⒫⒬⒭⒮⒯⒰⒱⒲⒳⒴⒵",
            "doublestruck": "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫",
            "region": "🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿",
            "squared": "🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉",
            "squared_neg": "🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉",
            "subscript": "ₐBCDₑFGₕᵢⱼₖₗₘₐbcdₑfgₕᵢⱼₖₗₘₙₒₚQᵣₛₜᵤᵥWₓYZₙₒₚqᵣₛₜᵤᵥwₓyz",
            "superscript": "ᴬᴮᶜᴰᴱᶠᴳᴴᴵᴶᴷᴸᴹᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐᴺᴼᴾQᴿˢᵀᵁⱽᵂˣʸᶻⁿᵒᵖqʳˢᵗᵘᵛʷˣʸᶻ",
            "inverted": "ɐqɔpǝɟƃɥıɾʞןɯɐqɔpǝɟƃɥıɾʞןɯuodbɹsʇn𐌡ʍxʎzuodbɹsʇnʌʍxʎz",
            "reversed": "AdↃbƎꟻGHIJK⅃MAdↄbɘꟻgHijklmᴎOꟼpᴙꙄTUVWXYZᴎoqpᴙꙅTUvwxYz",
            "smallcaps": "ABCDEFGHIJKLMᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍNOPQRSTUVWXYZɴᴏᴩqʀꜱᴛᴜᴠᴡxyᴢ",
            "weird1": "ልጌርዕቿቻኗዘጎጋጕረጠልጌርዕቿቻኗዘጎጋጕረጠክዐየዒዪነፕሁሀሠሸሃጊክዐየዒዪነፕሁሀሠሸሃጊ",
            "weird2": "ДБҀↁЄFБНІЈЌLМаъсↁэfБЂіјкlмИФРQЯЅГЦVЩЖЧZиорqѓѕтцvшхЎz",
            "weird3": "ค๒ƈɗﻉिﻭɦٱﻝᛕɭ๓ค๒ƈɗﻉिﻭɦٱﻝᛕɭ๓กѻρ۹ɼรՇપ۷ฝซץչกѻρ۹ɼรՇપ۷ฝซץչ",
            "weird4": "αв¢∂єƒﻭнιנкℓмαв¢∂єƒﻭнιנкℓмησρ۹яѕтυνωχуչησρ۹яѕтυνωχуչ",
            "weird5": "ค๒ς๔єŦﻮђเןкɭ๓ค๒ς๔єŦﻮђเןкɭ๓ภ๏קợгรՇยשฬאץչภ๏קợгรՇยשฬאץչ",
            "weird6": "ﾑ乃cd乇ｷgんﾉﾌズﾚﾶﾑ乃cd乇ｷgんﾉﾌズﾚﾶ刀oｱq尺丂ｲu√wﾒﾘ乙刀oｱq尺丂ｲu√wﾒﾘ乙",
            "sbancient": ""
        }
        if args[0].lower() == 'help':
            return "```\nAVAILABLE TRANSCODINGS:\n" + "\n".join(alt_code.keys()) + "```"
        elif args[0].lower() not in alt_code:
            raise CustomCommandSyntaxError(f"{args[0].lower()} is not a supported transcoding. Use (transcode "
                                           f"\"help\") to get a list of available transcodings.")
        else:
            alt_code = alt_code[args[0].lower()]
    else:
        def_code = args[0]
        alt_code = args[1]
        if len(def_code) != len(alt_code):
            raise CustomCommandSyntaxError("transcode: To and From transcoding patterns must be the same length.")
    return string.translate(str.maketrans(def_code, alt_code))


def standard_env(*_, **kwargs):
    env = Env(**kwargs)
    env.update(vars(math))
    env.update({
        '+': op.add, '-': op.sub, '*': op.mul, '/': op.truediv, '//': op.floordiv, '%': op.mod,
        '>': op.gt, '<': op.lt, '>=': op.ge, '<=': op.le, '==': op.eq, '<>': op.xor,
        '!=': lambda *x: op.not_(op.eq(*x)),
        '#': lambda x, y: y[x],
        'abs': abs,
        'append': lambda x, y: x.append(y) if type(x) == list else x + y,
        'apply': lambda proc, args: proc(*args),
        'do': lambda *x: x[-1],
        'car': lambda x: x[0],
        'cdr': lambda x: x[1:],
        'cons': lambda x, y: [x] + y,
        'is': op.is_,
        'in': op.contains,
        'len': len,
        'list': lambda *x: list(x),
        'l': lambda *x: list(x),
        'tolist': list,
        '2l': list,
        'range': range,
        'list?': lambda x: isinstance(x, list),
        'map': lambda *x: list(map(*x)),
        'imap': map,
        'sum': sum,
        'max': max,
        'filter': filter,
        'reduce': reduce,
        'sort': sorted,
        'reverse': lambda x: x[::-1],
        'ireverse': reversed,
        'pass': lambda *x: None,
        'min': min,
        'not': op.not_,
        'null?': lambda x: x == [],
        'number?': lambda x: isinstance(x, Number),
        'procedure?': callable,
        'round': round,
        'symbol?': lambda x: isinstance(x, Symbol),
        'assert': _assert,
        'f': lambda *x: "".join(map(str, x)),

        'int': int,
        'float': float,
        'zip': zip,

        'resub': re.sub,
        'rematch': re.match,
        'refindall': re.findall,

        'str': _str,
        'transcode': transcode,

        'randint': random.randint,
        'choice': lambda *x: random.choices(*x).pop(),

        'eztime': eztime,
        'time': time,
        'ezchoice': lambda *x: random.choice(x),

        # to be overriden by the cc function
        "username": "",
        "usernick": "",
        "usermention": "",
        "authorname": "",
        "authornick": "",
        "argstring": "",
        "args": [],

        "output": ""
    })
    return env


global_env = standard_env()


# Make predicates and field functions of a user defined struct
def make_functions(name, param, env=global_env):
    create = 'make-' + name
    check = name + '?'
    index_array = []
    key_array = []
    i = 0
    for par in param:
        index_array.append(i)
        i += 1

    for par in param:
        key_array.append(name + '-' + par + '-pos')

    env.update(zip(key_array, index_array))

    env[name + '-pos'] = lambda arr, index: arr[index]

    env[check] = lambda arr: len(arr) == lisp_eval(create)
    env[create] = len(param)


# recursively access the list and set the last item
def _lset(lst, val, *indexes):
    if len(indexes) == 1:
        lst[indexes[0]] = val
    else:
        _lset(lst[indexes[0]], val, *indexes[1:])


# search for a list item recursively
def _lget(lst, *indexes):
    if len(indexes) == 0:
        return lst
    elif len(indexes) == 1:
        return lst[indexes[0]]
    else:
        return _lget(lst[indexes[0]], *indexes[1:])


# Evaluate an expression in an environment.f
def lisp_eval(x, env=global_env):
    if env.max_runtime != 0 and time() - env.timestamp > env.max_runtime:
        raise CustomCommandSyntaxError("The command ran too long.")
    try:
        if isinstance(x, Symbol):  # variable reference
            l, *ind = x.split(':')
            ind = [int(x) if x.isdigit() else lisp_eval(x, env) for x in ind]
            return _lget(env.find(l)[l], *ind)
        elif not isinstance(x, list):  # constant literal
            return x
        elif x[0] == _args:
            argstring = env.find('argstring')['argstring']
            arglist = env.find('args')['args']
            if len(x) == 1:
                return argstring
            if len(x) == 2:
                if x[1] == '*':
                    return arglist
                else:
                    try:
                        return arglist[x[1]]
                    except IndexError:
                        return None
            else:
                try:
                    if x[1] == '*':
                        return arglist[:x[2]]
                    elif x[2] == '*':
                        return arglist[x[1]:]
                    else:
                        return arglist[x[1]:x[2]]
                except IndexError:
                    return []
        elif x[0] == _quote:  # quotation
            (_, exp) = x
            return exp
        elif x[0] == _access:  # attempt using an object method
            a = list(map(lambda i: lisp_eval(i, env), x[1:]))
            try:
                ar, kw = get_args(a[2:])
                return getattr(a[1], a[0])(*ar, **kw)
            except AttributeError:
                raise CustomCommandSyntaxError(f'{type(a[1])} has no method {a[0]}')
        elif x[0] == _if:  # conditional (if bool then else)
            (_, test, conseq, alt) = x
            exp = (conseq if lisp_eval(test, env) else alt)
            return lisp_eval(exp, env)
        elif x[0] in [_define, _def]:  # definition
            (_, var, exp) = x
            env[var] = lisp_eval(exp, env)
        elif x[0] == _set:  # assignment
            (_, var, exp) = x
            if ':' in var:
                l, *ind = var.split(':')
                ind = [int(x) if x.isdigit() else lisp_eval(x, env) for x in ind]
                _lset(env.find(l)[l], lisp_eval(exp, env), *ind)
            else:
                env.find(var)[var] = lisp_eval(exp, env)
        elif x[0] == _lambda:  # procedure
            (_, parms, body) = x
            return Procedure(parms, body, env)
        elif x[0] == _checkexpect:  # test exact
            (_, var, exp) = x
            return lisp_eval(var, env) == lisp_eval(exp, env)
        elif x[0] == _checkwithin:  # test range
            (_, var, lower_bound, upper_bound) = x
            return ((lisp_eval(var, env) <= lisp_eval(upper_bound, env) and
                     (lisp_eval(var, env) >= lisp_eval(lower_bound, env))))
        elif x[0] == _member:  # member?
            (_, var, lst) = x
            return lisp_eval(var, env) in lisp_eval(lst, env)
        elif x[0] == _struct:  # struct definition
            (_, name, params) = x
            make_functions(name, params, env)
        elif x[0] == _while:  # while loop
            while lisp_eval(x[1], env):
                lisp_eval(x[2], env)
        elif x[0] == _print:  # prints into "output" variable
            try:
                env.find('output')['output'] += f'{" ".join(map(lambda y: str(lisp_eval(y,env)), x[1:]))}\n'
            except IndexError:
                env.find('output')['output'] += '\n'
        elif x[0] == _try:  # (try (body) (except)) - returns result of body if successful or evaluates except if not
            expr, *args = x[1:]
            try:
                return lisp_eval(expr, env)
            except Exception as e:
                if len(args) >= 1:
                    return lisp_eval(args[0], env)
                else:
                    return e
        elif x[0] == _unquote:
            return lisp_eval(lisp_eval(x[1], env), env)
        else:  # procedure call
            proc = lisp_eval(x[0], env)
            if isinstance(x[0], str) and x[0].startswith('make-'):
                args = [lisp_eval(arg, env) for arg in x[2:]]
                if len(args) != proc:
                    print(f'TypeError: {x[0]} requires {proc}%d values, given {len(args)}')
                else:
                    env[x[1]] = args
                return
            else:
                args = [lisp_eval(arg, env) for arg in x[1:]]
            return proc(*args)
    except Exception as e:
        if len(str(e)) > 1500:
            e = "..." + re.match(r"(?:.+)(\(.+?\): .+?$)", str(e)).group(1)
        try:
            raise CustomCommandSyntaxError(f"({x[0]}): {e}")
        except IndexError:
            raise CustomCommandSyntaxError(e)
