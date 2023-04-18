# This file is part of the Open Data Cube, see https://opendatacube.org for more information
#
# Copyright (c) 2015-2020 ODC Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Module
"""
import pytest
import configparser
from textwrap import dedent

from datacube_sp.config import LocalConfig, parse_connect_url, parse_env_params, auto_config
from datacube_sp.testutils import write_files


def test_find_config():
    files = write_files({
        'base.conf': dedent("""\
            [datacube_sp]
            db_hostname: fakehost.test.lan
        """),
        'override.conf': dedent("""\
            [datacube_sp]
            db_hostname: overridden.test.lan
            db_database: overridden_db
        """)
    })

    # One config file
    config = LocalConfig.find(paths=[str(files.joinpath('base.conf'))])
    assert config['db_hostname'] == 'fakehost.test.lan'
    # Not set: uses default
    assert config['db_database'] == 'datacube_sp'

    # Now two config files, with the latter overriding earlier options.
    config = LocalConfig.find(paths=[str(files.joinpath('base.conf')),
                                     str(files.joinpath('override.conf'))])
    assert config['db_hostname'] == 'overridden.test.lan'
    assert config['db_database'] == 'overridden_db'


config_sample = """
[default]
db_database: datacube_sp

# A blank host will use a local socket. Specify a hostname (such as localhost) to use TCP.
db_hostname:

# Credentials are optional: you might have other Postgres authentication configured.
# The default username is the current user id
# db_username:
# A blank password will fall back to default postgres driver authentication, such as reading your ~/.pgpass file.
# db_password:
index_driver: pg


## Development environment ##
[dev]
# These fields are all the defaults, so they could be omitted, but are here for reference

db_database: datacube_sp

# A blank host will use a local socket. Specify a hostname (such as localhost) to use TCP.
db_hostname:

# Credentials are optional: you might have other Postgres authentication configured.
# The default username is the current user id
# db_username:
# A blank password will fall back to default postgres driver authentication, such as reading your ~/.pgpass file.
# db_password:

