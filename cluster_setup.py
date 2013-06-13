import os
import shutil
import sys
from time import sleep
from pymongo import MongoClient


replset_0_ports = range(4000, 4002 + 1)
replset_1_ports = range(5000, 5002 + 1)
config_ports = range(6000, 6002 + 1)

# Data directories.
replset_0_dirs = ['replset_0_%d' % i for i in replset_0_ports]
replset_1_dirs = ['replset_1_%d' % i for i in replset_1_ports]
config_dirs = ['config_%d' % i for i in config_ports]
all_dirs = replset_0_dirs + replset_1_dirs + config_dirs


def setup_directories():
    print 'Removing data directories....'
    for directory in all_dirs:
        shutil.rmtree(directory, ignore_errors=True)

    command = 'killall mongod mongos'
    print(command)
    os.system(command)

    print 'Creating data directories....'
    for directory in all_dirs:
        os.mkdir(directory)

        # Create an empty logfile.
        open(os.path.join(directory, 'log'), 'w+').close()


def setup_replica_sets():
    # Start replica sets.
    for replset_name, ports, dirs in [
        ('replset_0', replset_0_ports, replset_0_dirs),
        ('replset_1', replset_1_ports, replset_1_dirs),
    ]:
        for port, directory in zip(ports, dirs):
            logpath = os.path.join(directory, 'log')
            command = (
                'mongod --dbpath %s --logpath %s --port %d --nohttpinterface'
                ' --fork --replSet %s'
                % (directory, logpath, port, replset_name))

            print(command)
            assert 0 == os.system(command)

        sleep(5)

        client = MongoClient('localhost', ports[0])
        client.admin.command(
            'replSetInitiate', {
                '_id': replset_name,
                'members': [{
                    '_id': i,
                    'host': 'localhost:%d' % port,
                } for i, port in enumerate(ports)]})

    print('Waiting for primaries.')
    clients = [
        MongoClient('localhost', replset_0_ports[0]),
        MongoClient('localhost', replset_1_ports[0])]

    for second in range(45):
        if not clients:
            print('Both replica sets are initialized.')
            break

        for client in clients:
            status = client.admin.command('replSetGetStatus')
            primary = [
                member for member in status['members']
                if member['stateStr'] == 'PRIMARY']

            if primary:
                clients.remove(client)
                break

        sleep(1)  # Try again in a second.
    else:
        print('One or both replica sets has no primary after 45 seconds.')
        sys.exit(2)


def setup_config_servers():
    # Start config servers.
    for port, directory in zip(config_ports, config_dirs):
        logpath = os.path.join(directory, 'log')
        command = (
            'mongod --dbpath %s --logpath %s --port %d --nohttpinterface'
            ' --fork --configsvr'
            % (directory, logpath, port))

        print(command)
        assert 0 == os.system(command)

    sleep(1)


def start_mongos():
    config_dbs = ','.join([
        'localhost:%d' % port for port in config_ports])

    command = ('mongos --configdb %s --fork --logpath mongos.log' % config_dbs)
    print(command)
    assert 0 == os.system(command)
    sleep(1)


def add_shards():
    print('Adding shards.')
    client = MongoClient()  # Connect to mongos.
    for replset_name, ports in [
        ('replset_0', replset_0_ports),
        ('replset_1', replset_1_ports),
    ]:
        shard = '%s/%s' % (
            replset_name,
            ','.join(['localhost:%d' % port for port in ports]))

        client.admin.command('addShard', shard, name=replset_name)


def shard_collection():
    print('Sharding collection.')
    client = MongoClient()  # Connect to mongos.
    client.admin.command('enableSharding', 'test')  # Shard the 'test' db.
    client.admin.command(
        'shardCollection', 'test.sharded_collection', key={'shard_key': 1})


def main():
    # response = raw_input(
    #     'Clear local data directories and kill all mongod and mongos? [y/n]\n')
    #
    # if response.lower().strip() not in ('y', 'yes'):
    #     print('Quitting.')
    #     sys.exit(1)

    setup_directories()
    setup_replica_sets()
    setup_config_servers()
    start_mongos()
    add_shards()
    shard_collection()


if __name__ == '__main__':
    main()
