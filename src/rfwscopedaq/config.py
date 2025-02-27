# R041WFTIMES
zones = ['R04',
         'R17', 'R1M', 'R1N', 'R1P', 'R1Q',
         'R2M', 'R2N', 'R2O', 'R2P', 'R2Q']
zone_names = ['0L04',
              '1L07', '1L22', '1L23', '1L24', '1L25', '1L26',
              '2L22', '2L23', '2L24', '2L25', '2L26']
channels = ['TIMES',
            'TQMES', 'TGMES', 'TPMES',
            'TGASK', 'TPASK',
            'TCRFP', 'TCRFPP', 'TCRRP', 'TCRRPP',
            'TGLDE', 'TPLDE', 'TDETA2',
            'TCFQE2', 'TDFQES']
scope_channels = ['SIMES',
                  'SQMES', 'SGMES', 'SPMES',
                  'SGASK', 'SPASK',
                  'SCRFP', 'SCRFPP', 'SCRRP', 'SCRRPP',
                  'SGLDE', 'SPLDE',
                  'SDETA2', 'SCFQE2', 'SDFQES']
duration = 5
basedir = '/tmp/c100-rfw-scope-data/'
email = 'tsm'
interval = ''
verbose = 0

db_config = {
    'host': 'localhost',
	'user': 'scope_rw',
	'password': 'password',
	'port': '3306',
    'database': 'scope_database'
}

