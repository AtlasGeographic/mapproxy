Caches
######

.. versionadded:: 1.2.0

MapProxy supports multiple backends to store the internal tiles. The default backend is file based and does not require any further configuration.


Configuration
=============

You can configure a backend for each cache with the ``cache`` option.
Each backend has a ``type`` and one or more options.

.. code-block:: yaml

  caches:
    mycache:
      sources: [...]
      grids: [...]
      cache:
        type: backendtype
        backendoption1: value
        backendoption2: value

You may add a coverage definition to any cache with the ``coverage`` option under ``cache``.

.. code-block:: yaml

  caches:
    mycache:
      sources: [...]
      grids: [...]
      cache:
        type: backendtype
        backendoption1: value
        backendoption2: value
        coverage:
          bbox: [5, 50, 10, 55]
          srs: 'EPSG:4326'


The following backend types are available.


- :ref:`cache_file`
- :ref:`cache_mbtiles`
- :ref:`cache_sqlite`
- :ref:`cache_geopackage`
- :ref:`cache_couchdb`
- :ref:`cache_riak`
- :ref:`cache_redis`
- :ref:`cache_s3`
- :ref:`cache_azureblob`
- :ref:`cache_compact`

.. _cache_file:

``file``
========

This is the default cache type and it uses a single file for each tile. Available options are:

