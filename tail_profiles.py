#!/usr/bin/env python
import datetime
import threading
import sys
from time import sleep

try:
    import json
except ImportError:
    import simplejson as json

# Get list of terminal foreground colors if possible.
try:
    from colorama import Fore
except ImportError:
    Fore = None
    colors = ['']
else:
    # Color names are like Fore.RED, Fore.BLUE, ....
    colors = [
        getattr(Fore, name) for name in dir(Fore)
        if name.upper() == name
        and not name.startswith('_')
        and name not in ('BLACK', 'BLUE', 'RESET')]

import bson
from pymongo import MongoClient, ReadPreference


replset_0_ports = range(4000, 4002 + 1)
replset_1_ports = range(5000, 5002 + 1)
all_ports = replset_0_ports + replset_1_ports


class Member(object):
    def __init__(self, client, color):
        self.client = client
        ismaster = client.admin.command('ismaster')
        if ismaster.get('ismaster'):
            self.state = 'primary'
        else:
            self.state = 'secondary'

        self.replset_name = ismaster['setName']
        self.color = color


def connect():
    members = []
    for i, port in enumerate(all_ports):
        client = MongoClient(
            'localhost',
            port,
            read_preference=ReadPreference.SECONDARY,  # Allow secondaries.
            document_class=bson.SON                    # Preserve field order.
        )

        color = colors[i % len(colors)]
        members.append(Member(client, color))

    return members


def enable_profiling(members):
    print('Turning on profiling.')
    for member in members:
        # Enable profiling on the 'test' database.
        member.client.test.set_profiling_level(2)


def tail_profiles(members):
    class ProfileThread(threading.Thread):
        def __init__(self, member):
            super(ProfileThread, self).__init__()
            self.setDaemon(True)
            self.member = member

        def run(self):
            db = self.member.client.test
            profile = db.system.profile

            sys.stdout.write('Tailing %s on %s %s on %s\n' % (
                profile,
                self.member.replset_name,
                self.member.state,
                self.member.client.port))

            latest_entries = list(
                profile.find().sort([('$natural', -1)]).limit(1))

            if latest_entries:
                ts = latest_entries[0].get('ts', datetime.datetime.min)
            else:
                ts = datetime.datetime.min

            while True:
                # Make a tailable cursor. Filter out old entries, getMores,
                # serverStatus, commands from mongos, and this query itself.
                cursor = profile.find({
                    'ts': {'$gt': ts},
                    'op': {'$ne': 'getmore'},
                    'command.serverStatus': {'$ne': 1},
                    'ns': {'$nin': [
                        'test.system.profile', 'test.system.indexes']},
                }, tailable=True, await_data=True)

                while cursor.alive:
                    for doc in cursor:
                        if doc.get('op') == 'query':
                            ns = doc.get('ns', '')
                            query = json.dumps(doc.get('query', {}))
                            extra = '%s %s' % (ns, query)
                        elif doc.get('op') == 'command':
                            # This is why we had to set document_class=SON
                            # above: command name is first field.
                            command_name, arg = doc['command'].items()[0]
                            extra = '%s: %s' % (command_name, arg)
                        else:
                            extra = ''

                        values = {
                            'replset_name': self.member.replset_name,
                            'state': self.member.state,
                            'port': self.member.client.port,
                            'op': doc.get('op', ''),
                            'extra': extra,
                            'read_pref': doc.get('$read_preference', '')
                        }

                        message = (
                            '%(replset_name)s %(state)s on %(port)d:'
                            ' %(op)s %(extra)s %(read_pref)s\n'
                            % values)

                        # Unlike print(), this style avoids interleaving
                        # threads' output.
                        sys.stdout.write(self.member.color + message)

                # Cursor died; e.g. if profile is empty.
                sys.stdout.write('Cursor died\n')
                sleep(0.1)

    threads = []
    for member in members:
        t = ProfileThread(member)
        t.start()
        threads.append(t)

    while True:
        try:
            sleep(1)
        except KeyboardInterrupt:
            sys.exit(0)


def main():
    members = connect()
    enable_profiling(members)
    tail_profiles(members)


if __name__ == '__main__':
    main()
