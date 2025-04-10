"""A class for managing data collection tasks"""
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import warnings

import epics.ca
import numpy as np
import pandas as pd
from mysql.connector import PoolError
from mysql.connector.pooling import MySQLConnectionPool, PooledMySQLConnection
from rfscopedb.data_model import Scan

from .cavity import Cavity


# pylint: disable=too-many-instance-attributes
class DaqThread(threading.Thread):
    """A class that manages collecting and storing data for a single cavity."""

    # pylint: disable=too-many-arguments
    def __init__(self, *, exit_event: threading.Event, epics_name: str, out_dir: Path, signals: List[str],
                 duration: float, db_pool: Optional[MySQLConnectionPool], output: str,
                 meta_pvs: List[str] = None):
        """Create a thread that will collect and store data for a single cavity.

        This job will cycle for duration minutes.  

        Args:
            epics_name: The EPICSName of the cavity to collect data for
            out_dir: The base directory to store data in.  If None, no data will be written to disk
            signals: The name of the signals to collect data for. ("GMES", "PMES", etc.).  The exact PV name for the
              signals will be automatically constructed later.
            duration: How long in minutes to collect data for this cavity.
            db_pool: The connection pool for the waveform database.
            output: 'db': Write to database.  'file': Write to file
        """

        super().__init__()
        self.epics_name = epics_name
        self.out_dir = out_dir
        self.signals = signals
        self.duration = duration
        self.db_pool = db_pool
        self.output = output
        self.exit_event = exit_event
        self.errors = []

        # Construct all of the metadata PVs
        self.meta_pvs = []
        for pv in meta_pvs:
            self.meta_pvs.append(epics.PV(pv))

        self.cavity = Cavity(epics_name=self.epics_name, waveform_signals=self.signals)

        # Wait for connections after Cavity call as these may have already connected in the background.
        for pv in self.meta_pvs:
            pv.wait_for_connection()

        # Track samples that worked/failed
        self.n_success = 0
        self.n_attempts = 0

    def run(self):
        """Collect and store data for a single cavity.  This job will cycle for self.duration minutes.  
        """

        try:
            # Use the context initialized in the main thread
            epics.ca.use_initial_context()

            # We want all warnings to be raised as exceptions
            np.seterr(all='raise')
            with warnings.catch_warnings():
                warnings.simplefilter("error")

                try:
                    # Put the cavity into the desired scope mode.  Make sure to return it to old mode when done.
                    self.cavity.setup_scope()

                    current_time = datetime.now()
                    stop_time = current_time + timedelta(seconds=self.duration * 60)

                    # grab sample rate (time_ms)
                    time_ms_stamp = self.cavity.sample_interval.get()

                    if time_ms_stamp is None:
                        raise RuntimeError(f"Error setting time_ms_stamp for: '{self.epics_name}")
                    while current_time < stop_time:
                        if self.exit_event.is_set():
                            print(f"{self.epics_name}: Exiting early")
                            break

                        try:
                            # Recheck the scope is in the desired mode before every download.  Useful for long runs.
                            self.cavity.setup_scope()

                            # Wait until CEBAF and cavity is in a stable state or it is time to stop collecting.
                            skip_loop = False
                            while not self.cavity.is_state_valid():
                                time.sleep(0.05)
                                if (datetime.now() > stop_time) or self.exit_event.is_set():
                                    skip_loop = True
                                    break
                            if skip_loop:
                                continue

                            # Here goes the actual data collection
                            self.n_attempts += 1

                            # Get the waveform data and the closest estimate for the waveforms' location in absolute
                            # time.
                            results_dict, start, end = self.cavity.get_waveforms()

                            float_meta, string_meta = self.get_meta_data()
                            if self.output == "db":
                                self.write_to_db(start_time=start, end_time=end,
                                                 data_dict=results_dict, float_meta=float_meta, string_meta=string_meta,
                                                 sampling_rate=1.0 / time_ms_stamp)
                            elif self.output == "file":
                                self.write_files(results=results_dict, start_time=start, end_time=end,
                                                 f_metadata=float_meta, s_metadata=string_meta)

                            self.n_success += 1
                        # Broad exception since any problem needs to be swallowed and collection retried within the
                        # thread.
                        # pylint: disable=broad-exception-caught
                        except Exception as exc:
                            self.errors.append(exc)
                        finally:
                            # Sleep a little bit so we don't eat up CPU needlessly.
                            time.sleep(0.025)
                            current_time = datetime.now()
                finally:
                    # Put the scope back in its original settings.
                    self.cavity.return_scope()

        # Failure report should be emailed if we experienced many errors or no attempts were made (this case is the
        # likely one here).
        # pylint: disable=broad-exception-caught
        except Exception as exc:
            self.errors.append(exc)

    def get_connection_with_retry(self, max_retries=10, wait_time=0.1) -> PooledMySQLConnection:
        """Attempts to get a connection from the pool, waiting if necessary.

        We may use a small pool so waiting might be necessary. This could be run across the entire linac and saturate
        the database server.
        """

        conn = None
        if max_retries <= 0:
            raise ValueError("Must try at least once to get the connection.")

        for attempt in range(max_retries):
            try:
                conn = self.db_pool.get_connection()  # Try to get a connection
                break
            except PoolError:
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise
        return conn

    def get_meta_data(self) -> Tuple[Dict[str, float], Dict[str, str]]:
        """Query the CEBAF state via a set of PVs.

        Returns:
            Dictionary of PV names to float values, dictionary of PV names to string values.
        """
        if self.meta_pvs is None:
            return {}, {}

        # Get the PVS, then split them into the different types.  Should be fast since the value is updated by the
        # automonitor and the PV was connected at the start.
        vals = {}
        for pv in self.meta_pvs:
            vals[pv.pvname] = pv.get()

        f_metadata = {}
        s_metadata = {}
        for pv, val in zip(self.meta_pvs, vals):
            if isinstance(val, float):
                f_metadata[pv.pvname] = val
            elif isinstance(val, int):
                f_metadata[pv.pvname] = float(val)
            else:
                s_metadata[pv.pvname] = str(val)

        return f_metadata, s_metadata

    def write_files(self, *, results: Dict[str, np.ndarray], start_time: datetime, end_time: datetime,
                    f_metadata: Dict[str, float], s_metadata: Dict[str, str]):
        """Write data to standardized TSV file."""
        tsv_file, cavity_dir = self.get_cavity_filepath(start_time=start_time, end_time=end_time)
        cavity_dir.mkdir(parents=True, exist_ok=True)

        # Convert the data to a more friendly format and generate a timestamp column
        df = pd.DataFrame(results).astype(float)
        df.insert(0, 'Time', self.generate_time_column(wf_length=df.shape[0]))
        df['Time'] = df['Time'].astype(str)

        with open(tsv_file, 'w', encoding="utf-8") as f:
            if f_metadata is not None:
                for key, val in f_metadata.items():
                    f.write(f"# {key}\t{val}\n")
            if s_metadata is not None:
                for key, val in s_metadata.items():
                    f.write(f"# {key}\t\"{val}\"\n")
        df.to_csv(str(tsv_file), mode='a', sep='\t', index=None, float_format="%.5e", lineterminator='\n')

    def generate_time_column(self, wf_length: int):
        """Generate a list for the time column in data files.  [0, ..., (wf_length-1) * sample_interval]

        Args:
            wf_length: Length of the time column.
        """
        # pandas seems to specify an ndarray as acceptable, but not list
        return np.array([self.cavity.sample_interval.get() * i for i in range(wf_length)])

    def get_cavity_filepath(self, start_time: datetime, end_time: datetime) -> Path:
        """Generate the full path to the cavity file.

        Args:
            start_time: Start time of the scan
            end_time: End time of the scan
        """
        cav = self.epics_name[0:4]
        cavity_dir = self.out_dir.joinpath(cav)

        s_str = start_time.strftime("%Y_%m_%d_%H-%M-%S-%f")
        e_str = end_time.strftime("%Y_%m_%d_%H-%M-%S-%f")
        tsv_file = cavity_dir.joinpath(f"{cav}WFS_{s_str}_{e_str}.tsv")

        return tsv_file, cavity_dir

    def write_to_db(self, *, start_time, end_time, data_dict, float_meta, string_meta, sampling_rate):
        """Write data to the scope waveform database

        Args:
            start_time: start time of the waveform data collection
            end_time: end time of the waveform data collection
            data_dict: dictionary of waveform names to values
            float_meta: dictionary of scan metadata, names to float value mapping
            string_meta: dictionary of scan metadata, names to string value mapping
            sampling_rate: sampling rate in Hz
        """
        scan = Scan(start=start_time, end=end_time)
        scan.add_scan_data(float_data=float_meta, str_data=string_meta)
        scan.add_cavity_data(cavity=self.epics_name, data=data_dict, sampling_rate=sampling_rate)
        conn = None
        try:
            conn = self.get_connection_with_retry()
            scan.insert_data(conn=conn)
        finally:
            if conn is not None:
                conn.close()