``directory_layout``:
  The directory layout MapProxy uses to store tiles on disk. Defaults to ``tc`` which uses a TileCache compatible directory layout (``zz/xxx/xxx/xxx/yyy/yyy/yyy.format``). ``mp`` uses a directory layout with less nesting (``zz/xxxx/xxxx/yyyy/yyyy.format```). ``tms`` uses TMS compatible directories (``zz/xxxx/yyyy.format``). ``quadkey`` uses Microsoft Virtual Earth or quadkey compatible directories (see http://msdn.microsoft.com/en-us/library/bb259689.aspx). ``arcgis`` uses a directory layout with hexadecimal row and column numbers that is compatible to ArcGIS exploded caches (``Lzz/Rxxxxxxxx/Cyyyyyyyy.format``).

  .. note::
    ``tms``, ``quadkey`` and ``arcgis`` layout are not suited for large caches, since it will create directories with thousands of files, which most file systems do not handle well.

``use_grid_names``:
  When ``true`` MapProxy will use the actual grid name in the path instead of the SRS code. E.g. tiles will be stored in ``./cache_data/mylayer/mygrid/`` instead of ``./cache_data/mylayer/EPSG1234/``.

  .. versionadded:: 1.5.0

.. _cache_file_directory:

``directory``:
  Directory where MapProxy should directly store the tiles. This will not add the cache name or grid name (``use_grid_name``) to the path. You can use this option to point MapProxy to an existing tile collection (created with ``gdal2tiles`` for example).

  .. versionadded:: 1.5.0

``tile_lock_dir``:
  Directory where MapProxy should write lock files when it creates new tiles for this cache. Defaults to ``cache_data/tile_locks``.

  .. versionadded:: 1.6.0

``image``:
  See :ref:`image_options` for options.

  .. versionadded:: 2.0.0

``directory_permissions``, ``file_permissions``:
  Permissions that MapProxy will set when creating files and directories. Must be given as string containing the octal representation of permissions. I.e. ``rwxrw-r--`` is ``'764'``. This will not work on windows OS.

  .. versionadded:: 3.1.0

.. _cache_mbtiles:

``mbtiles``
===========

Use a single SQLite file for this cache. It uses the `MBTile specification <http://mbtiles.org/>`_.

Available options:

``filename``:
  The path to the MBTiles file. Defaults to ``cachename.mbtiles``.

``tile_lock_dir``:
  Directory where MapProxy should write lock files when it creates new tiles for this cache. Defaults to ``cache_data/tile_locks``.

  .. versionadded:: 1.6.0


You can set the ``sources`` to an empty list, if you use an existing MBTiles file and do not have a source.

.. code-block:: yaml

  caches:
    mbtiles_cache:
      sources: []
      grids: [GLOBAL_MERCATOR]
      cache:
        type: mbtiles
        filename: /path/to/bluemarble.mbtiles

.. note::

  The MBTiles format specification does not include any timestamps for each tile and the seeding function is limited therefore. If you include any ``refresh_before`` time in a seed task, all tiles will be recreated regardless of the value. The cleanup process does not support any ``remove_before`` times for MBTiles and it always removes all tiles.
  Use the ``--summary`` option of the ``mapproxy-seed`` tool.

The note about ``bulk_meta_tiles`` for SQLite below applies to MBtiles as well.

``directory_permissions``, ``file_permissions``:
  Permissions that MapProxy will set when creating files and directories. Must be given as string containing the octal representation of permissions. I.e. ``rwxrw-r--`` is ``'764'``. This will not work on windows OS.

  .. versionadded:: 3.1.0

.. _cache_sqlite:

``sqlite``
===========

.. versionadded:: 1.6.0

Use SQLite databases to store the tiles, similar to ``mbtiles`` cache. The difference to ``mbtiles`` cache is that the ``sqlite`` cache stores each level into a separate database. This makes it easy to remove complete levels during mapproxy-seed cleanup processes. The ``sqlite`` cache also stores the timestamp of each tile.

Available options:

``dirname``:
  The directory where the level databases will be stored.

``tile_lock_dir``:
  Directory where MapProxy should write lock files when it creates new tiles for this cache. Defaults to ``cache_data/tile_locks``.

  .. versionadded:: 1.6.0

``ttl``:
  The time-to-live of each tile in the cache in seconds. Use 0 (default) to allow unlimited tile reuse.

.. code-block:: yaml

  caches:
    sqlite_cache:
      sources: [mywms]
      grids: [GLOBAL_MERCATOR]
      cache:
        type: sqlite
        directory: /path/to/cache


.. note::

  .. versionadded:: 1.10.0

  All tiles from a meta tile request are stored in one transaction into the SQLite file to increase performance. You need to activate the :ref:`bulk_meta_tiles <bulk_meta_tiles>` option to get the same benefit when you are using tiled sources.

  .. code-block:: yaml

    caches:
      sqlite_cache:
        sources: [mytilesource]
        bulk_meta_tiles: true
        grids: [GLOBAL_MERCATOR]
        cache:
          type: sqlite
          directory: /path/to/cache

``directory_permissions``, ``file_permissions``:
  Permissions that MapProxy will set when creating files and directories. Must be given as string containing the octal representation of permissions. I.e. ``rwxrw-r--`` is ``'764'``. This will not work on windows OS.

  .. versionadded:: 3.1.0

.. _cache_couchdb:

``couchdb``
===========

.. versionadded:: 1.3.0

Store tiles inside a `CouchDB <http://couchdb.apache.org/>`_. MapProxy creates a JSON document for each tile. This document contains metadata, like timestamps, and the tile image itself as a attachment.


Requirements
------------

Besides a running CouchDB you will need the `Python requests package <http://python-requests.org/>`_. You can install it the usual way, for example ``pip install requests``.

Configuration
-------------

You can configure the database and database name and the tile ID and additional metadata.

Available options:

``url``:
  The URL of the CouchDB server. Defaults to ``http://localhost:5984``.

``db_name``:
  The name of the database MapProxy uses for this cache. Defaults to the name of the cache.

``tile_lock_dir``:
  Directory where MapProxy should write lock files when it creates new tiles for this cache. Defaults to ``cache_data/tile_locks``.

  .. versionadded:: 1.6.0

``tile_id``:
  Each tile document needs a unique ID. You can change the format with a Python format string that expects the following keys:

  ``x``, ``y``, ``z``:
    The tile coordinate.

  ``grid_name``:
    The name of the grid.

  The default ID uses the following format::

    %(grid_name)s-%(z)d-%(x)d-%(y)d

  .. note:: You can't use slashes (``/``) in CouchDB IDs.

``tile_metadata``:
  MapProxy stores a JSON document for each tile in CouchDB and you can add additional key-value pairs  with metadata to each document.
  There are a few predefined values that MapProxy will replace with  tile-depended values, all other values will be added as they are.

  Predefined values:

  ``{{x}}``, ``{{y}}``, ``{{z}}``:
    The tile coordinate.

  ``{{timestamp}}``:
    The creation time of the tile as seconds since epoch. MapProxy will add a ``timestamp`` key for you, if you don't provide a custom timestamp key.

  ``{{utc_iso}}``:
    The creation time of the tile in UTC in ISO format. For example: ``2011-12-31T23:59:59Z``.

  ``{{tile_centroid}}``:
    The center coordinate of the tile in the cache's coordinate system as a list of long/lat or x/y values.

  ``{{wgs_tile_centroid}}``:
    The center coordinate of the tile in WGS 84 as a list of long/lat values.

Example
-------

.. code-block:: yaml

  caches:
    mycouchdbcache:
      sources: [mywms]
      grids: [mygrid]
      cache:
        type: couchdb
        url: http://localhost:9999
        db_name: mywms_tiles
        tile_metadata:
          mydata: myvalue
          tile_col: '{{x}}'
          tile_row: '{{y}}'
          tile_level: '{{z}}'
          created_ts: '{{timestamp}}'
          created: '{{utc_iso}}'
          center: '{{wgs_tile_centroid}}'



MapProxy will place the JSON document for tile z=3, x=1, y=2 at ``http://localhost:9999/mywms_tiles/mygrid-3-1-2``. The document will look like:


.. code-block:: json


  {
      "_attachments": {
          "tile": {
              "content_type": "image/png",
              "digest": "md5-ch4j5Piov6a5FlAZtwPVhQ==",
              "length": 921,
              "revpos": 2,
              "stub": true
          }
      },
      "_id": "mygrid-3-1-2",
      "_rev": "2-9932acafd060e10bc0db23231574f933",
      "center": [
          -112.5,
          -55.7765730186677
      ],
      "created": "2011-12-15T12:56:21Z",
      "created_ts": 1323953781.531889,
      "mydata": "myvalue",
      "tile_col": 1,
      "tile_level": 3,
      "tile_row": 2
  }


The ``_attachments``-part is the internal structure of CouchDB where the tile itself is stored. You can access the tile directly at: ``http://localhost:9999/mywms_tiles/mygrid-3-1-2/tile``.


.. _cache_riak:

``riak``
========

Support dropped after version 3.1.3 of MapProxy.


.. _cache_redis:

``redis``
=========

.. versionadded:: 1.10.0

Store tiles in a `Redis <https://redis.io/>`_ in-memory database. This backend is useful for short-term caching. Typical use-case is a small Redis cache that allows you to benefit from meta-tiling.

Your Redis database should be configured with ``maxmemory`` and ``maxmemory-policy`` options to limit the memory usage. For example::

  maxmemory 256mb
  maxmemory-policy volatile-ttl


Requirements
------------

You will need the `Python Redis client <https://pypi.org/project/redis>`_. You can install it in the usual way, for example with ``pip install redis``.

Configuration
-------------

Available options:

``host``:
    Host name of the Redis server. Defaults to ``127.0.0.1``.

``port``:
    Port of the Redis server. Defaults to ``6379``.

``db``:
    Number of the Redis database. Please refer to the Redis documentation. Defaults to `0`.

``username``:
  Optional authentication username. No defaults.

``password``:
  Optional authentication password. No defaults.

``prefix``:
    The prefix added to each tile-key in the Redis cache. Used to distinguish tiles from different caches and grids.  Defaults to ``cache-name_grid-name``.

``default_ttl``:
    The default Time-To-Live of each tile in the Redis cache in seconds. Defaults to 3600 seconds (1 hour).



Example
-------

.. code-block:: yaml

    redis_cache:
        sources: [mywms]
        grids: [mygrid]
        cache:
          type: redis
          username: mapproxy
          password: iamgreatpassword
          default_ttl: 600


.. _cache_geopackage:

``geopackage``
==============

.. versionadded:: 1.10.0

Store tiles in a `geopackage <http://www.geopackage.org/>`_ database. MapProxy creates a tile table if one isn't defined and populates the required meta data fields.
This backend is good for datasets that require portability.
Available options:

``filename``:
  The path to the geopackage file. Defaults to ``cachename.gpkg``.

``table_name``:
  The name of the table where the tiles should be stored (or retrieved if using an existing cache). Defaults to the ``cachename_gridname``.

``levels``:
  Set this to true to cache to a directory where each level is stored in a separate geopackage. Defaults to ``false``.
  If set to true, ``filename`` is ignored.

``directory``:
  If levels is true use this to specify the directory to store geopackage files.

You can set the ``sources`` to an empty list, if you use an existing geopackage file and do not have a source.

.. code-block:: yaml

  caches:
    geopackage_cache:
      sources: []
      grids: [GLOBAL_MERCATOR]
      cache:
        type: geopackage
        filename: /path/to/bluemarble.gpkg
        table_name: bluemarble_tiles

.. note::

  The geopackage format specification does not include any timestamps for each tile and the seeding function is limited therefore. If you include any ``refresh_before`` time in a seed task, all tiles will be recreated regardless of the value. The cleanup process does not support any ``remove_before`` times for geopackage and it always removes all tiles.
  Use the ``--summary`` option of the ``mapproxy-seed`` tool.


.. _cache_s3:

``s3``
======

.. versionadded:: 1.10.0

.. versionadded:: 1.11.0
  ``region_name``, ``endpoint_url`` and ``access_control_list``

Store tiles in a `Amazon Simple Storage Service (S3) <https://aws.amazon.com/s3/>`_ or any other S3 compatible object storage.


Requirements
------------

You will need the Python `boto3 <https://pypi.org/project/boto3>`_ package. You can install it in the usual way, for example with ``pip install boto3``.

Configuration
-------------

Available options:

``bucket_name``:
  The bucket used for this cache. You can set the default bucket with ``globals.cache.s3.bucket_name``.

``profile_name``:
  Optional profile name for `shared credentials <http://boto3.readthedocs.io/en/latest/guide/configuration.html>`_ for this cache. Alternative methods of authentification are using the  ``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY`` environmental variables, or by using an `IAM role <http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html>`_ when using an Amazon EC2 instance.
  You can set the default profile with ``globals.cache.s3.profile_name``.

``region_name``:
  Optional name of the region. You can set the default region_name with ``globals.cache.s3.region_name``

``endpoint_url``:
  Optional endpoint_url for the S3. You can set the default endpoint_url with ``globals.cache.s3.endpoint_url``.

``access_control_list``:
  Optional access control list for the S3. You can set the default access_control_list with ``globals.cache.s3.access_control_list``.

``directory``:
  Base directory (path) where all tiles are stored.

``directory_layout``:
  Defines the directory layout for the tiles (``12/12345/67890.png``, ``L12/R00010932/C00003039.png``, etc.).  See :ref:`cache_file` for available options. Defaults to ``tms`` (e.g. ``12/12345/67890.png``). This cache cache also supports ``reverse_tms`` where tiles are stored as ``y/x/z.format``. See *note* below.

``use_http_get``:
  When set to ``true``, requests to S3 ``GetObject`` will be fetched via urllib2 instead of boto, which decreases response times. Defaults to ``false``.

``include_grid_name``:
  When set to ``true``, the grid name will be included in the path in the bucket (``[directory]/[grid.name]/[z]/...``). Defaults to ``false``.

.. note::
  The hierarchical ``directory_layouts`` can hit limitations of AWS S3 if you are routinely processing 3500 or more requests per second. ``directory_layout: reverse_tms`` can work around this limitation. Please read `S3 Request Rate and Performance Considerations <http://docs.aws.amazon.com/AmazonS3/latest/dev/request-rate-perf-considerations.html>`_ for more information on this issue.

Example
-------

.. code-block:: yaml

  cache:
    my_layer_20110501_epsg_4326_cache_out:
      sources: [my_layer_20110501_cache]
      cache:
        type: s3
        directory: /1.0.0/my_layer/default/20110501/4326/
        bucket_name: my-s3-tiles-cache

  globals:
    cache:
      s3:
        profile_name: default


Example usage with DigitalOcean Spaces
--------------------------------------

.. code-block:: yaml

  cache:
    my_layer_20110501_epsg_4326_cache_out:
      sources: [my_layer_20110501_cache]
      cache:
        type: s3
        directory: /1.0.0/my_layer/default/20110501/4326/
        bucket_name: my-s3-tiles-cache

  globals:
    cache:
      s3:
        profile_name: default
        region_name: nyc3
        endpoint_url: https://nyc3.digitaloceanspaces.com
        access_control_list: public-read

.. _cache_azureblob:

``azureblob``
=============

.. versionadded:: to be released

Store tiles in `Azure Blob Storage <https://azure.microsoft.com/en-us/products/storage/blobs/>`_, Microsoft's object storage solution for the cloud.


Requirements
------------

You will need the `azure-storage-blob <https://pypi.org/project/azure-storage-blob/>`_ package. You can install it in the usual way, for example with ``pip install azure-storage-blob``.

Configuration
-------------

Available options:

``container_name``:
  The blob container used for this cache. You can set the default container with ``globals.cache.azureblob.container_name``.

``connection_string``:
  Credentials/url to connect and authenticate against Azure Blob storage. You can set the default connection_string with ``globals.cache.azureblob.connection_string`` or
  using the ``AZURE_STORAGE_CONNECTION_STRING`` environment variable. There are several ways to
  `authenticate against Azure Blob storage <https://learn.microsoft.com/en-us/azure/storage/common/storage-configure-connection-string>`_:

- Using the storage account key. This connection string can also found in the Azure Portal under the "Access Keys" section. For example:

::

    "DefaultEndpointsProtocol=https;AccountName=my-storage-account;AccountKey=my-key"

- Using a SAS token. For example:

::

    "BlobEndpoint=https://my-storage-account.blob.core.windows.net;SharedAccessSignature=sv=2015-04-05&sr=b&si=tutorial-policy-635959936145100803&sig=9aCzs76n0E7y5BpEi2GvsSv433BZa22leDOZXX%2BXXIU%3D"

- Using a local Azurite emulator, this is for TESTING purposes only. For example, using the default Azurite account:

::

    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://localhost:10000/devstoreaccount1"

``directory``:
  Base directory (path) where all tiles are stored.

``directory_layout``:
  Defines the directory layout for the tiles (``12/12345/67890.png``, ``L12/R00010932/C00003039.png``, etc.).  See :ref:`cache_file` for available options. Defaults to ``tms`` (e.g. ``12/12345/67890.png``). This cache cache also supports ``reverse_tms`` where tiles are stored as ``y/x/z.format``.

Example
-------

.. code-block:: yaml

  cache:
    my_layer_20110501_epsg_4326_cache_out:
      sources: [my_layer_20110501_cache]
      cache:
        type: azureblob
        directory: /1.0.0/my_layer/default/20110501/4326/
        container_name: my-azureblob-tiles-cache

  globals:
    cache:
      azureblob:
        connection_string: "DefaultEndpointsProtocol=https;AccountName=xxxx;AccountKey=xxxx"

.. _cache_compact:


``compact``
===========

.. versionadded:: 1.10.0
  Support for format version 1

.. versionadded:: 1.11.0
  Support for format version 2

Store tiles in ArcGIS compatible compact cache files. A single compact cache ``.bundle`` file stores up to about 16,000 tiles.

Version 1 of the compact cache format is compatible with ArcGIS 10.0 and the default version of ArcGIS 10.0-10.2. Version 2 is supported by ArcGIS 10.3 or higher.
Version 1 stores is one additional ``.bundlx`` index file for each ``.bundle`` data file.


Available options:

``directory``:
  Directory where MapProxy should store the level directories. This will not add the cache name or grid name to the path. You can use this option to point MapProxy to an existing compact cache.

``version``:
  The version of the ArcGIS compact cache format. This option is required. Either ``1`` or ``2``.

``directory_permissions``, ``file_permissions``:
  Permissions that MapProxy will set when creating files and directories. Must be given as string containing the octal representation of permissions. I.e. ``rwxrw-r--`` is ``'764'``. This will not work on windows OS.

  .. versionadded:: 3.1.0


You can set the ``sources`` to an empty list, if you use an existing compact cache files and do not have a source.


The following configuration will load tiles from ``/path/to/cache/L00/R0000C0000.bundle``, etc.

.. code-block:: yaml

  caches:
    compact_cache:
      sources: []
      grids: [webmercator]
      cache:
        type: compact
        version: 2
        directory: /path/to/cache

.. note::

  MapProxy does not support reading and writiting of the ``conf.cdi`` and ``conf.xml`` files. You need to configure a compatible MapProxy grid when you want to reuse exsting ArcGIS compact caches in MapProxy. You need to create or modify existing ``conf.cdi`` and ``conf.xml`` files when you want to use compact caches created with MapProxy in ArcGIS.


.. note::

  The compact cache format does not include any timestamps for each tile and the seeding function is limited therefore. If you include any ``refresh_before`` time in a seed task, all tiles will be recreated regardless of the value. The cleanup process does not support any ``remove_before`` times for compact caches and it always removes all tiles.
  Use the ``--summary`` option of the ``mapproxy-seed`` tool.


.. note::

  The compact cache format is append-only to allow parallel read and write operations.
  Removing or refreshing tiles with ``mapproxy-seed`` does not reduce the size of the cache files.
  You can use the :ref:`defrag-compact-cache <mapproxy_defrag_compact_cache>` util to reduce the file size of existing bundle files.
