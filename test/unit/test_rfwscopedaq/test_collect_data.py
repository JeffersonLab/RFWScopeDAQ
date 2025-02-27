import shutil
from pathlib import Path
from unittest import TestCase
import os
from datetime import datetime
import filecmp

import numpy as np
import pandas as pd

from rfwscopedaq.collect_data import write_files

class TestCollectData(TestCase):

    def test_write_files(self):
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
            df = pd.DataFrame({'Time': np.linspace(0, 4095, 8192), 'GMES': np.ones(8192),
                               'PMES': np.ones(8192) * 2})

            # write_files expects that the parent directories will have already be created
            dir_path = Path(os.path.normpath(os.path.join(basedir, epics_name[0:3], epics_name[0:4])))
            dir_path.mkdir(parents=True, exist_ok=True)

            # Write the file out and compare
            write_files(basedir=basedir, epics_name=epics_name, start_time=start_time, end_time=end_time, data_frame=df)
            self.assertTrue(filecmp.cmp(exp, str(file_path)))
        finally:
            # Make sure we clean up
            if tmp_path.exists():
                shutil.rmtree(str(tmp_path))
