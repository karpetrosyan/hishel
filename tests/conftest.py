import os

import boto3
import pytest


@pytest.fixture()
def use_temp_dir(tmpdir):
    cur_dir = os.getcwd()
    os.chdir(tmpdir)
    yield
    os.chdir(cur_dir)


@pytest.fixture(scope="session")
def client():
    endpoint_url = "http://localhost:4566"

    client = boto3.client("s3", endpoint_url=endpoint_url)

    yield client

    client.close()


@pytest.fixture(scope="session")
def bucket_name(client):
    # create bucket
    bucket_name = "hisheltests"
    client.create_bucket(Bucket=bucket_name)

    return bucket_name
