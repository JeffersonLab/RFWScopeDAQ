"""A module for managing the entry point to the application"""
import copy
import signal
import threading
from pathlib import Path
import shutil
import argparse
from datetime import datetime
import re
from typing import List, Tuple

from mysql.connector.conversion import MySQLConverter
from mysql.connector.pooling import MySQLConnectionPool
import epics

from .collect_data import DaqThread
from . import app_config as cfg
from . import __version__
from .email_sender import EmailSender

# SET NP TO PRINT OUT ENTIRE WAVEFORM ARRAY
# np.set_printoptions(threshold=sys.maxsize)


# Signal all threads to exit
EXIT_EVENT = threading.Event()


class NumpyConverterClass(MySQLConverter):
    """Class for converting numpy numeric types to those supported by mysql-connector-python."""

    @staticmethod
    def _float32_to_mysql(value):
        return float(value)

    @staticmethod
    def _float64_to_mysql(value):
        return float(value)

    @staticmethod
    def _int32_to_mysql(value):
        return int(value)

    @staticmethod
    def _int64_to_mysql(value):
        return int(value)


# unsure of all the arguments that will be passed when a signal is received, but we don't use any
# pylint: disable=unused-argument
def handler(*args, **kwargs):
    """Signal handler that notifies any threads watching the EXIT_EVENT that it's time to exit."""
    # pylint: disable=global-variable-not-assigned
    global EXIT_EVENT
    EXIT_EVENT.set()


def process_cavities(cavities, out_dir, output: str):
    """Collect data from the specified cavities.

    Args:
        cavities: List of cavities to collect data from
        out_dir: Directory to write output to if file output requested
        output: Where to store data
    """

    # Initialize EPICS context that will be used by worker threads
    epics.ca.create_context()

    # Define handlers for common 'exit now' signals
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    # Use a pool with a small number of connections.  First because the pool handles thready safety where a single
    # connection does not.  Second, becuase if we used a larger pool size and launched this script once per zone, then
    # we could exhaust the number of connections on the database (often ~150).
    pool = None
    pool_size = 1 if len(cavities) == 1 else cfg.get_parameter(['db_config', 'pool_size'])
    if output == "db":
        db_config = copy.deepcopy(cfg.get_parameter('db_config'))
        del db_config['pool_size']
        pool = MySQLConnectionPool(pool_name="scope-pool", pool_size=pool_size, pool_reset_session=True,
                                   converter_class=NumpyConverterClass, **db_config)

    threads = []
    for cavity in cavities:
        threads.append(DaqThread(exit_event=EXIT_EVENT, epics_name=cavity, duration=cfg.get_parameter('duration'),
                                 out_dir=out_dir, signals=cfg.get_parameter('signals'),
                                 db_pool=pool, output=output, meta_pvs=cfg.get_parameter('meta_pvs')))

    # Kick off the threads
    for thread in threads:
        thread.start()

    # Wait for the threads to join.
    for thread in threads:
        # Python join is a blocking operation even for signals.  Solution is to set a timeout in a loop, and keep
        # joining as long as the thread is still alive.  This gives the signals a chance to be handled once every
        # second. Alternative would be to check is_alive() with a sleep.
        while thread.is_alive():
            thread.join(timeout=0.1)

    send_failure_report(threads=threads)


def send_failure_report(threads: List[DaqThread]):
    """Send an email summarizing DAQ performance if there were sufficient problems to require attention.

    If no email config no to_addrs are available in the application configuraiton, then no email will be sent.

    Args:
        threads: The set of threads that have performed data collection.
    """

    # Check if we can send an email
    if (cfg.get_parameter('email') is None) or (len(cfg.get_parameter(['email', 'to_addrs'])) == 0):
        return

    max_fail_percent = 0.0
    for thread in threads:
        if thread.n_attempts == 0:
            max_fail_percent = 1.0
            break

        # Calculate the current failure percentage and compare against current max.
        max_fail_percent = max(max_fail_percent, 1.0 - float(thread.n_success) / thread.n_attempts)

    if max_fail_percent >= cfg.get_parameter('failure_threshold'):
        mailer = EmailSender(subject="RFWScopeDAQ Failure Report", toaddrs=cfg.get_parameter(['email', 'to_addrs']),
                             fromaddr=cfg.get_parameter(['email', 'from_addr']))
        msg = f"Failure report for run ending at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        for thread in threads:
            msg += f"{thread.epics_name}: {thread.n_success} / {thread.n_attempts} attempts succeeded\n"
            for error in thread.errors:
                msg += f"  {error}\n"
            msg += "\n"

        mailer.send_txt_email(msg)


def validate_cavity(cavity: str):
    """Check if the cavity name is valid.  Raise exception if not.

    Args:
        cavity: Cavity name to validate
    """

    valid_linacs = "012"
    valid_zones = "23456789ABCDEFGHIJKLMNOPQ"
    valid_cavities = "12345678"

    if not re.match(r"R\d\w\d$", cavity):
        raise ValueError("Invalid cavity name.  Use EPICSName format ('R1M1').")
    if cavity[1] not in valid_linacs:
        raise ValueError("Invalid linac number.  Only use 0=Inj, 1=NL, or 2=SL.")

    if cavity[0] == "1":
        valid_zones = "234"

    if cavity[2] not in valid_zones:
        raise ValueError(f"Invalid zone.  Options for that linac are {valid_zones}.")

    if cavity[1] == "0" and cavity[2] == '2':
        valid_cavities = '78'
    if cavity[3] not in valid_cavities:
        raise ValueError("Invalid cavity number.")


