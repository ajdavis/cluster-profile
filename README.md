Real-time Profiling a MongoDB Cluster
=====================================

In a sharded cluster of replica sets, which server or servers handle each of your queries? What about each insert, update, or command? How these operations are routed is influenced by your shard key, the type of operation, and your read preference. I'll show you how to watch your cluster and see which server executes each operation, using the system profiler. This is an interactive, experimental way of learning how your cluster really behaves. You can use it to refine your intuition for exactly how MongoDB scales.

***

# Setup

You'll need a recent install of MongoDB (I'm using 2.4.4), Python, a recent version of PyMongo (at least 2.4--I'm using 2.5.2) and the code in THIS REPOSITORY. I assume a Mac, Linux, or Unix-y environment where commands like `killall` are available.

GITHUB LINK

## Sharded cluster of replica sets

I've written a script to do this setup for you, it's in LINK HERE

We're going to start off with a standard MongoDB sharded cluster, comprising a `mongos`, two shards with three replicas of each, and three config servers. You can run the whole thing on a laptop using a different port for each server. I'm going to run shard zero's replica set on ports 4000 through 4002, shard 1's on ports 5000 through 5002, and the three config servers on ports 6000 through 6002:

IMAGE HERE

## Shard a collection



## Profile collection

## tail_profile.py

Note this is only for one DB at a time right now. Note also limitations in profiling secondaries.

# Experiments

## Queries

Read preference, shard key. Diff b/w find and findOne.

## Updates

## Commands

# Conclusion, Further Steps
