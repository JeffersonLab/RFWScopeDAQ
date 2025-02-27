import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple

import epics.ca
import numpy as np
import pandas as pd
import warnings

from mysql.connector.pooling import MySQLConnectionPool
from rfscopedb.data_model import Scan

from .cavity import Cavity

class DaqThread(threading.Thread):
	"""A class that manages collecting and storing data for a single cavity."""

	def __init__(self, exit_event: threading.Event, epics_name: str, out_dir: Path, signals: List[str], duration: int,
				 timeout: float, db_pool: MySQLConnectionPool, output: str, meta_pvs: List[str] = None):
		"""Create a thread that will collect and store data for a single cavity.

		This job will cycle for duration minutes.  Each cycle will wait at most timeout seconds for the cavity to
		achieve stable operations before starting a new cycle.

		Args:
			epics_name: The EPICSName of the cavity to collect data for
			out_dir: The base directory to store data in.  If None, no data will be written to disk
			signals: The name of the signals to collect data for. ("GMES", "PMES", etc.).  The exact PV name for the
			  signals will be automatically constructed later.
			duration: How long in minutes to collect data for this cavity.
			timeout: How long to wait for this cavity to finish.
			db_pool: The connection pool for the waveform database.
			output: 'db': Write to database.  'file': Write to file
		"""

		super().__init__()
		self.epics_name = epics_name
		self.out_dir = out_dir
		self.signals = signals
		self.duration = duration
		self.timeout = timeout
		self.db_pool = db_pool
		self.output = output
		self.exit_event = exit_event
		self.meta_pvs = meta_pvs
		self.cavity = Cavity(epics_name=self.epics_name, waveform_signals=self.signals)

		# Track samples that worked/failed
		self.n_success = 0
		self.n_attempts = 0


	def run(self):
		"""Collect and store data for a single cavity.

		This job will cycle for self.duration minutes.  Each cycle will wait at most timeout seconds for the cavity to
		achieve stable operations before starting a new cycle.
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
						self.n_attempts += 1
						if self.exit_event.is_set():
							print(f"{self.epics_name}: Exiting early")
							break

						error = ""
						try:
							# Recheck the scope is in the desired mode before every download.  Useful for long runs.
							self.cavity.setup_scope()

							# Wait until there is no trip.  After timeout seconds, drop the sample, and retry if time allows
							start = datetime.now()
							while not self.cavity.is_stable_running():
								time.sleep(1)
								if (datetime.now() - start).total_seconds() > self.timeout:
									raise RuntimeError(f"{self.epics_name}: {start.strftime('%Y-%m-%d %H:%M:%S')} "
													   "sample timed out waiting for stable running")

							# Get the waveform data and the closest estimate for the waveforms' location in absolute time.
							results_dict, start, end = self.cavity.get_waveforms()

							float_meta, string_meta = self.get_meta_data()
							if self.output == "db":
								try:
									conn = self.db_pool.get_connection()
									self.write_to_db(start_time=start, end_time=end,
												data_dict=results_dict, float_meta=float_meta, string_meta=string_meta,
												conn=conn, sampling_rate=(1.0 / time_ms_stamp))
								finally:
									conn.close()
							elif self.output == "file":
								self.write_files(results=results_dict, start_time=start, end_time=end,
												 f_metadata=float_meta, s_metadata=string_meta)

							self.n_success += 1
						except Exception as e:
							# Not sure what to do with exceptions here.  At most we want to log them.
							traceback.print_exc()
							pass
						finally:
							# Sleep a little bit so we don't eat up CPU needlessly.
							time.sleep(0.025)
							current_time = datetime.now()
				finally:
					# Put the scope back in it's original settings.
					self.cavity.return_scope()

		except Exception as exc:
			print(f"Errored out: {repr(exc)}")
			traceback.print_exc()

	def get_meta_data(self) -> Tuple[Dict[str, float], Dict[str, str]]:
		"""Query the CEBAF state via a set of PVs.  Return a """
		if self.meta_pvs is None:
			return {}, {}

		vals = epics.caget_many(self.meta_pvs)
		f_metadata = {}
		s_metadata = {}
		for pv, val in zip(self.meta_pvs, vals):
			if isinstance(val, float):
				f_metadata[pv] = val
			else:
				s_metadata[pv] = val

		return f_metadata, s_metadata

	def write_files(self, results: Dict[str, np.ndarray], start_time: datetime, end_time: datetime,
					f_metadata: Dict[str, float], s_metadata: Dict[str, str]):
		"""Write data to standardized TSV file."""
		cav = self.epics_name[0:4]
		cavity_dir = self.out_dir.joinpath(cav)
		time_ms_stamp = self.cavity.sample_interval.get()

		# Convert the data to a more friendly format and generate a timestamp column
		df = pd.DataFrame(results).astype(float)
		wf_len = df.shape[0]
		df.insert(0, 'Time', np.array([time_ms_stamp * i for i in range(wf_len)]))
		df['Time'] = df['Time'].astype(str)

		s_str = start_time.strftime("%Y_%m_%d_%H-%M-%S-%f")
		e_str = end_time.strftime("%Y_%m_%d_%H-%M-%S-%f")

		tsv_file = cavity_dir.joinpath(f"{cav}WFS_{s_str}_{e_str}.tsv")
		cavity_dir.mkdir(parents=True, exist_ok=True)

		with open(tsv_file, 'w') as f:
			if f_metadata is not None:
				for key, val in f_metadata.items():
					f.write(f"# {key}\t{val}\n")
			if s_metadata is not None:
				for key, val in s_metadata.items():
					f.write(f"# {key}\t\"{val}\"\n")
		df.to_csv(tsv_file, mode='a', sep='\t', index=None, float_format="%.5e", lineterminator='\n')

	# TODO: Add end_time to rfscopedb and database
	def write_to_db(self, start_time, end_time, data_dict, float_meta, string_meta, conn, sampling_rate):
		"""Write data to the scope waveform database"""
		scan = Scan(dt=start_time)
		scan.add_scan_data(float_data=float_meta, str_data=string_meta)
		scan.add_cavity_data(cavity=self.epics_name, data=data_dict, sampling_rate=sampling_rate)
		scan.insert_data(conn=conn)
