# %% Set Up Logger
from colored_logger import customLogger
# end%%

# %% Import Base Packages
import numpy as np
import pandas as pd
import sys
import os
import argparse
import datetime
import traceback
from tkinter import Tk
from tkinter.filedialog import askopenfilename
logger = customLogger('report', fn='process_reports.log', mode='a')
# end%%


# %% main
def main():

    logger.info('process_reports - STARTING SCRIPT')

    # Parse inputs
    parser = RPCArgParse()
    args = parser.parse_args()

    rpc_fn = get_input_file(args, 'rpc_fn', 'RPC')
    bucket_fn = get_input_file(args, 'bucket_fn', 'Buckets')
    output_fn = args.output_fn

    # Read in RPC file
    logger.debug('Reading in rpc data file: %s' % (rpc_fn))
    rpc = read_rpc(rpc_fn)
    # Get all the buckets
    logger.debug('Reading in bucket data file: %s' % (bucket_fn))
    buckets = read_buckets(bucket_fn)

    # Process some of the RPC data to make it more useful
    def ib_ob(action_type):
        if action_type.upper().startswith('T'):
            return 'OB'
        else:
            return 'IB'
    try:
        rpc['IB_OB'] = rpc['Call Action Type Qcc'].apply(ib_ob)

        rpc['stripped'] = rpc['Call Result Type Qcc'].apply(lambda x: x[:2])
        rpc['GC'] = rpc['Created By Qcc'].apply(lambda x: x[:2])
        rpc.rename(columns={'Created By Qcc': 'Agent'}, inplace=True)
    except KeyError as e:
        # logger.exception("message")
        logger.error('Couldn"t find the key: "%s" in the RPC file: %s. '
                     'You may have input the wrong file or the file may '
                     'be corrupt' % (e.args[0], rpc_fn))
        logger.critical('ABORTING SCRIPT')
        sys.exit(0)

    # Remove any entry with a missing acct_num...these will likely be bad
    # skiprows it does remoe any empty sheets however
    buckets.dropna(subset=['Acct_Num'], inplace=True)

    # Check the BUCKETS
    if any(buckets.duplicated(subset=['Acct_Num'])):
        logger.waring(
            'You had a duplicate account number...that doesnt make a lot '
            'of sense')
        logger.warning(buckets.loc[buckets.duplicated(subset=['Acct_Num'])])

    # Merge the two together
    logger.debug('merging bucket and rpc information')
    all_df = pd.merge(buckets,
                      rpc[['Acct Id Acc', 'IB_OB', 'stripped', 'GC', 'Agent']],
                      how='outer', left_on='Acct_Num', right_on='Acct Id Acc')

    all_df.rename(columns={'Acct Id Acc': 'RPC'}, inplace=True)

    # Summarize and output
    logger.debug('summarizing data...')
    rpc_summary_df = rpc_summary(all_df)
    to_csv(rpc_summary_df, output_fn, 'RPC_Summary')

    Queue_Summary_df = Queue_Summary(all_df)
    to_csv(Queue_Summary_df, output_fn, 'Queue_Summary')

    Agent_Summary_df = Agent_Summary(all_df)
    to_csv(Agent_Summary_df, output_fn, 'Agent_Summary')

    logger.info('Ending Script successfully')

# end%%

# %% Read sheets info


def read_rpc(fn, f_type=None, skiprows=0,
             converters={'Acct Id Acc': str}, **kwargs):

    return read_info(fn, f_type=f_type, skiprows=skiprows,
                     converters=converters, **kwargs)


def read_info(fn, f_type=None, **kwargs):
    # Check for excel type if f_type is empty
    if not f_type:
        if check_excel(fn):
            f_type = 'excel'
        else:
            logger.error('read_info requires that you specify either a file '
                         'that is an excel file or a f_type input.')
            raise ValueError('Required excel filetype or f_type specified')

    # Return for bad f_types
    def unimplemented(f_type):
        logger.error('in read_info, f_type of {} is not supported at this '
                     'time...stopping'
                     .format(f_type.strip()))
        raise NotImplementedError(
            'read_info f_type - {} not implemented'.format(f_type))

    # If excel...
    if f_type.strip().lower() == 'excel':
        if not check_excel(fn):
            logger.warning(('Ftype was specified as an excel file but, '
                            '{} is not an excel file...continuing, '
                            'but may fail.'.format(
                                fn)))
        return pd.read_excel(fn, **kwargs)
    elif f_type.strip().lower() == 'csv':
        unimplemented(f_type)
    else:
        unimplemented(f_type)


def check_extension(fn, acceptable, case_insensitive=True):
    _, ext = os.path.splitext(fn)

    if case_insensitive:
        acceptable = [x.lower() for x in acceptable]
        ext = ext.lower()

    return ext.replace('.', '') in acceptable


