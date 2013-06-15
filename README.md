Real-time Profiling a MongoDB Cluster
=====================================

In a sharded cluster of replica sets, which server or servers handle each of your queries? What about each insert, update, or command? How these operations are routed is influenced by your choice of shard key, the type of operation, and your read preference. It'd be great if we could **see** where each operation goes. We could experiment with queries to refine our understanding of how MongoDB scales.

Let's set up a cluster and use the system profiler to watch its behavior. This is an interactive, experimental way of learning how your cluster really behaves.

***

# Setup

You'll need a recent install of MongoDB (I'm using 2.4.4), Python, a recent version of [PyMongo](https://pypi.python.org/pypi/pymongo/) (at least 2.4&mdash;I'm using 2.5.2) and the code in [my cluster-profile repository on GitHub](https://github.com/ajdavis/cluster-profile). If you install the [Colorama](https://pypi.python.org/pypi/colorama) Python package we'll get cute colored output. These scripts were tested on my Mac.

## Sharded cluster of replica sets

Run the `cluster_setup.py` script in my repository. It sets up a standard sharded cluster for you running on your local machine. There's a `mongos`, three config servers, and two shards, each of which is a three-member replica set. The first shard's replica set is running on ports 4000 through 4002, the second shard is on ports 5000 through 5002, and the three config servers are on ports 6000 through 6002:

![The setup](https://raw.github.com/ajdavis/cluster-profile/master/_static/setup.png "The setup")

For the finale, `cluster_setup.py` makes a collection named `sharded_collection`, sharded on a key named `shard_key`.

In a normal deployment, we'd let MongoDB's [balancer](http://docs.mongodb.org/manual/core/sharded-clusters/#sharding-balancing) automatically distribute chunks of data among our two shards. But for this demo we want documents to be on predictable shards, so my script disables the balancer. It makes a chunk for all documents with `shard_key` less than 500 and another chunk for documents with `shard_key` greater than or equal to 500. It moves the high chunk to `replset_1`:

```python
client = MongoClient()  # Connect to mongos.
admin = client.admin  # admin database.

# Pre-split.
admin.command(
    'split', 'test.sharded_collection',
    middle={'shard_key': 500})

admin.command(
    'moveChunk', 'test.sharded_collection',
    find={'shard_key': 500},
    to='replset_1')
```

If you connect to `mongos` with the MongoDB shell, `sh.status()` shows there's one chunk on each of the two shards:

```javascript
{ "shard_key" : { "$minKey" : 1 } } -->> { "shard_key" : 500 } on : replset_0 { "t" : 2, "i" : 1 }
{ "shard_key" : 500 } -->> { "shard_key" : { "$maxKey" : 1 } } on : replset_1 { "t" : 2, "i" : 0 }
```

The setup script also inserts a document with a `shard_key` of 0 and another with a `shard_key` of 500. Now we're ready for some profiling.

## Profiling

Run the `tail_profile.py` script from my repository. It connects to all the replica set members and sets the profiling level to 2 ("log everything") on the `test` database, and creates a [tailable cursor](http://docs.mongodb.org/manual/tutorial/create-tailable-cursor/) on the `system.profile` collection. The script filters out some noise in the profile collection&mdash;for example, the activities of the tailable cursor show up in the `system.profile` collection that it's tailing. Any legitimate entries in the profile are spat out to the console in pretty colors.

# Experiments

## Targeted queries versus scatter-gather

Let's run a query from Python in a separate terminal:

```
>>> from pymongo import MongoClient
>>> collection = MongoClient().test.sharded_collection
>>> collection.find_one({'shard_key': 0})
{'_id': ObjectId('51bb6f1cca1ce958c89b348a'), 'shard_key': 0}
```

`tail_profile.py` prints:

<span style="font-family:mono; color: aqua">replset\_0 primary on 4000: query test.sharded\_collection {"shard\_key": 0}</span><br>

The query includes the shard key, so `mongos` targets it to the shard that can satisfy it. What about a query that doesn't contain the shard key?:

```
>>> collection.find_one({})
```

`mongos` sends the query to both shards:

<span style="font-family:mono; color: aqua">replset\_0 primary on 4000: query test.sharded\_collection {"shard\_key": 0}</span><br>
<span style="font-family:mono; color:red">replset\_1 primary on 5000: query test.sharded\_collection {"shard\_key": 500}</span>

## Queries with read preference

We can use [read preferences](http://emptysqua.re/blog/reading-from-mongodb-replica-sets-with-pymongo/) to target a query to secondaries:

```
>>> from pymongo.read_preferences import ReadPreference
>>> collection.find_one({}, read_preference=ReadPreference.SECONDARY)
```

<span style="font-family:mono; color: green">replset\_0 secondary on 4001: query test.sharded\_collection {"$readPreference": {"mode": "secondary"}, "$query": {}}</span><br>
<span style="font-family:mono">replset\_1 secondary on 5001: query test.sharded\_collection {"$readPreference": {"mode": "secondary"}, "$query": {}}</span>

Note how PyMongo passes the read preference to `mongos` in the `$readPreference` part of the query. `mongos` targets one secondary in each of the two replica sets.

## Updates

With a sharded collection, updates must include the shard key or be "multi-updates". An update with the shard key goes to the proper shard, of course:

```
>>> collection.update({'shard_key': -100}, {'$set': {'field': 'value'}})
```

<span style="font-family:mono; color: aqua">replset\_0 primary on 4000: update test.sharded\_collection {"shard\_key": -100}</span>

And a multi-update hits all shards:

```
>>> collection.update({}, {'$set': {'field': 'value'}}, multi=True)
```

<span style="font-family:mono; color: aqua">replset\_0 primary on 4000: update test.sharded\_collection {}</span><br>
<span style="font-family:mono; color: red">replset\_1 primary on 5000: update test.sharded\_collection {}</span>

A multi-update on a range of the shard key need only involve the proper shard:

```
>>> collection.update({'shard_key': {'$gt': 1000}}, {'$set': {'field': 'value'}}, multi=True)
```

<span style="font-family:mono; color: red">replset\_1 primary on 5000: update test.sharded\_collection {"shard\_key": {"$gt": 1000}}</span>

## Commands

In version 2.4, `mongos` can use secondaries not only for queries, but also for [some commands](http://docs.mongodb.org/manual/core/read-preference/#database-commands). You can run `count` on secondaries if you pass the right read preference:

```
>>> collection.find(read_preference=ReadPreference.SECONDARY).count()
```

<span style="font-family:mono; color: aqua">replset\_0 primary on 4000: command count: sharded\_collection</span><br>
<span style="font-family:mono; color: red">replset\_1 primary on 5000: command count: sharded\_collection</span>

Whereas `findAndModify`, since it modifies data, is run on the primaries no matter your read preference:

```
>>> db = MongoClient().test
>>> test.command(
...     'findAndModify',
...     'sharded_collection',
...     query={'shard_key': -1},
...     remove=True,
...     read_preference=ReadPreference.SECONDARY)
```

<span style="font-family:mono; color: aqua">replset\_0 primary on 4000: command findAndModify: sharded\_collection</span>

# Conclusion, Further Steps

To scale a sharded cluster, it helps to understand how operations are distributed: are they scatter-gather, or targeted to one shard? Do they run on primaries or secondaries? If you set up a cluster and test your queries interactively like we did here, you can see how your cluster behaves in practice. When you're designing your schema, shard keys, and read preferences, gaining this understanding early will guide you to scalable solutions.
