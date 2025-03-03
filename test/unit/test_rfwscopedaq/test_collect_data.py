import shutil
from pathlib import Path
from threading import Event
from unittest import TestCase
from unittest.mock import patch, MagicMock
import os
from datetime import datetime
import filecmp

import numpy as np
import pandas as pd

from rfwscopedaq.collect_data import DaqThread


class MockPV:
    def __init__(self, value):
        self.value = value

    def get(self, *args, **kwargs):
        return self.value

class MockCavity(MagicMock):
    def __init__(self,value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sample_interval = MockPV(value=value)

class TestDAQThread(TestCase):

    def test_write_files1(self):
        # Path where the files should exist
        curr_path = Path(__file__).resolve().parent
        tmp_path = curr_path / "tmp/R12"
        file_path = tmp_path / "R123/R123WFS_2020_01_01_12-34-56-000001_2020_01_01_12-34-58-000002.tsv"
        exp = curr_path / "write_files_test.tsv"

        try:
            basedir = os.path.join(os.path.dirname(__file__), "tmp")
            start_time = datetime.strptime("2020-01-01 12:34:56.000001", "%Y-%m-%d %H:%M:%S.%f")
            end_time = datetime.strptime("2020-01-01 12:34:58.000002", "%Y-%m-%d %H:%M:%S.%f")
            epics_name = 'R123'
            result_dict = {'GMES': np.ones(8192), 'PMES': np.ones(8192) * 2}
            f_metadata = {'a': 1.0}
            s_metadata = {'b': "asdf"}

            # write_files expects that the parent directories will have already be created
            # dir_path = Path(os.path.normpath(os.path.join(basedir, epics_name[0:3], epics_name[0:4])))
            dir_path = Path(os.path.normpath(os.path.join(basedir, epics_name[0:3])))

            # Write the file out and compare
            with patch("rfwscopedaq.collect_data.Cavity", new=lambda *args, **kwargs: MockCavity(0.2, *args, **kwargs)):
                thread = DaqThread(exit_event=Event(), epics_name=epics_name, out_dir=dir_path, signals=["GMES", "PMES"],
                                   duration=5.0, timeout=1.0, db_pool=None, output="file", meta_pvs=[])

                thread.write_files(results=result_dict, start_time=start_time, end_time=end_time, f_metadata=f_metadata,
                                   s_metadata=s_metadata)

            self.assertTrue(filecmp.cmp(exp, str(file_path)))
        finally:
            # Make sure we clean up
            if tmp_path.exists():
                shutil.rmtree(str(tmp_path))
