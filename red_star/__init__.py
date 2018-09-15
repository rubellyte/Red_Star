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

    parser = ArgumentParser(description="General-purpose Discord bot with administration and entertainment functions.")
    parser.add_argument("-v", "--verbose", "--debug", action="count", default=0,
                        help="Enables debug output. Calling multiple times increases verbosity; two calls enables "
                             "discord.py debug output, and three calls enables asyncio's debug mode.")
    conf_path_group = parser.add_mutually_exclusive_group()
    conf_path_group.add_argument("-d", "--directory", type=Path, default=default_user_dir,
                                 help="Sets the directory in which configs, logs, and data will be stored.")
    conf_path_group.add_argument("-p", "--portable", action="store_true",
                                 help="Runs Red Star in portable mode. In portable mode, data files will be stored "
                                      "in the installation directory.")
    parser.add_argument("-l", "--logfile", type=str, default="red_star.log", help="Sets the name of the log file.")
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

    storage_dir = Path.cwd() if args.portable else args.directory

    if not storage_dir.exists():
        base_logger.warning(f"Specified config directory {storage_dir} does not exist! Creating now...")
        config_folder = args.config / "config"
        config_folder.mkdir(parents=True)
        plugins_folder = args.config / "plugins"
        plugins_folder.mkdir(parents=True)
        plugin_init = plugins_folder / "__init__.py"
        plugin_init.touch()

    logfile = storage_dir / args.logfile
    if not logfile.exists():
        logfile.touch()

    file_logger = RotatingFileHandler(logfile, maxBytes=1048576, backupCount=5, encoding="utf-8")
    file_logger.setLevel(loglevel)
    file_logger.setFormatter(formatter)
    base_logger.addHandler(file_logger)

    loop = asyncio.get_event_loop()

    if args.verbose >= 3:
        loop.set_debug(True)
        logging.getLogger("asyncio").setLevel(logging.DEBUG)
    else:
        logging.getLogger("asyncio").setLevel(logging.INFO)

    bot = RedStar(storage_dir=storage_dir, debug=args.verbose)
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
