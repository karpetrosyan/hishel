import os

import pytest


@pytest.fixture()
def use_temp_dir(tmpdir):
    cur_dir = os.getcwd()
    os.chdir(tmpdir)
    yield
    os.chdir(cur_dir)


@pytest.fixture(scope='function', autouse=True)
def use_redisdb(redisdb):
    ...