def check_excel(fn):
    return check_extension(fn, ['xls', 'xlsx', 'xlsb', 'xlsm'])


def read_buckets(bucket_fn):
    if not check_excel(bucket_fn):
        logger.warning('Bucket only supports excel filetypes. '
                       'Input file of {} is not known to be an excel type. '
                       'Continuing, but may have issues.'.format(bucket_fn))

    excel_bucket = pd.ExcelFile(bucket_fn)

    bucket_dfs = []
    for sheet in excel_bucket.sheet_names:
        bucket_dfs.append(read_bucket_sheet(sheet, excel_bucket))

    buckets = pd.concat(bucket_dfs, ignore_index=True)
    return buckets


def read_bucket_sheet(sheet_name, excel_file,
                      global_names=['Acct_Num', 'Delinq', 'Date'],
                      queue_name='Associate'):
    logger.debug('Reading %s' % (sheet_name))
    if sheet_name in ['60 Day',
                      'Mid GC',
                      'Mid In',
                      'EPD 31+',
                      'FPD 2-30',
                      'Can 2-30',
                      'Can 31+']:
        skiprows = 0
        cols = ['Acct Number', 'Days Delinquent', 'Current Date']
    elif sheet_name == 'GC-P30':
        skiprows = None
        cols = ['Acct Id Acc', 'Days Dlq Acf', 'Current Date']
    elif sheet_name == 'GC-EPD':
        skiprows = 0
        cols = ['Acct Id Acc', 'Days Dlq Acf', 'Current Date']
    else:
        logger.warning('Sheetname %s - We dont have a known pattern...using '
                       'default' % (sheet_name))
        skiprows = 0
        cols = ['Acct Number', 'Days Delinquent', 'Current Date']

    try:
        df = excel_file.parse(
            sheet_name=sheet_name, skiprows=skiprows,
            converters={cols[0]: str,
                        cols[-1]:
                            lambda x: pd.to_datetime(x, format='%m/%d/%y')})
    except ValueError as e:
        logger.warn('Read buckets failed, likely datetime formatter for speed'
                    '...repeating with no datetime formatter')
        logger.warn('{0}'.format(e))

        # Slower generic version
        df = excel_file.parse(
            sheet_name=sheet_name, skiprows=skiprows,
            converters={cols[0]: str, cols[-1]: pd.to_datetime})

    # Check to make sure we found all the columns
    for col in cols:
        if col not in df.columns:
            logger.error('Could not find specified col - "{}" in inputs. '
                         ' Known columns are {}...exiting'
                         .format(col, df.columns.values))
            raise KeyError("['{}'] not in index".format(col))

    # Fill in queuename with nans if it doesn't exist
    if queue_name not in df.columns:
        df[queue_name] = np.nan

    # Rename the columns
    df.rename(columns=dict(zip(cols, global_names)), inplace=True)

    # Add the bucket Column
    df['Bucket'] = sheet_name

    if len(df.dropna(subset=[global_names[0]]).index) < 1:
        logger.warn(
            '%s was empty and had no account numbers.  '
            'Could be something wrong.' % (sheet_name))

    return df[global_names + [queue_name] + ['Bucket']]

# end%%

# %%


def rpc_summary(all_df):
    summary_df = all_df.groupby(['Bucket', 'Date']).apply(
        lambda x: pd.Series(dict(
            Queue_total=x['Acct_Num'].nunique(),
            Total_RPC=x['RPC'].count(),
            Unique_RPC=x['RPC'].nunique(),
            Total_PTP=x['RPC'].loc[x['stripped'] == 'PP'].count(),
            Unique_PTP=x['RPC'].loc[x['stripped'] == 'PP'].nunique(),
            Outbound_RPC=x['RPC'].loc[x['IB_OB'] == 'OB'].count(),
            Outbound_PTP=x['RPC'].loc[(x['IB_OB'] == 'OB') & (
                x['stripped'] == 'PP')].count(),
            Inbound_RPC=x['RPC'].loc[x['IB_OB'] == 'IB'].count(),
            Inbound_PTP=x['RPC'].loc[(x['IB_OB'] == 'IB') & (
                x['stripped'] == 'PP')].count(),
            HD_RPC=x['RPC'].loc[x['GC'] != 'GC'].count(),
            HD_PTP=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['stripped'] == 'PP')].count(),
            HD_OB_RPC=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['IB_OB'] == 'OB')].count(),
            HD_OB_PTP=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['stripped'] == 'PP') & (x['IB_OB'] == 'OB')].count(),
            HD_IB_RPC=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['IB_OB'] == 'IB')].count(),
            HD_IB_PTP=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['stripped'] == 'PP') & (x['IB_OB'] == 'IB')].count(),
            GC_RPC=x['RPC'].loc[x['GC'] == 'GC'].count(),
            GC_PTP=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['stripped'] == 'PP')].count(),
            GC_OB_RPC=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['IB_OB'] == 'OB')].count(),
            GC_OB_PTP=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['stripped'] == 'PP') & (x['IB_OB'] == 'OB')].count(),
            GC_IB_RPC=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['IB_OB'] == 'IB')].count(),
            GC_IB_PTP=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['stripped'] == 'PP') & (x['IB_OB'] == 'IB')].count(),
        )))

    summary_df['U_RPC_Q'] = summary_df['Unique_RPC'].astype(
        np.float64) / summary_df['Queue_total'].astype(np.float64)
    summary_df['U_PTP_Q'] = summary_df['Unique_PTP'].astype(
        np.float64) / summary_df['Queue_total'].astype(np.float64)

    # Reorder Cols
    cols = [
        'Queue_total',
        'Total_RPC',
        'Unique_RPC',
        'Total_PTP',
        'Unique_PTP',
        'U_RPC_Q',
        'U_PTP_Q',
        'Outbound_RPC',
        'Outbound_PTP',
        'Inbound_RPC',
        'Inbound_PTP',
        'HD_RPC',
        'HD_PTP',
        'HD_OB_RPC',
        'HD_OB_PTP',
        'HD_IB_RPC',
        'HD_IB_PTP',
        'GC_RPC',
        'GC_PTP',
        'GC_OB_RPC',
        'GC_OB_PTP',
        'GC_IB_RPC',
        'GC_IB_PTP']

    summary_df = summary_df[cols]

    return summary_df


