import pytest
from process_reports import main
import os
import pandas as pd


@pytest.fixture
def rpc_fn():
    return os.path.join('Sample_Reports', 'ALL_RPC-2-1-2018_Scrubbed.xlsx')


@pytest.fixture
def bucket_fn():
    return os.path.join('Sample_Reports', '2_1_18Bucket_Scrubbed.xls')


def test_default(rpc_fn, bucket_fn):

    # Run the main
    main(['-r', rpc_fn, '-b', bucket_fn, '-o', os.path.join('tests', 'test_out')])

    # Read in the files to ensure it is working
    good = 'Sample'

    files = ['Agent_Summary.csv', 'Queue_Summary.csv', 'RPC_Summary.csv']

    for file in files:
        good_df = pd.read_csv(os.path.join('tests', '{}_{}'.format(good, file)))

        out_file = os.path.join('tests', '{}_{}'.format('test_out', file))
        test_df = pd.read_csv(out_file)

        assert (good_df == test_df).all().all()
        os.remove(out_file)
