# Error classes in a neutral space to avoid import order issues.


class CommandSyntaxError(Exception):
    # We don't want to catch code-based syntax errors by accident
    pass


class UserPermissionError(Exception):
    # For when a command user lacks the permissions needed.
    # We don't want to catch OS permission errors by accident, unlikely as they are
    pass


class ChannelNotFoundError(TypeError):
    # For when a channel of type x doesn't exist
    pass


class CustomCommandSyntaxError(CommandSyntaxError):
    # For when the CC author made a syntax error
    pass


class ConsoleCommandSyntaxError(CommandSyntaxError):
    # For errors in console commands
    pass

class DataCarrier(Exception):
    # This is intended to carry a message up out of a stack, not to signal any actual error.
    def __init__(self, data):
        self.data = data