def Queue_Summary(all_df):
    summary_df = all_df.groupby(['Bucket', 'Associate', 'Date']).apply(
        lambda x: pd.Series(dict(
            Queue=x['Acct_Num'].nunique(),
            Total_RPC=x['RPC'].count(),
            Unique_RPC=x['RPC'].nunique(),
            Total_PTP=x['RPC'].loc[x['stripped'] == 'PP'].count(),
            Unique_PTP=x['RPC'].loc[x['stripped'] == 'PP'].nunique(),
            Outbound_RPC=x['RPC'].loc[x['IB_OB'] == 'OB'].count(),
            Outbound_PTP=x['RPC'].loc[(x['IB_OB'] == 'OB') & (
                x['stripped'] == 'PP')].count(),
            Inbound_RPC=x['RPC'].loc[x['IB_OB'] == 'IB'].count(),
            Inbound_PTP=x['RPC'].loc[(x['IB_OB'] == 'IB') & (
                x['stripped'] == 'PP')].count(),
            HD_RPC=x['RPC'].loc[x['GC'] != 'GC'].count(),
            HD_PTP=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['stripped'] == 'PP')].count(),
            HD_OB_RPC=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['IB_OB'] == 'OB')].count(),
            HD_OB_PTP=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['stripped'] == 'PP') & (x['IB_OB'] == 'OB')].count(),
            HD_IB_RPC=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['IB_OB'] == 'IB')].count(),
            HD_IB_PTP=x['RPC'].loc[(x['GC'] != 'GC') & (
                x['stripped'] == 'PP') & (x['IB_OB'] == 'IB')].count(),
            GC_RPC=x['RPC'].loc[x['GC'] == 'GC'].count(),
            GC_PTP=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['stripped'] == 'PP')].count(),
            GC_OB_RPC=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['IB_OB'] == 'OB')].count(),
            GC_OB_PTP=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['stripped'] == 'PP') & (x['IB_OB'] == 'OB')].count(),
            GC_IB_RPC=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['IB_OB'] == 'IB')].count(),
            GC_IB_PTP=x['RPC'].loc[(x['GC'] == 'GC') & (
                x['stripped'] == 'PP') & (x['IB_OB'] == 'IB')].count(),
        )))

    summary_df['U_RPC_Q'] = summary_df['Unique_RPC'].astype(
        np.float64) / summary_df['Queue'].astype(np.float64)
    summary_df['U_PTP_Q'] = summary_df['Unique_PTP'].astype(
        np.float64) / summary_df['Queue'].astype(np.float64)

    # Reorder cols
    cols = [
        'Queue',
        'Total_RPC',
        'Unique_RPC',
        'Total_PTP',
        'Unique_PTP',
        'U_RPC_Q',
        'U_PTP_Q',
        'Outbound_RPC',
        'Outbound_PTP',
        'Inbound_RPC',
        'Inbound_PTP',
        'HD_RPC',
        'HD_PTP',
        'HD_OB_RPC',
        'HD_OB_PTP',
        'HD_IB_RPC',
        'HD_IB_PTP',
        'GC_RPC',
        'GC_PTP',
        'GC_OB_RPC',
        'GC_OB_PTP',
        'GC_IB_RPC',
        'GC_IB_PTP']

    summary_df = summary_df[cols]

    return summary_df