def validate_zone(zone: str):
    """Check if the zone name is valid.  Raise exception if not.

    Args:
        zone: Zone name to validate
    """

    valid_linacs = "012"
    valid_zones = "23456789ABCDEFGHIJKLMNOPQ"

    if not re.match(r"R\d\w$", zone):
        raise ValueError("Invalid zone name.  Use EPICSName format ('R1M')")
    if zone[1] not in valid_linacs:
        raise ValueError("Invalid linac number.  Only use 0=Inj, 1=NL, or 2=SL")

    if zone[1] == "0":
        valid_zones = "234"

    if zone[2] not in valid_zones:
        raise ValueError(f"Invalid zone.  Options for that linac are {valid_zones}")


def check_and_alert_free_storage(check_dir):
    """Check that we have sufficient storage to take more data.

    Args:
        check_dir: Directory to check for free storage
    """
    free_gb = shutil.disk_usage(check_dir).free / (1024 ** 3)
    if free_gb < cfg.get_parameter("min_free_space"):
        msg = f"Error: insufficient free space in {check_dir}.  {free_gb} GB < {cfg.get_parameter('min_free_space')}" \
              " GB."
        # Only print a message if no email is configured
        if (cfg.get_parameter("email") is None) or (len(cfg.get_parameter(['email', 'to_addrs'])) == 0):
            print(msg)
        else:
            sender = EmailSender(subject="RFWScopeDAQ: Insufficient free space",
                                 fromaddr=cfg.get_parameter(["email", 'from_addr']),
                                 toaddrs=cfg.get_parameter(["email", 'to_addrs']), )
            sender.send_txt_email(msg)
        return 1
    return 0


def process_args_and_cfg(args: argparse.Namespace) -> Tuple[List[str], Path]:
    """Process command line args and config file.  Update cfg as necessary.
    Args:
        args: Command line arguments
    """
    # Default value is set in app_config
    cfg.parse_config_file(args.file)

    # Update configuration
    if args.duration:
        cfg.set_parameter("duration", args.duration)
    if args.email is not None:
        cfg.set_parameter(["email", "to_addrs"], args.email)
    if args.no_email:
        cfg.set_parameter("email", None)
    if args.dir:
        cfg.set_parameter('base_dir', args.dir)

    base_dir = Path(cfg.get_parameter("base_dir"))
    app_start = datetime.now().strftime("%Y_%m_%d")
    cavities = []
    if args.cavity is not None:
        out_dir = base_dir.joinpath(app_start, args.cavity[:-1])
        cavities.append(args.cavity)
    elif args.zone is not None:
        validate_zone(args.zone)
        out_dir = base_dir.joinpath(app_start, args.zone)
        for i in range(1, 9):
            cavities.append(f"{args.zone}{i}")
    else:
        raise ValueError("Cavity or Zone must be supplied to CLI.")

    for cavity in cavities:
        validate_cavity(cavity)

    # Make sure that we have all the configuration we need fully setup
    cfg.validate_config()

    return cavities, out_dir


def main():
    """This should be used as the entry point for the application."""
    try:
        # Setup parser.  You can target either a cavity or a zone.  Secondary check is
        # required to make sure that the user hasn't blocked all output of results.
        parser = argparse.ArgumentParser(prog="RFWScopeDAQ",
                                         description="Collect waveform data to teach AI model.  Most settings are in "
                                                     "cfg.json")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("-z", "--zone", type=str,
                           help="EPICS name of a zone to check.  E.g. R1M")
        group.add_argument("-c", "--cavity", type=str,
                           help="EPICS name of cavity to check.  E.g., R1M1")
        parser.add_argument("-q", "--quiet", action='store_true',
                            help="Suppresses text output")
        parser.add_argument("-t", "--duration", type=float,
                            help="How long to gather data in minutes, default = 5 minutes")
        parser.add_argument("-d", "--dir", type=str,
                            help="Base data directory to save data")
        parser.add_argument('-o', '--output', type=str, choices=["db", "file"],
                            help="Where to save data")
        parser.add_argument("-e", "--email", type=str, nargs='*',
                            help="Space separated list of email addresses to receive report failures.")
        parser.add_argument("-E", "--no-email", action='store_true',
                            help="Suppress generation of the email report")
        parser.add_argument("-f", "--file", type=str,
                            default=f"{Path(cfg.CSUE_CONFIG_DIR).joinpath('cfg.yaml')}", help="Configuration file")
        parser.add_argument("-v", "--version", action='version', version='%(prog)s ' + __version__)

        # Process CLI arguments and config file
        args = parser.parse_args()
        cavities, out_dir = process_args_and_cfg(args)

        # Check that we have sufficient free storage.  Exit if not.
        if args.output == "db":
            check_dir = cfg.get_parameter("db_data_partition")
        elif args.output == "file":
            check_dir = cfg.get_parameter('base_dir')
        else:
            raise ValueError(f"Unsupported output {args.output}")
        if check_and_alert_free_storage(check_dir):
            return 1

        # Go get the data
        process_cavities(cavities=cavities, out_dir=out_dir, output=args.output)

    # I want to give a friendly error message for any likely errors and not a massive stack trace.
    # pylint: disable=broad-exception-caught
    except Exception as e:
        print("Error:", e)
        return 1

    return 0
