from sys import argv
import math
import random


def _parse_rpn(args):
    args = [x for x in args]
    if len(args) == 0:
        raise SyntaxError("<rpn> tag requires arguments.")
    stack = []
    out = []

    def _dup(x):
        stack.append(x)
        stack.append(x)

    def _swap(x, y):
        stack.append(x)
        stack.append(y)

    def _modf(x):
        v, v1 = math.modf(x)
        stack.append(v)
        stack.append(v1)

    binary_ops = {
        "+": lambda x, y: stack.append(x + y),
        "-": lambda x, y: stack.append(y - x),
        "*": lambda x, y: stack.append(x * y),
        "/": lambda x, y: stack.append(y / x),
        "^": lambda x, y: stack.append(y ** x),
        "%": lambda x, y: stack.append(y % x),
        "//": lambda x, y: stack.append(y // x),
        "log": lambda x, y: stack.append(math.log(y, x)),
        "atan2": lambda x, y: stack.append(math.atan2(y, x)),
        "swap": _swap,
        "min": lambda x, y: stack.append(min(x, y)),
        "max": lambda x, y: stack.append(max(x, y)),
    }
    unary_ops = {
        "sin": lambda x: stack.append(math.sin(x)),
        "cos": lambda x: stack.append(math.cos(x)),
        "tan": lambda x: stack.append(math.tan(x)),
        "ln": lambda x: stack.append(math.log(x)),
        "pop": lambda x: out.append(x),
        "int": lambda x: stack.append(int(x)),
        "dup": _dup,
        "drop": lambda x: x,
        "modf": _modf,
        "round": lambda x: stack.append(round(x)),
        "rndint": lambda x: stack.append(random.randint(0, x))
    }
    constants = {
        "e": lambda: stack.append(math.e),
        "pi": lambda: stack.append(math.pi),
        "tau": lambda: stack.append(math.tau),
        "m2f": lambda: stack.append(3.280839895),
        "m2i": lambda: stack.append(39.37007874),
        "rnd": lambda: stack.append(random.random())
    }
    for arg in args:
        try:
            value = int(arg, 0)
        except ValueError:
            try:
                value = float(arg)
            except ValueError:
                if arg in binary_ops and len(stack) > 1:
                    binary_ops[arg](stack.pop(), stack.pop())
                elif arg in unary_ops and len(stack) >= 1:
                    unary_ops[arg](stack.pop())
                elif arg in constants:
                    constants[arg]()
            else:
                stack.append(value)
        else:
            stack.append(value)
    return [*out, *stack]


if __name__ == "__main__":
    try:
        print(" ".join(str(x) for x in _parse_rpn(argv[1:])))
    except (ValueError, ZeroDivisionError, SyntaxError) as e:
        print(e)
        raise Exception()