def Agent_Summary(all_df):
    unique_associates = all_df['Associate'].dropna().unique()
    # unique_agents = all_df['Agent'].unique()
    only_queue_agents = all_df.loc[all_df['Agent'].isin(unique_associates)]

    cols = [
        'Unique_RPC',
        'Unique_PTP',
        'Outbound_RPC',
        'Outbound_PTP',
        'Inbound_RPC',
        'Inbound_PTP']

    if len(only_queue_agents['Agent'].dropna().unique()) < 1:
        logger.error(
            "Cant summarize Agents...couldn't find agents in queues..."
            "often this means you have some issues with the bucket Associate "
            "and RPC Agent names")
        return pd.DataFrame(columns=cols)
    summary_df = only_queue_agents.groupby(['Bucket', 'Agent', 'Date']).apply(
        lambda x: pd.Series(dict(
            Unique_RPC=x['RPC'].nunique(),
            Unique_PTP=x['RPC'].loc[x['stripped'] == 'PP'].nunique(),
            Outbound_RPC=x['RPC'].loc[x['IB_OB'] == 'OB'].count(),
            Outbound_PTP=x['RPC'].loc[(x['IB_OB'] == 'OB') & (
                x['stripped'] == 'PP')].count(),
            Inbound_RPC=x['RPC'].loc[x['IB_OB'] == 'IB'].count(),
            Inbound_PTP=x['RPC'].loc[(x['IB_OB'] == 'IB') &
                                     (x['stripped'] == 'PP')].count())))

    # Re order
    summary_df = summary_df[cols]
    return summary_df
# end%%

# %% to csv


def to_csv(df, output_header, tail):
    write_fn = '{}_{}.csv'.format(output_header, tail)
    logger.debug('Outputing CSV to : {}'.format(write_fn))

    if len(df.index) < 1:
        logger.error(
            'The data frame for {} is empty...skipping ouput'.format(write_fn))
    else:
        df.to_csv(write_fn)
# end%%

# %% logger


def log_uncaught_exceptions(ex_cls, ex, tb):
    logger.critical(''.join(traceback.format_tb(tb)))
    logger.critical('{0}: {1}'.format(ex_cls, ex))

# end%%

# %% Is valid file for arg parser

# end%%

# %% Open file if you don't want to specify in the command line


def get_input_file(parsed_args, key, real_text=None):
    if real_text is None:
        real_text = key
    if vars(parsed_args)[key] is None:
        logger.debug(
            'You didnt enter a file in the command line for %s...'
            'opening dialog' % (key))
        return tk_open_file('Select File for %s' % real_text)
    else:
        return vars(parsed_args)[key]


def tk_open_file(title=None):
    # http://infohost.nmt.edu/tcc/help/pubs/tkinter/web/tkFileDialog.html
    Tk().withdraw()  # we don't want a full GUI, so keep the root window from
    # show an "Open" dialog box and return the path to the selected file
    filename = askopenfilename(title=title)
    if not filename:
        logger.error('You didnt select a filename for %s' % (title))
        logger.critical('ABORTING SCRIPT')
        sys.exit(0)
    return filename

# end%%

# %% Arg parser


class argparse_logger(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if file is sys.stderr:
            logger.warning('Arg Parse did something bad...see below:')
            logger.error(message)
        else:
            super()._print_message(message, file=file)


class RPCArgParse(argparse_logger):

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # Set default description...can be overridden
        if not self.description:
            self.description = 'Read in the main files to create RPC summary'

        # Add the elements we want
        self.add_CustomElements()

    @staticmethod
    def is_valid_file(arg):
        if not os.path.exists(arg):
            # parser.error("Cannot find the file: %s" % arg)
            raise argparse.ArgumentTypeError(
                "Specified file does not exist = {}".format(arg))
        return arg

    def add_CustomElements(self):
        self.add_argument('-r', '--rpc_fn', metavar='RPC_INPUT_PATH',
                          type=self.is_valid_file,
                          help='Needs to be the full or '
                          'relative path to the RPC excel file')
        self.add_argument('-b', '--bucket_fn', metavar='BUCKET_INPUT_PATH',
                          type=self.is_valid_file,
                          help='Needs to be the full or '
                          'relative path to the Buckets excel file')
        self.add_argument('-o', '--output_fn', metavar='OUTPUT_FN_HEADER',
                          type=str,
                          default='%s' % datetime.date.today().strftime(
                              '%Y_%m_%d'),
                          help='Output file location, '
                          'defaults to YYYY_MM_DD_<DESCRIP>.csv')

# end%%


# %%
if __name__ == '__main__':
    #  Set up logger
    sys.excepthook = log_uncaught_exceptions
    main()

# end%%
