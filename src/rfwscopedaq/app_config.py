"""A module for managing application configuration in a thread-safe manner."""
import threading
import os
import logging
from typing import Any, List, Union
from functools import reduce
import operator

import yaml

logger = logging.getLogger(__name__)

# The root directory of the app.  Commented out version is root if not in csue
# app_root = os.path.realpath(os.path.join(os.path.basename(__file__), ".."))
# app_root = os.path.realpath(os.path.join(os.path.dirname(__file__),
#                                          "..", "..", "..", ".."))
# Launcher scripts should set this.
app_root = os.environ.get('APP_ROOT')

# CSUE variables - challenging to use these if not using CSUE templates.
# Instead, use a relative path to identify the root directory for this version.
CSUE_APP_PATH = app_root
CSUE_LOG_DIR = f"{CSUE_APP_PATH}/fileio/log"
CSUE_CONFIG_DIR = f"{CSUE_APP_PATH}/fileio/config"

# The configuration dictionary for the application
_CONFIG = {}

# Lock for accessing configuration
_CONFIG_LOCK = threading.Lock()


def _get_from_dict(d: dict, key_list: list):
    """Query a value from a nested dictionary using a list of keys."""
    return reduce(operator.getitem, key_list, d)


def _set_in_dict(d: dict, key_list: list, value: Any):
    """Set a values from a nested dictionary using a list of keys."""
    _get_from_dict(d, key_list[:-1])[key_list[-1]] = value


def parse_config_file(filename: str = f"{app_root}/cfg.yaml"):
    """Process an application level configuration file

    Args:
        filename:  The name of the file parse
    """
    # pylint: disable=global-variable-not-assigned
    global _CONFIG, _CONFIG_LOCK
    with _CONFIG_LOCK:
        try:
            with open(filename, mode="r", encoding="utf-8") as f:
                _CONFIG = yaml.safe_load(f)

        except yaml.YAMLError as exc:
            # Print out the portion of config file near the error.
            if hasattr(exc, 'problem_mark'):
                line = exc.problem_mark.line + 1
                column = exc.problem_mark.column
                logger.error("Error parsing %s near line %s column %s", filename, line, column)
            else:
                logger.error("Error parsing config: %s", exc)
            raise

        except Exception as exc:
            logger.error("Error reading file %s': %s", filename, exc)
            raise exc


def clear_config():
    """Clear the configuration"""
    # pylint: disable=global-variable-not-assigned
    global _CONFIG, _CONFIG_LOCK
    with _CONFIG_LOCK:
        _CONFIG = {}


def set_parameter(key: Union[str, List[str]], value: Any):
    """Set an individual _CONFIG parameter.  Thread safe.

    Note: This class doesn't currently support saving config files to disk, but any value set here would need to be
    json serializable if that functionality is desired.

    Args:
        key:  A string for top level parameter.  A list of strings where each string is key on the path to the desired
            parameter.  Example key = ["db_config", "user"] would query _CONFIG["db_config"]["user"], while
            key = "db_config" would query _CONFIG["db_config"].
        value:  The value to set.  Can be any object.
    """
    # pylint: disable=global-variable-not-assigned
    global _CONFIG, _CONFIG_LOCK
    with _CONFIG_LOCK:
        if isinstance(key, str):
            _CONFIG[key] = value
        elif len(key) == 1:
            _CONFIG[key[0]] = value
        else:
            _get_parameter(key[:-1])[key[-1]] = value


def get_parameter(key: Union[str, List[str], None]) -> Any:
    """Set an individual _CONFIG parameter.  If key is None, return entire dictionary.  Thread safe.

    Args:
        key:  A string for top level parameter.  A list of strings where each string is key on the path to the desired
            parameter.  Example key = ["db_config", "user"] would query _CONFIG["db_config"]["user"], while
            key = "db_config" would query _CONFIG["db_config"].
    """
    # pylint: disable=global-variable-not-assigned
    global _CONFIG_LOCK
    with _CONFIG_LOCK:
        return _get_parameter(key)


def _get_parameter(key: Union[str, List[str], None]) -> Any:
    """Set an individual config parameter.  If key is None, return entire dictionary.  Not thread safe, internal use."""
    # pylint: disable=global-variable-not-assigned
    global _CONFIG, _CONFIG_LOCK
    out = None
    try:
        if key is None:
            out = _CONFIG
        elif isinstance(key, str):
            out = _CONFIG[key]
        else:
            out = _get_from_dict(_CONFIG, key)
    except KeyError:
        # It's OK to request a parameter that doesn't exist, you get None back
        pass

    return out


def validate_config():
    """Make sure that a handful of required _CONFIG settings are present and of correct type."""
    # pylint: disable=global-variable-not-assigned
    global _CONFIG, _CONFIG_LOCK
    required = [
        ('signals', list),
        ('meta_pvs', list),
        ('base_dir', str),
        ('email', dict),
        ('failure_threshold', float),
        ('db_config', dict),
        ('min_beam_current', float)
    ]

    with _CONFIG_LOCK:
        for entry in required:
            (key, typ) = entry
            if key not in _CONFIG.keys():
                raise ValueError(f"Configuration is missing '{key}")
            # Check that all of these are floats / numbers
            if not isinstance(_CONFIG[key], typ):
                logger.error("Required config parameter '%s' is not required type '%s'."
                             "  Received '%s' of type '%s'", key, typ, _CONFIG[key], type(_CONFIG[key]))
                logger.error("_CONFIG = %s", _CONFIG)
                raise ValueError(f"Required config parameter '{key}' is not required type '{typ}'."
                                 f"  Received '{_CONFIG[key]}' of type '{type(_CONFIG[key])}'")
