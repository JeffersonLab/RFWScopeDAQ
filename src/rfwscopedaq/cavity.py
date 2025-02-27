import time
from contextlib import contextmanager
import threading
from datetime import datetime
import math
from typing import Any, Dict, Tuple

import epics
import numpy as np


class Cavity:

    def _data_ready_cb(self, pvname=None, value=None, char_value=None, timestamp=None, **kwargs):
        """This callback should only be used to monitor the R...STAT2b.B3 PV to see when the FCC has updated data."""

        with self.data_ready_lock:
            # Start of data taking phase for the FPGA and other pauses
            if value == 128:
                # FPGA has finished reading data.  Now time to transfer to IOC.  Waveform records will be in
                # an inconsistent state until the step is done.
                self.first_time = True
            elif value == 256 and self.first_time:
                self.data_ready = False
                self.window_start = timestamp
            # We've read all the waveforms into EPICS records and are calculating statistics.
            elif value == 512 and self.first_time:
                self.window_end = timestamp
                self.data_ready = True

    def _connection_cb(self, pvname=None, conn=None):
        """Callback used to track connection status for cavity PVs in a single data structure."""
        with self.pv_conn_lock:
            self.pv_conns[pvname] = conn

    def pvs_connected(self):
        """Are all PVs currently connected."""
        all_connected = False
        with self.pv_conn_lock:
            if len(self.pv_conns.keys()) > 0:
                all_connected = all(self.pv_conns.values())
        return all_connected

    def __init__(self, epics_name, waveform_signals):
        """Initialize a Cavity object and connect to it's PVs.  Exception raised if unable to connect."""
        self.epics_name = epics_name

        # Track that we are not catching the scope state machine mid-cycle
        self.first_time = False

        # Structure for tracking connection status.  It's probable that pyepics has something like this built-in.
        self.pv_conns = {}
        self.pv_conn_lock = threading.Lock()
        self.pvs = []

        # Cavity status PVs
        # self.rf_on = epics.PV(f"{epics_name}RFONr", connection_callback=self._connection_cb)  # Is the cavity RF on
        self.rf_on = epics.PV(f"{epics_name}RFONr")  # Is the cavity RF on
        self.pvs.append(self.rf_on)
        # self.stat1 = epics.PV(f"{epics_name}STAT1", connection_callback=self._connection_cb)  # Is the cavity currently ramping gradient
        self.stat1 = epics.PV(f"{epics_name}STAT1")  # Is the cavity currently ramping gradient
        self.pvs.append(self.stat1)
        # self.cntl2mode = epics.PV(f"{epics_name}CNTL2MODE", connection_callback=self._connection_cb)  # The RF control mode. 4 or 64 == stable operations)
        self.cntl2mode = epics.PV(f"{epics_name}CNTL2MODE")  # The RF control mode. 4 or 64 == stable operations)
        self.pvs.append(self.cntl2mode)

        # Data PVs
        self.waveform_pvs = {}
        for signal in waveform_signals:
            # self.waveform_pvs[epics_name+"WF"+signal] = epics.PV(epics_name+"WF"+signal, auto_monitor=False, connection_callback=self._connection_cb)
            self.waveform_pvs[epics_name + signal] = epics.PV(epics_name + signal, auto_monitor=False)
            self.pvs.append(self.waveform_pvs[epics_name + signal])

        # Control the waveform mode.  Not sure why we have two separate PVs, but this is the API.
        # -1 = User requested stop, 0 = Is Stopped, 1 = single, 2 = run, 3 = periodic, others also exist.
        # self.scope_setting = epics.PV(f"{epics_name}WFSCOPrun", connection_callback=self._connection_cb)  
        self.scope_setting = epics.PV(f"{epics_name}WFSCOPrun")
        self.pvs.append(self.scope_setting)

        # Notification flags for OPS
        # 1 - zone in maintenance
        # 0 - normal operation
        # self.system_status = epics.PV(f"{epics_name}XSystemStatus")
        # self.pvs.append(self.system_status)
        # # message string to appear on screens?
        # self.system_status = epics.PV(f"{epics_name}XSystemUser")
        # self.pvs.append(self.system_status)

        # Change Periodic Delay to 0.1 secs.  Typical default is 1, Don't go lower than 0.1.  This is a pause that
        # happens somewhere during the data collection cycle.
        # self.periodic_setting = epics.PV(f"{epics_name}WFSCOPper", connection_callback=self._connection_cb)
        self.periodic_setting = epics.PV(f"{epics_name}WFSCOPper")
        self.pvs.append(self.periodic_setting)

        # Sample interval within a waveform
        # self.sample_interval = epics.PV(f"{epics_name}TRGS1", connection_callback=self._connection_cb)
        self.sample_interval = epics.PV(f"{epics_name}TRGS1")
        self.pvs.append(self.sample_interval)

        # Controls skipping waveform statistic calculations
        # self.wf_debug = epics.PV(f"{epics_name}WFSdebug1", connection_callback=self._connection_cb)
        self.wf_debug = epics.PV(f"{epics_name}WFSdebug1")
        self.pvs.append(self.wf_debug)

        # Waveform collection trigger delay - used in harvester, but not sure if it has impact here.
        # self.trigger_delay = epics.PV(f"{epics_name}TRGD1", connection_callback=self._connection_cb)
        self.trigger_delay = epics.PV(f"{epics_name}TRGD1")
        self.pvs.append(self.trigger_delay)

        # New Firmware has new sequencer state PV - the states that matter are these values. 
        # Waveforms are ready upon entering 512.
        # 1   -  1. Button (initial state)
        # 128 -  8. Run 3 Setup & Timing
        # 256 -  9. Run 3 Read WFs
        # 512 - 10. Run 3 Calc
        # self.scope_seq_step = epics.PV(f"{epics_name}WFSCOPstp", form='time', callback=self._data_ready_cb, connection_callback=self._connection_cb)
        self.scope_seq_step = epics.PV(f"{epics_name}WFSCOPstp", form='time', callback=self._data_ready_cb)
        self.pvs.append(self.scope_seq_step)
        # self.scope_reached_read_step = False  # Is the sequencer currently at or past the read step (2048) this cycle.

        # New firmware includes string PVs that track the time the fpga was reading data
        # self.fpga_start_PV = epics.PV(f"{epics_name}WFSharvTake", connection_callback=self._connection_cb)
        self.fpga_start_PV = epics.PV(f"{epics_name}WFSharvTake")
        self.pvs.append(self.fpga_start_PV)
        # self.fpga_end_PV = epics.PV(f"{epics_name}WFSharvDa", connection_callback=self._connection_cb)
        self.fpga_end_PV = epics.PV(f"{epics_name}WFSharvDa")
        self.pvs.append(self.fpga_end_PV)

        # The data_ready flag will be updated from callbacks and work thread.  Indicates that the data set is ready to
        # harvest.
        self.data_ready_lock = threading.Lock()
        self.data_ready = False

        # Need to monitor beam current.  User may specify a minimum beam current for data collection.
        self.beam_current = epics.PV("R2XXITOT")
        self.pvs.append(self.beam_current)

        # These will be float type timestamps indicating the acceptable start and end times of the waveforms for them
        # to be a valid set.  Access should be synchronized using data_ready_lock.
        # fpga times are when data was really collected by the FPGA
        self.fpga_start = None
        self.fpga_end = None
        # window times are when the waveform PVs should have been updated
        self.window_start = None
        self.window_end = None

        # Track connection status of the PVs
        with self.pv_conn_lock:
            for pv in self.pvs:
                # Make sure we don't set to false if the connection CB has already run.
                if pv.pvname not in self.pv_conns.keys():
                    self.pv_conns[pv.pvname] = False

        # Wait for things to connect.  If the IOC isn't available at the start, raise an exception for the worker thread
        # to handle.
        for pv in self.pvs:
            if not pv.wait_for_connection(timeout=2):
                raise RuntimeError(f"Could not connect to PV '{pv.pvname}'")

        # Track the initial state of the scope settings so that they can be returned to later
        self.init_mode = self.__get_pv(self.scope_setting)
        self.init_sample_interval = self.__get_pv(self.sample_interval)
        self.init_trigger_delay = self.__get_pv(self.trigger_delay)
        self.init_periodic_setting = self.__get_pv(self.periodic_setting)
        self.init_debug_setting = self.__get_pv(self.wf_debug)

    def get_fpga_times(self):
        """Read the timestamps for when the FPGA started and stopped collecting data."""
        fmt = "%Y-%m-%d %H:%M:%S.%f"
        self.fpga_start = datetime.strptime(self.__get_pv(self.fpga_start_PV), fmt)
        self.fpga_end = datetime.strptime(self.__get_pv(self.fpga_end_PV), fmt)

    def is_gradient_ramping(self):
        """Check if the cavity is currently ramping gradient."""
        # If the cavity is ramping is saved as the 11th bit in the
        # R...STAT1 PV
        value = self.__get_pv(self.stat1)

        # We're ramping if the bit is not 0
        is_ramping = int(value) & 0x0800 > 0

        return is_ramping

    def is_rf_on(self):
        """Check if the cavity currently has RF on."""
        value = self.__get_pv(self.rf_on)
        is_on = value == 1
        return is_on

    def is_valid_control_mode(self):
        """Check that the cavity is in a valid control mode for this measurement."""
        value = self.__get_pv(self.cntl2mode)
        valid = value == 4 or value == 64
        return valid

    def is_beam_current_sufficient(self):
        """Check that we have enough beam current present in the machine for data to be valid."""
        beam_current = self.__get_pv(self.beam_current)
        return beam_current > cfg.get_parameter("min_beam_current")

    def is_state_valid(self):
        not_ramping = not self.is_gradient_ramping()
        rf_on = self.is_rf_on()
        valid_mode = self.is_valid_control_mode()
        sufficient_beam = self.is_beam_current_sufficient()

        return all((not_ramping, rf_on, valid_mode, sufficient_beam))

    def get_waveforms(self, timeout=60, sleep_dur=0.01) -> Tuple[Dict[str, np.ndarray], datetime, datetime]:
        """Waits for the FCC to have reported data is ready, then grabs those waveforms.  Checks for valid timestamps"""
        count = 0
        while True:
            # Check that the sequencer-related PV is still connected since that is what drives this whole process.
            if not self.scope_seq_step.connected:
                print("lost connection to scope")
                raise RuntimeError(f"{self.epics_name}: Scope sequencer PV ({self.scope_seq_step.pvname}) "
                                   f"disconnected.")

            # Wait for to be ready, but timeout eventually
            with self.data_ready_lock:
                # Check if the FCC has gathered all the data we need.  Get it if so.
                if self.data_ready:
                    self.get_fpga_times()
                    self.data_ready = False

                    # Get the waveforms           
                    wf_values = {}
                    fpga_start = self.fpga_start
                    fpga_end = self.fpga_end

                    start = datetime.now()
                    for wf in self.waveform_pvs.values():
                        wf_values[wf.pvname] = (self.__get_pv(wf, use_monitor=False))

                    # Warn if total download time was too long.
                    duration = (datetime.now() - start).total_seconds()
                    if duration > 1.5:
                        print(f"{self.epics_name}: Warning.  Waveform downloads took {duration} seconds")

                    # Make sure that they look like a synchronous grouping.  These should throw if not.
                    for wf in self.waveform_pvs.values():
                        self.__pv_in_window(wf)

                    break

            # Sleep for a little bit before we check again if data is ready.
            time.sleep(sleep_dur)
            count += 1
            if count * sleep_dur > timeout:
                raise RuntimeError(f"{self.epics_name}: Timed out waiting for good data. (> {timeout}s)")

        return wf_values, fpga_start, fpga_end

    def __pv_in_window(self, pv):
        """Check that the provided timestamp is within the acquisition window.  Raise exception if not.

        Should be called within a 'data_ready_lock'ed context.  Also raises if we have an invalid window
        """
        if self.window_end < self.window_start:
            raise RuntimeError(f"{self.epics_name}: Invalid data acquisition window")
        if not self.window_start <= pv.timestamp <= self.window_end:
            raise RuntimeError(f"{self.epics_name}: {pv.pvname} timestamp ({pv.timestamp}) outside acquisition window "
                               f"({self.window_start}, {self.window_end}).")

    @staticmethod
    def __get_pv(pv, **kwargs):
        """Get the current value of the PV and raise an exception if it is None.  kwargs passed to PV.get()"""
        value = pv.get(**kwargs)
        if value is None:
            raise RuntimeError(f"Error retrieving PV value '{pv.pvname}")
        return value

    @staticmethod
    def __wait_for_pv(pv: epics.PV, value: Any, timeout: float = 5.0, delta: float = 0.005):
        """Pause execution until PV has been updated to specified value.
        
        Args:
            pv: The pv to wait for
            value: The value we want the PV to take before continuing
            timeout: Seconds to wait before raising an exception
            delta: How long to sleep between checks of PV value
        """
        start = datetime.now()
        if isinstance(value, float):
            while not math.isclose(pv.get(), value):
                time.sleep(delta)
                if (datetime.now() - start).total_seconds() >= timeout:
                    raise RuntimeError(f"Timed out waiting for {pv.pvname} == {value}")
        else:
            while pv.get() != value:
                time.sleep(delta)
                if (datetime.now() - start).total_seconds() >= timeout:
                    raise RuntimeError(f"Timed out waiting for {pv.pvname} == {value}")

    def setup_scope(self, mode=3):
        """Put the scope into the desired configuration.

        Only change the scope if necessary as a full scope system is necessary.
        """
        curr_mode = self.__get_pv(self.scope_setting)
        curr_sample_interval = self.__get_pv(self.sample_interval)
        curr_trigger_delay = self.__get_pv(self.trigger_delay)
        curr_periodic_setting = self.__get_pv(self.periodic_setting)
        curr_debug_setting = self.__get_pv(self.wf_debug)

        # These desired settings for data collection
        sample_interval = 0.2
        trigger_delay = 102.4
        periodic = 0.1
        wf_debug = 1

        # Only go through the trouble of reseting the scope system if we need to change the settings. K. Hesse
        # said that occassionally we have trouble with changing settings if a reset is not done first
        if (curr_mode != mode) or (curr_sample_interval != sample_interval) or (
                curr_trigger_delay != trigger_delay) or (curr_periodic_setting != periodic) or (
                curr_debug_setting != wf_debug):
            # We need to turn the scope mode off.  Apply our settings.  Turn it to periodic.  Unroll those changes
            # when done.
            self.scope_setting.put(-1, wait=True)
            # Particularly in development environment, this can take a long time to recover back to 0 after being reset.
            self.__wait_for_pv(self.scope_setting, 0, timeout=10)

            # Set the new scope parameters
            self.sample_interval.put(sample_interval)
            self.trigger_delay.put(trigger_delay)
            self.periodic_setting.put(periodic)
            self.wf_debug.put(wf_debug)

            # Wait to make sure they've been implemented
            self.__wait_for_pv(self.sample_interval, sample_interval)
            self.__wait_for_pv(self.trigger_delay, trigger_delay)
            self.__wait_for_pv(self.periodic_setting, periodic)
            self.__wait_for_pv(self.wf_debug, wf_debug)

            # Put the scope operation back into the mode we want
            self.scope_setting.put(mode, wait=True)
            self.__wait_for_pv(self.scope_setting, mode)

    def return_scope(self):
        """Put the scope back into it's original configuration."""
        # When that context exits, we put it back in the old mode.
        # Setting changes should only happen when scope is in off mode.
        self.scope_setting.put(-1, wait=True)
        self.__wait_for_pv(self.scope_setting, 0, timeout=10)

        self.sample_interval.put(self.init_sample_interval)
        self.trigger_delay.put(self.init_trigger_delay)
        self.periodic_setting.put(self.init_periodic_setting)
        self.wf_debug.put(self.init_debug_setting)

        self.__wait_for_pv(self.sample_interval, self.init_sample_interval)
        self.__wait_for_pv(self.trigger_delay, self.init_trigger_delay)
        self.__wait_for_pv(self.periodic_setting, self.init_periodic_setting)
        self.__wait_for_pv(self.wf_debug, self.init_debug_setting)

        self.scope_setting.put(self.init_mode, wait=True)
        self.__wait_for_pv(self.scope_setting, self.init_mode)

    @contextmanager
    def scope_mode(self, mode=3):
        """Allows convenient flip to scope mode via context manager.  Restores original values on exiting context."""
        # Cache the values so we can restore
        old_mode = self.__get_pv(self.scope_setting)
        old_sample_interval = self.__get_pv(self.sample_interval)
        old_trigger_delay = self.__get_pv(self.trigger_delay)
        old_periodic_setting = self.__get_pv(self.periodic_setting)
        old_debug_setting = self.__get_pv(self.wf_debug)

        # These desired settings for data collection
        sample_interval = 0.2
        trigger_delay = 102.4
        periodic = 0.1
        wf_debug = 1

        # Put the cavity into scope mode when called with 'with'.  Make sure we disable the first mode before updating
        # the second.
        try:

            # Only go through the trouble of reseting the scope system if we need to change the settings. K. Hesse
            # said that occassionally we have trouble with changing settings if a reset is not done first
            if (old_mode != mode) or (old_sample_interval != sample_interval) or (
                    old_trigger_delay != trigger_delay) or (old_periodic_setting != periodic) or (
                    old_debug_setting != wf_debug):
                # We need to turn the scope mode off.  Apply our settings.  Turn it to periodic.  Unroll those changes
                # when done.
                self.scope_setting.put(-1, wait=True)
                # Particularly in development environment, this can take a long time to recover back to 0 after being reset.
                self.__wait_for_pv(self.scope_setting, 0, timeout=10)

                self.sample_interval.put(sample_interval)
                self.trigger_delay.put(trigger_delay)
                self.periodic_setting.put(periodic)
                self.wf_debug.put(wf_debug)

                self.__wait_for_pv(self.sample_interval, sample_interval)
                self.__wait_for_pv(self.trigger_delay, trigger_delay)
                self.__wait_for_pv(self.periodic_setting, periodic)
                self.__wait_for_pv(self.wf_debug, wf_debug)

                self.scope_setting.put(mode, wait=True)
                self.__wait_for_pv(self.scope_setting, mode)

            # yield so we can run statements from body of 'with' statement with cavity in scope mode.
            yield

        finally:
            # When that context exits, we put it back in the old mode.
            # Setting changes should only happen when scope is in off mode.            
            self.scope_setting.put(-1, wait=True)
            self.__wait_for_pv(self.scope_setting, 0, timeout=10)

            self.sample_interval.put(old_sample_interval)
            self.trigger_delay.put(old_trigger_delay)
            self.periodic_setting.put(old_periodic_setting)
            self.wf_debug.put(old_debug_setting)

            self.__wait_for_pv(self.sample_interval, old_sample_interval)
            self.__wait_for_pv(self.trigger_delay, old_trigger_delay)
            self.__wait_for_pv(self.periodic_setting, old_periodic_setting)
            self.__wait_for_pv(self.wf_debug, old_debug_setting)

            self.scope_setting.put(old_mode, wait=True)
            self.__wait_for_pv(self.scope_setting, old_mode)
