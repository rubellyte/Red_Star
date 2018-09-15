import asyncio
import logging
from argparse import ArgumentParser
from logging.handlers import RotatingFileHandler
from os import chdir
from pathlib import Path
from red_star.client import RedStar


def main():
    chdir(Path(__file__).parent)
    default_user_dir = Path.home() / ".red_star"

    verbose_docstr = "Enables debug output. Calling multiple times increases verbosity; two calls enables discord.py" \
                     " debug output, and three calls enables asyncio's debug mode."
    parser = ArgumentParser(description="General-purpose Discord bot with administration and entertainment functions.")
    parser.add_argument("-v", "--verbose", "-d", "--debug", action="count", help=verbose_docstr, default=0)
    parser.add_argument("-c", "--config", type=Path, default=default_user_dir, help="Sets the path to the "
                                                                                    "configuration directory.")
    parser.add_argument("-l", "--logfile", type=Path, default=default_user_dir / "red_star.log", help="Sets the path to"
                                                                                                      " the log file.")
    args = parser.parse_args()

    if args.verbose > 0:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s # %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    base_logger = logging.getLogger()
    stream_logger = logging.StreamHandler()
    stream_logger.setLevel(loglevel)
    stream_logger.setFormatter(formatter)
    base_logger.addHandler(stream_logger)

    if not args.config.exists():
        base_logger.warning(f"Specified config directory {args.config} does not exist! Creating now...")
        config_folder = args.config / "config"
        config_folder.mkdir(parents=True)
        plugins_folder = args.config / "plugins"
        plugins_folder.mkdir(parents=True)
        plugin_init = plugins_folder / "__init__.py"
        plugin_init.touch()

    if args.logfile.is_dir():
        args.logfile /= "red_star.log"

    if not args.logfile.exists():
        args.logfile.touch()

    file_logger = RotatingFileHandler(args.logfile, maxBytes=1048576, backupCount=5, encoding="utf-8")
    file_logger.setLevel(loglevel)
    file_logger.setFormatter(formatter)
    base_logger.addHandler(file_logger)

    loop = asyncio.get_event_loop()

    if args.verbose >= 3:
        loop.set_debug(True)
        logging.getLogger("asyncio").setLevel(logging.DEBUG)
    else:
        logging.getLogger("asyncio").setLevel(logging.INFO)

    bot = RedStar(base_dir=default_user_dir, debug=args.verbose, config_path=args.config / "config" / "config.json")
    task = loop.create_task(bot.start(bot.config["token"]))
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        bot.logger.info("Interrupt caught, shutting down...")
    except SystemExit:
        pass
    finally:
        pending = asyncio.Task.all_tasks()
        for task in pending:
            task.cancel()
        bot.logger.info("Exiting...")
        loop.close()
