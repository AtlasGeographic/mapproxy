# This file is part of the MapProxy project.
# Copyright (C) 2016-2017 Omniscale <http://omniscale.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import errno
import hashlib
import os
import shutil
import struct
import io

from mapproxy.image import ImageSource
from mapproxy.cache.base import TileCacheBase, tile_buffer
from mapproxy.util.fs import ensure_directory, write_atomic
from mapproxy.util.lock import FileLock
from mapproxy.compat import BytesIO

from google.cloud import storage
from google.cloud.storage.fileio import BlobReader
from google.cloud.storage.fileio import BlobWriter

import logging
log = logging.getLogger(__name__)

BUNDLE_EXT = '.bundle'
BUNDLEX_V1_EXT = '.bundlx'

INT64LE = struct.Struct('<Q')

BUNDLE_V2_GRID_WIDTH = 128
BUNDLE_V2_GRID_HEIGHT = 128
BUNDLE_V2_TILES = BUNDLE_V2_GRID_WIDTH * BUNDLE_V2_GRID_HEIGHT
BUNDLE_V2_INDEX_SIZE = BUNDLE_V2_TILES * 8

BUNDLE_V2_HEADER = (
    3,                          # Version
    BUNDLE_V2_TILES,            # numRecords
    0,                          # maxRecord Size
    5,                          # Offset Size
    0,                          # Slack Space
    64 + BUNDLE_V2_INDEX_SIZE,  # File Size
    40,                         # User Header Offset
    20 + BUNDLE_V2_INDEX_SIZE,  # User Header Size
    3,                          # Legacy 1
    16,                         # Legacy 2 0?
    BUNDLE_V2_TILES,            # Legacy 3
    5,                          # Legacy 4
    BUNDLE_V2_INDEX_SIZE        # Index Size
)
BUNDLE_V2_HEADER_STRUCT_FORMAT = '<4I3Q6I'
BUNDLE_V2_HEADER_SIZE = 64


class CompactCacheGCS(TileCacheBase):
    supports_timestamp = False
    bundle_class = None

    def __init__(self, cache_dir, bucket_name, credential_file):
        self.lock_cache_id = 'compactgcscache-' + hashlib.md5(cache_dir.encode('utf-8')).hexdigest()
        self.cache_dir = cache_dir
        self.client = storage.Client.from_service_account_json(credential_file)
        self.bucket = self.client.bucket(bucket_name)
        self.bundle_class = BundleV2

    def _get_bundle_fname_and_offset(self, tile_coord):
        x, y, z = tile_coord

        level_dir = os.path.join(self.cache_dir, 'L%02d' % z).lstrip('/')

        c = x // BUNDLE_V2_GRID_WIDTH * BUNDLE_V2_GRID_WIDTH
        r = y // BUNDLE_V2_GRID_HEIGHT * BUNDLE_V2_GRID_HEIGHT

        basename = 'R%04xC%04x' % (r, c)
        return os.path.join(level_dir, basename), (c, r)

    def _get_bundle(self, tile_coord):
        bundle_fname, offset = self._get_bundle_fname_and_offset(tile_coord)
        return self.bundle_class(bundle_fname, self.bucket, self.client, offset=offset)

    def is_cached(self, tile, dimensions=None):
        if tile.coord is None:
            return True
        if tile.source:
            return True

        return self._get_bundle(tile.coord).is_cached(tile, dimensions=dimensions)

    def store_tile(self, tile, dimensions=None):
        if tile.stored:
            return True

        return self._get_bundle(tile.coord).store_tile(tile, dimensions=dimensions)

    def store_tiles(self, tiles, dimensions=None):
        if len(tiles) > 1:
            # Check if all tiles are from a single bundle.
            bundle_files = set()
            tile_coord = None
            for t in tiles:
                if t.stored:
                    continue
                bundle_files.add(self._get_bundle_fname_and_offset(t.coord)[0])
                tile_coord = t.coord
            if len(bundle_files) == 1:
                return self._get_bundle(tile_coord).store_tiles(tiles, dimensions=dimensions)

        # Tiles are across multiple bundles
        failed = False
        for tile in tiles:
            if not self.store_tile(tile, dimensions=dimensions):
                failed = True
        return not failed


    def load_tile(self, tile, with_metadata=False, dimensions=None):
        if tile.source or tile.coord is None:
            return True

        return self._get_bundle(tile.coord).load_tile(tile, dimensions=dimensions)

    def load_tiles(self, tiles, with_metadata=False, dimensions=None):
        if len(tiles) > 1:
            # Check if all tiles are from a single bundle.
            bundle_files = set()
            tile_coord = None
            for t in tiles:
                if t.source or t.coord is None:
                    continue
                bundle_files.add(self._get_bundle_fname_and_offset(t.coord)[0])
                tile_coord = t.coord
            if len(bundle_files) == 1:
                return self._get_bundle(tile_coord).load_tiles(tiles, dimensions=dimensions)

        # No support_bulk_load or tiles are across multiple bundles
        missing = False
        for tile in tiles:
            if not self.load_tile(tile, with_metadata=with_metadata, dimensions=dimensions):
                missing = True
        return not missing

    def remove_tile(self, tile, dimensions=None):
        if tile.coord is None:
            return True

        return self._get_bundle(tile.coord).remove_tile(tile, dimensions=dimensions)

    def load_tile_metadata(self, tile, dimensions=None):
        if self.load_tile(tile, dimensions=dimensions):
            tile.timestamp = -1

    def remove_level_tiles_before(self, level, timestamp):
        if timestamp == 0:
            level_dir = os.path.join(self.cache_dir, 'L%02d' % level)
            shutil.rmtree(level_dir, ignore_errors=True)
            return True
        return False