## Staging environment ##
[staging]
db_hostname: staging.dea.ga.gov.au
"""


def test_using_configparser(tmpdir):
    sample_config = tmpdir.join('datacube_sp.conf')
    sample_config.write(config_sample)

    config = configparser.ConfigParser()
    config.read(str(sample_config))


def test_empty_configfile(tmpdir):
    default_only = """[default]"""
    sample_file = tmpdir.join('datacube_sp.conf')
    sample_file.write(default_only)
    config = configparser.ConfigParser()
    config.read(str(sample_file))


def test_parse_db_url():

    assert parse_connect_url('postgresql:///db') == dict(database='db', hostname='')
    assert parse_connect_url('postgresql://some.tld/db') == dict(database='db', hostname='some.tld')
    assert parse_connect_url('postgresql://some.tld:3344/db') == dict(
        database='db',
        hostname='some.tld',
        port='3344')
    assert parse_connect_url('postgresql://user@some.tld:3344/db') == dict(
        username='user',
        database='db',
        hostname='some.tld',
        port='3344')
    assert parse_connect_url('postgresql://user:pass@some.tld:3344/db') == dict(
        password='pass',
        username='user',
        database='db',
        hostname='some.tld',
        port='3344')

    # check urlencode is reversed for password field
    assert parse_connect_url('postgresql://user:pass%40@some.tld:3344/db') == dict(
        password='pass@',
        username='user',
        database='db',
        hostname='some.tld',
        port='3344')

    assert parse_connect_url('postgresql:///db?host=/var/run/postgresql') == dict(
        database='db',
        hostname='/var/run/postgresql')

    assert parse_connect_url(
        'postgresql:///?user=user&password=pass%40&host=/var/run/postgresql&port=3344&dbname=db&sslmode=allow'
    ) == dict(
        password='pass@',
        username='user',
        database='db',
        hostname='/var/run/postgresql',
        port='3344')


def _clear_cfg_env(monkeypatch):
    for e in ('DATACUBE_DB_URL',
              'DB_HOSTNAME',
              'DB_PORT',
              'DB_USERNAME',
              'DB_PASSWORD',
              'DATACUBE_IAM_AUTHENTICATION',
              'DATACUBE_IAM_TIMEOUT'):
        monkeypatch.delenv(e, raising=False)


def test_parse_env(monkeypatch):
    def set_env(**kw):
        _clear_cfg_env(monkeypatch)
        for e, v in kw.items():
            monkeypatch.setenv(e, v)

    def check_env(**kw):
        set_env(**kw)
        return parse_env_params()

    assert check_env() == {}
    assert check_env(DATACUBE_IAM_AUTHENTICATION="yes",
                     DATACUBE_IAM_TIMEOUT='666') == dict(
        iam_authentication=True,
        iam_timeout=666)
    assert check_env(DATACUBE_DB_URL='postgresql:///db') == dict(
        hostname='',
        database='db'
    )
    assert check_env(DATACUBE_DB_URL='postgresql://uu:%20pass%40@host.tld:3344/db') == dict(
        username='uu',
        password=' pass@',
        hostname='host.tld',
        port='3344',
        database='db'
    )
    assert check_env(DB_DATABASE='db') == dict(
        database='db'
    )
    assert check_env(DB_DATABASE='db', DB_HOSTNAME='host.tld') == dict(
        database='db',
        hostname='host.tld'
    )
    assert check_env(DB_DATABASE='db',
                     DB_HOSTNAME='host.tld',
                     DB_USERNAME='user',
                     DB_PASSWORD='pass@') == dict(
                         database='db',
                         hostname='host.tld',
                         username='user',
                         password='pass@')

    assert check_env(DB_DATABASE='db',
                     DB_HOSTNAME='host.tld',
                     DB_USERNAME='user',
                     DB_PORT='',
                     DB_PASSWORD='pass@') == dict(
                         database='db',
                         hostname='host.tld',
                         username='user',
                         password='pass@')


def test_cfg_from_env(monkeypatch):
    def set_env(**kw):
        _clear_cfg_env(monkeypatch)
        for e, v in kw.items():
            monkeypatch.setenv(e, v)

    set_env(DATACUBE_DB_URL='postgresql://uu:%20pass%40@host.tld:3344/db')
    cfg = LocalConfig.find()
    assert '3344' in str(cfg)
    assert '3344' in repr(cfg)
    assert cfg['db_username'] == 'uu'
    assert cfg['db_password'] == ' pass@'
    assert cfg['db_hostname'] == 'host.tld'
    assert cfg['db_database'] == 'db'
    assert cfg['db_port'] == '3344'

    # check that password is redacted
    assert " pass@" not in str(cfg)
    assert "***" in str(cfg)
    assert " pass@" not in repr(cfg)
    assert "***" in repr(cfg)

    set_env(DB_DATABASE='dc2',
            DB_HOSTNAME='remote.db',
            DB_PORT='4433',
            DB_USERNAME='dcu',
            DB_PASSWORD='gg')
    cfg = LocalConfig.find()
    assert cfg['db_username'] == 'dcu'
    assert cfg['db_password'] == 'gg'
    assert cfg['db_hostname'] == 'remote.db'
    assert cfg['db_database'] == 'dc2'
    assert cfg['db_port'] == '4433'


def test_auto_config(monkeypatch, tmpdir):
    from pathlib import Path

    cfg_file = Path(str(tmpdir/"dc.cfg"))
    assert cfg_file.exists() is False
    cfg_file_name = str(cfg_file)

    _clear_cfg_env(monkeypatch)
    monkeypatch.setenv('DATACUBE_CONFIG_PATH', cfg_file_name)

    assert auto_config() == cfg_file_name
    assert cfg_file.exists() is True

    monkeypatch.setenv('DB_HOSTNAME', 'should-not-be-used.local')
    # second run should skip overwriting
    assert auto_config() == cfg_file_name

    config = LocalConfig.find(paths=cfg_file_name)
    assert config['db_hostname'] == ''
    assert config['db_database'] == 'datacube_sp'

    cfg_file.unlink()
    assert cfg_file.exists() is False
    _clear_cfg_env(monkeypatch)

    monkeypatch.setenv('DATACUBE_CONFIG_PATH', cfg_file_name)
    monkeypatch.setenv('DB_HOSTNAME', 'some.db')
    monkeypatch.setenv('DB_USERNAME', 'user')

    assert auto_config() == cfg_file_name
    config = LocalConfig.find(paths=cfg_file_name)
    assert config['db_hostname'] == 'some.db'
    assert config['db_database'] == 'datacube_sp'
    assert config['db_username'] == 'user'

    assert config.get('no_such_key', 10) == 10
    with pytest.raises(configparser.NoOptionError):
        config.get('no_such_key')
