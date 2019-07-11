# -*- coding: utf-8 -*-

import logging
import os
import shutil

import pandas as pd

LOGGER = logging.getLogger(__name__)


class GreenGuardLoader(object):
    """GreenGuardLoader class.

    The GreenGuardLoader class provides a simple interface to load a relational
    dataset in the format expected by the GreenGuard Pipelines.

    Args:
        dataset_path (str):
            Path to the root folder of the dataset.
        target_times (str):
            Name of the target_times file.
        target_column (str):
            Name of the target column within the target_times file.
        readings (str):
            Name of the readings file.
        turbines (str):
            Name of the turbines file.
        signals (str):
            Name of the signals file.
        gzip (bool):
            Whether the CSV files will be in GZipped. If `True`, the filenames
            are expected to have the `.csv.gz` extension.
    """

    def __init__(self, dataset_path, target_times='target_times', target_column='target',
                 readings='readings', turbines='turbines', signals='signals', gzip=False):

        self._dataset_path = dataset_path
        self._target_times = target_times
        self._target_column = target_column
        self._readings = readings
        self._turbines = turbines
        self._signals = signals
        self._gzip = gzip

    def _read_csv(self, table, timestamp=False):
        if timestamp:
            timestamp = ['timestamp']

        if '.csv' not in table:
            table += '.csv'
            if self._gzip:
                table += '.gz'

        path = os.path.join(self._dataset_path, table)

        return pd.read_csv(path, parse_dates=timestamp, infer_datetime_format=True)

    def load(self, return_target=True):
        """Load the dataset.

        Args:
            return_target (bool):
                If True, return the target column as a separated vector.
                Otherwise, the target column is expected to be already missing from
                the target table.

        Returns:
            (tuple):
                * ``X (pandas.DataFrame)``: A pandas.DataFrame with the contents of the
                  target table.
                * ``y (pandas.Series, optional)``: A pandas.Series with the contents of
                  the target column.
                * ``tables (dict)``: A dictionary containing the readings, turbines and
                  signals tables as pandas.DataFrames.
        """
        tables = {
            'readings': self._read_csv(self._readings, True),
            'signals': self._read_csv(self._signals),
            'turbines': self._read_csv(self._turbines),
        }

        X = self._read_csv(self._target_times, True)
        if return_target:
            y = X.pop(self._target_column)
            return X, y, tables

        else:
            return X, tables


class GreenGuardRawLoader(object):
    """GreenGuardRawLoader class.

    The GreenGuardRawLoader class provides a simple interface to load a
    time series data provided turbine in raw format and return it in the
    format expected by the GreenGuard Pipelines.

    This raw format has the following characteristics:

        * All the data from all the turbines is inside a single folder.
        * Inside the data folder, a folder exists for each turbine.
          This folders are named exactly like each turbine id, and inside it one or more
          CSV files can be found. The names of these files is not relevant.
        * Each CSV file will have the the following columns:

            * timestamp: timestemp of the reading.
            * signal: name or id of the signal.
            * value: value of the reading.

    And the output is the following 4 tables:

        * turbines:
            * `turbine_id`: column with the unique id of each turbine.
            * A number of additional columns with information about each turbine.
        * signals:
            * `signal_id`: column with the unique id of each signal.
            * A number of additional columns with information about each signal.
        * readings:
            * `reading_id`: Unique identifier of this reading.
            * `turbine_id`: Unique identifier of the turbine which this reading comes from.
            * `signal_id`: Unique identifier of the signal which this reading comes from.
            * `timestamp`: Time where the reading took place, as an ISO formatted datetime.
            * `value`: Numeric value of this reading.
        * target_times:
            * `turbine_id`: Unique identifier of the turbine which this target corresponds to.
            * `cutoff_timestamp`: The timestamp at which the target value is deemed to be known.
              This timestamp is used to filter data such that only data prior to this is used
              for featurize.
            * `target`: The value that we want to predict. This can either be a numerical value
              or a categorical label. This column can also be skipped when preparing data that
              will be used only to make predictions and not to fit any pipeline.

    Args:
        target_times_path (str):
            Path to the target_times CSV file. If turbines file is given,
            this file is expected to have a `turbines_id` column that acts
            as a foreign key to the turbines table.
            Otherwise, this file is expected to have a `turbines` column
            with the name of the turbine.
        data_path (str):
            Path to the folder containing all the turbines data.
    """

    def __init__(self, target_times_path, data_path):
        self._target_times_path = target_times_path
        self._data_path = data_path

    def _load_turbine_file(self, turbine_file):
        data = pd.read_csv(turbine_file)
        data.columns = data.columns.str.lower()

        if 'unnamed: 0' in data.columns:
            # Someone forgot to drop the index before
            # storing the DataFrame as a CSV
            del data['unnamed: 0']

        return data

    def _load_turbine(self, turbine):
        turbine_path = os.path.join(self._data_path, turbine)

        readings = list()
        for turbine_file in os.listdir(turbine_path):
            turbine_file_path = os.path.join(turbine_path, turbine_file)
            readings.append(self._load_turbine_file(turbine_file_path))

        return pd.concat(readings)

    def _load_readings(self, turbine_ids):
        readings = list()
        for turbine_id in turbine_ids:
            turbine_readings = self._load_turbine(turbine_id)
            turbine_readings['turbine_id'] = turbine_id
            readings.append(turbine_readings)

        return pd.concat(readings)

    def load(self, return_target=True):
        """Load the dataset.

        Args:
            return_target (bool):
                If True, return the target column as a separated vector.
                Otherwise, the target column is expected to be already missing from
                the target table.

        Returns:
            (tuple):
                * ``X (pandas.DataFrame)``: A pandas.DataFrame with the contents of the
                  target_times table.
                * ``y (pandas.Series, optional)``: A pandas.Series with the contents of
                  the target column.
                * ``tables (dict)``: A dictionary containing the readings, turbines and
                  signals tables as pandas.DataFrames.
        """
        X = pd.read_csv(self._target_times_path)

        turbine_ids = X.turbine_id.unique()

        readings = self._load_readings(turbine_ids)
        readings.rename(columns={'signal': 'signal_id'}, inplace=True)

        turbines = pd.DataFrame({'turbine_id': turbine_ids})
        signals = pd.DataFrame({'signal_id': readings.signal_id.unique()})

        tables = {
            'turbines': turbines,
            'readings': readings[['turbine_id', 'signal_id', 'timestamp', 'value']],
            'signals': signals
        }

        if return_target:
            y = X.pop('target')
            return X, y, tables

        else:
            return X, tables


def load_demo():
    """Load the demo included in the GreenGuard project.

    The first time that this function is executed, the data will be downloaded
    and cached inside the `greenguard/demo` folder.
    Subsequent calls will load the cached data instead of downloading it again.
    """
    demo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'demo')
    if os.path.exists(demo_path):
        loader = GreenGuardLoader(demo_path, gzip=True)
        return loader.load()

    else:
        os.mkdir(demo_path)
        try:
            loader = GreenGuardLoader('https://d3-ai-greenguard.s3.amazonaws.com/', gzip=True)
            X, tables = loader.load(target=False)
            X.to_csv(os.path.join(demo_path, 'targets.csv.gz'), index=False)
            for name, table in tables.items():
                table.to_csv(os.path.join(demo_path, name + '.csv.gz'), index=False)

            y = X.pop('target')
            return X, y, tables
        except Exception:
            shutil.rmtree(demo_path)
            raise