class BundleV2(object):
    def __init__(self, base_filename, bucket, client, offset=None):
        # offset not used by V2
        self.filename = base_filename + '.bundle'
        self.lock_filename = base_filename + '.lck'
        self.bucket = bucket
        self.client = client

        # defer initialization to update/remove calls to avoid
        # index creation on is_cached (prevents new files in read-only caches)
        self._initialized = False

    def _init_index(self):
        self._initialized = True
        blob = self.bucket.blob(self.filename)
        if blob.exists():
            return
        #if os.path.exists(self.filename):
        #    return
        #ensure_directory(self.filename)
        with blob.open('wb') as f:
            buf = BytesIO()
            buf.write(struct.pack(BUNDLE_V2_HEADER_STRUCT_FORMAT, *BUNDLE_V2_HEADER))
            # Empty index (ArcGIS stores an offset of 4 and size of 0 for missing tiles)
            buf.write(struct.pack('<%dQ' % BUNDLE_V2_TILES, *(4, ) * BUNDLE_V2_TILES))
            f.write(buf.getvalue())
            #write_atomic(self.filename, buf.getvalue())

    def _tile_idx_offset(self, x, y):
        return BUNDLE_V2_HEADER_SIZE + (x + BUNDLE_V2_GRID_HEIGHT * y) * 8

    def _rel_tile_coord(self, tile_coord):
        return (tile_coord[0] % BUNDLE_V2_GRID_WIDTH,
                tile_coord[1] % BUNDLE_V2_GRID_HEIGHT, )

    def _tile_offset_size(self, fh, x, y):
        idx_offset = self._tile_idx_offset(x, y)
        buffer = io.BytesIO()
        fh.download_to_file(buffer, start=idx_offset, end= idx_offset + 8)
        buffer.seek(0)
        #fh.seek(idx_offset)
        #val = INT64LE.unpack(fh.read(8))[0]
        val = INT64LE.unpack(buffer.read(8))[0]
        # Index contains 8 bytes per tile.
        # Size is stored in 24 most significant bits.
        # Offset in the least significant 40 bits.
        size = val >> 40
        if size == 0:
            return 0, 0
        offset = val - (size << 40)
        return offset, size

    def _load_tile(self, fh, tile, dimensions=None):
        if tile.source or tile.coord is None:
            return True

        x, y = self._rel_tile_coord(tile.coord)
        offset, size = self._tile_offset_size(fh, x, y)
        if not size:
            return False

        #fh.seek(offset)
        #data = fh.read(size)
        buffer = io.BytesIO()
        fh.download_to_file(buffer, start=offset, end= offset + size)
        buffer.seek(0)
        data = buffer.read()


        tile.source = ImageSource(BytesIO(data))
        return True

    def load_tile(self, tile, with_metadata=False, dimensions=None):
        if tile.source or tile.coord is None:
            return True

        return self.load_tiles([tile], with_metadata, dimensions=dimensions)

    def load_tiles(self, tiles, with_metadata=False, dimensions=None):
        missing = False

        with self._readonly() as fh:
            if not fh:
                return False

            for t in tiles:
                if t.source or t.coord is None:
                    continue
                if not self._load_tile(fh, t):
                    missing = True

        return not missing

    def is_cached(self, tile, dimensions=None):
        with self._readonly() as fh:
            if not fh:
                return False

            x, y = self._rel_tile_coord(tile.coord)
            _, size = self._tile_offset_size(fh, x, y)
            if not size:
                return False
            return True

    def _update_tile_offset(self, fh, x, y, offset, size):
        idx_offset = self._tile_idx_offset(x, y)
        val = offset + (size << 40)

        fh.seek(idx_offset, os.SEEK_SET)
        fh.write(INT64LE.pack(val))

    def _append_tile(self, fh, data):
        # Write tile size first, then tile data.
        # Offset points to actual tile data.
        fh.seek(0, os.SEEK_END)
        fh.write(struct.pack('<L', len(data)))
        offset = fh.tell()
        fh.write(data)
        return offset

    def _update_metadata(self, fh, filesize, tilesize):
        # Max record/tile size
        fh.seek(8)
        old_tilesize = struct.unpack('<I', fh.read(4))[0]
        if tilesize > old_tilesize:
            fh.seek(8)
            fh.write(struct.pack('<I', tilesize))

        # Complete file size
        fh.seek(24)
        fh.write(struct.pack("<Q", filesize))

    def _store_tile(self, fh, tile_coord, data, dimensions=None):
        size = len(data)
        x, y = self._rel_tile_coord(tile_coord)
        offset = self._append_tile(fh, data)
        self._update_tile_offset(fh, x, y, offset, size)

        filesize = offset + size
        self._update_metadata(fh, filesize, size)

    def store_tile(self, tile, dimensions=None):
        if tile.stored:
            return True

        return self.store_tiles([tile], dimensions=dimensions)

    def store_tiles(self, tiles, dimensions=None):
        self._init_index()

        tiles_data = []
        for t in tiles:
            if t.stored:
                continue
            with tile_buffer(t) as buf:
                data = buf.read()
            tiles_data.append((t.coord, data))

        with FileLock(self.lock_filename):
            with self._readwrite() as fh:
                for tile_coord, data in tiles_data:
                    self._store_tile(fh, tile_coord, data, dimensions=dimensions)

        return True


    def remove_tile(self, tile, dimensions=None):
        if tile.coord is None:
            return True

        self._init_index()
        with FileLock(self.lock_filename):
            with self._readwrite() as fh:
                x, y = self._rel_tile_coord(tile.coord)
                self._update_tile_offset(fh, x, y, 0, 0)

        return True

    def size(self):
        total_size = 0
        with self._readonly() as fh:
            if not fh:
                return 0, 0
            for y in range(BUNDLE_V2_GRID_HEIGHT):
                for x in range(BUNDLE_V2_GRID_WIDTH):
                    _, size = self._tile_offset_size(fh, x, y)
                    if size:
                        total_size += size + 4
            #fh.seek(0, os.SEEK_END)
            #actual_size = fh.tell()
            actual_size=fh.size
            return total_size + 64 + BUNDLE_V2_INDEX_SIZE, actual_size
    @contextlib.contextmanager
    def _readonly(self):
        try:
            blob = self.bucket.get_blob(self.filename)
            if blob == None:
                raise errno.ENOENT
            if blob.exists() == False:
                raise errno.ENOENT
            yield blob #  BlobReader(blob)
            #with blob.open('rb') as fh:
                #yield fh
            #with open(self.filename, 'rb') as fh:
            #    yield fh
        except IOError as ex:
            if ex.errno == errno.ENOENT:
                # missing bundle file -> missing tile
                yield None
            else:
                raise ex

    @contextlib.contextmanager
    def _readwrite(self):
        self._init_index()
        blob = self.bucket(self.filename)
        yield BlobWriter(blob)
        #with blob.open('r+b') as fh:
        #    yield fh
        #with open(self.filename, 'r+b') as fh:
        #    yield fh
