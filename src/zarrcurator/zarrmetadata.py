"""
This module contains helpers for translating zarr v3 metadata (zarr.json) to zarr v2
metadata (.zgroup, .zarray, .zattrs), so that the chunks of zarr v3 stores can be
referenced by Kerchunk, which combines references in the zarr v2 layout.

The chunk bytes are referenced unchanged, so only codecs with a zarr v2 equivalent are
supported: the 'bytes' codec followed by at most one compressor. 'transpose' and chained
compressors raise a ValueError.

Sharded arrays ('sharding_indexed' codec) are translated to zarr v2 arrays of their inner
chunks: each shard ends (or starts) with an index of the offset and size of its inner
chunks, which is read to reference each inner chunk as a byte range within the shard.
The inner codecs follow the rules above; nested sharding raises a ValueError.
"""

#Standard modules
import logging
import math
import posixpath

#Non-Standard modules
import numpy as np

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

BLOSC_SHUFFLE = { 'noshuffle': 0, 'shuffle': 1, 'bitshuffle': 2 }

# Offset and size of an inner chunk that is not written, as it holds only the fill value
SHARD_EMPTY_CHUNK = 2**64 - 1


def v3CodecsToV2( codecs ):
    """Translate the codecs of a zarr v3 array to a zarr v2 compressor.

    Args:
            list[dict]: The 'codecs' of the zarr v3 array metadata.
    Returns:
            tuple: (endian, compressor), endian being 'little' or 'big' and compressor
            the zarr v2 compressor configuration or None.
    """
    endian = None
    compressor = None
    for codec in codecs:
        name = codec['name']
        conf = codec.get( 'configuration', {} ) or {}
        if name == 'bytes':
            endian = conf.get( 'endian', 'little' )
            continue
        if endian is None:
            # e.g. 'sharding_indexed' or 'transpose'
            raise ValueError( f"zarr v3 codec '{name}' has no zarr v2 equivalent" )
        if compressor is not None:
            raise ValueError( f"zarr v3 codec '{name}' after the compressor has no zarr v2 equivalent" )
        if name == 'zstd':
            compressor = { 'id': 'zstd', 'level': conf.get( 'level', 0 ), 'checksum': conf.get( 'checksum', False ) }
        elif name == 'gzip':
            compressor = { 'id': 'gzip', 'level': conf.get( 'level', 1 ) }
        elif name == 'blosc':
            compressor = { 'id': 'blosc', 'cname': conf['cname'], 'clevel': conf['clevel'],
                           'shuffle': BLOSC_SHUFFLE[ conf.get( 'shuffle', 'noshuffle' ) ],
                           'blocksize': conf.get( 'blocksize', 0 ) }
        elif name.startswith( 'numcodecs.' ):
            compressor = { 'id': name[ len( 'numcodecs.' ): ], **conf }
        else:
            raise ValueError( f"zarr v3 codec '{name}' has no zarr v2 equivalent" )
    if endian is None:
        raise ValueError( "zarr v3 array without 'bytes' codec has no zarr v2 equivalent" )
    return endian, compressor


def v3MetadataToV2( meta ):
    """Translate the zarr v3 metadata of a group or array to zarr v2 metadata files.

    The dimension names become the '_ARRAY_DIMENSIONS' attribute. xarray keeps the fill value
    in the '_FillValue' attribute of zarr v3 arrays, in zarr v2 it is the array's fill_value,
    which xarray reads as '_FillValue'. So an array without '_FillValue' and a zero fill value
    gets no fill value; zarr v2 reads missing chunks (not written as they hold only the fill
    value) as zeros then as well. A non-zero fill value is kept so missing chunks read correctly,
    though xarray then masks it.

    Args:
            dict: Content of a zarr v3 'zarr.json' file.
    Returns:
            dict: zarr v2 file name ('.zgroup', '.zarray', '.zattrs') -> content.
    """
    attrs = dict( meta.get( 'attributes', {} ) or {} )
    if meta.get( 'node_type' ) == 'group':
        return { '.zgroup': { 'zarr_format': 2 }, '.zattrs': attrs }

    chunk_grid = meta.get( 'chunk_grid', {} )
    if chunk_grid.get( 'name' ) != 'regular':
        raise ValueError( f"zarr v3 chunk grid '{chunk_grid.get( 'name' )}' has no zarr v2 equivalent" )
    chunks = chunk_grid['configuration']['chunk_shape']
    codecs = meta.get( 'codecs', [] )
    sharding = v3ShardingLayout( meta )
    if sharding is not None:
        # The zarr v2 chunks are the inner chunks of the shards
        chunks = sharding['chunk_shape']
        codecs = sharding['codecs']
    endian, compressor = v3CodecsToV2( codecs )
    dtype = np.dtype( meta['data_type'] ).newbyteorder( '<' if endian == 'little' else '>' ).str

    fill_value = meta.get( 'fill_value' )
    if '_FillValue' not in attrs:
        if fill_value in ( 0, False ):
            fill_value = None
        elif fill_value is not None:
            logger.warning("zarr v3 array without '_FillValue' has fill value %s, which xarray masks in zarr v2", fill_value)
    attrs.pop( '_FillValue', None )
    # zarr leaves out the dimension names of 0-d arrays, e.g. a 'crs' grid mapping variable
    dimension_names = meta.get( 'dimension_names' )
    if dimension_names is None and len( meta['shape'] ) == 0:
        dimension_names = []
    if dimension_names is not None:
        attrs['_ARRAY_DIMENSIONS'] = list( dimension_names )

    zarray = {
        'zarr_format': 2,
        'shape': meta['shape'],
        'chunks': chunks,
        'dtype': dtype,
        'compressor': compressor,
        'fill_value': fill_value,
        'order': 'C',
        'filters': None,
        'dimension_separator': '.',
    }
    return { '.zarray': zarray, '.zattrs': attrs }


def v3ShardingLayout( meta ):
    """Get the layout of the shards of a sharded zarr v3 array.

    Args:
            dict: Content of the zarr v3 'zarr.json' file of an array.
    Returns:
            dict or None: None for an array without sharding, else 'shape' (of the array),
            'shard_shape', 'chunk_shape' (of the inner chunks), 'codecs' (of the inner chunks),
            'index_location' ('start' or 'end'), 'index_endian', 'index_checksum' (bool) and
            'index_size' (bytes).
    """
    codecs = meta.get( 'codecs', [] )
    if not codecs or codecs[0]['name'] != 'sharding_indexed':
        return None
    if len( codecs ) > 1:
        # e.g. a compressor applied to the whole shard hides the byte ranges of the inner chunks
        raise ValueError( f"zarr v3 codec '{codecs[1]['name']}' after 'sharding_indexed' is not supported" )
    conf = codecs[0].get( 'configuration', {} )
    shard_shape = meta['chunk_grid']['configuration']['chunk_shape']
    chunk_shape = conf['chunk_shape']
    if any( s % c for s, c in zip( shard_shape, chunk_shape ) ):
        raise ValueError( f"Shard shape {shard_shape} is not a multiple of the inner chunk shape {chunk_shape}" )

    index_endian = None
    index_checksum = False
    for codec in conf.get( 'index_codecs', [] ):
        if codec['name'] == 'bytes' and index_endian is None:
            index_endian = ( codec.get( 'configuration', {} ) or {} ).get( 'endian', 'little' )
        elif codec['name'] == 'crc32c' and index_endian is not None and not index_checksum:
            index_checksum = True
        else:
            raise ValueError( f"Shard index codec '{codec['name']}' is not supported" )
    if index_endian is None:
        raise ValueError( "Shard index without 'bytes' codec is not supported" )

    num_chunks = math.prod( s // c for s, c in zip( shard_shape, chunk_shape ) )
    return {
        'shape': meta['shape'],
        'shard_shape': shard_shape,
        'chunk_shape': chunk_shape,
        'codecs': conf.get( 'codecs', [] ),
        'index_location': conf.get( 'index_location', 'end' ),
        'index_endian': index_endian,
        'index_checksum': index_checksum,
        'index_size': 16 * num_chunks + ( 4 if index_checksum else 0 ),
    }


def shardChunkReferences( shard_ref, shard_key, layout, read_range ):
    """Get the references of the inner chunks of a shard.

    Args:
            list: Reference of the shard, [url, offset, size].
            str: Dot-separated zarr v2 key of the shard, relative to the array, e.g. '1.0'.
            dict: Layout of the shards, see v3ShardingLayout().
            callable: read_range(url, start, end) returning the bytes in [start, end) of url.
    Returns:
            list[tuple]: (dot-separated key of the inner chunk relative to the array, [url, offset, size])
            for every inner chunk in the shard that is written and lies within the array.
    Raises:
            ValueError: If the checksum of the shard index does not match.
    """
    url, offset, size = shard_ref
    index_size = layout['index_size']
    if layout['index_location'] == 'end':
        index = read_range( url, offset + size - index_size, offset + size )
    else:
        index = read_range( url, offset, offset + index_size )
    if layout['index_checksum']:
        from numcodecs import CRC32C
        try:
            index = bytes( CRC32C().decode( index ) )
        except RuntimeError as exp:
            raise ValueError( f"Shard index checksum mismatch for shard {shard_key} in {url}" ) from exp
    entries = np.frombuffer( index, dtype=( '<' if layout['index_endian'] == 'little' else '>' ) + 'u8' ).reshape( -1, 2 )

    chunks_per_shard = [ s // c for s, c in zip( layout['shard_shape'], layout['chunk_shape'] ) ]
    grid = [ math.ceil( s / c ) for s, c in zip( layout['shape'], layout['chunk_shape'] ) ]
    shard_coord = [ int( i ) for i in shard_key.split( '.' ) ] if layout['shape'] else []
    references = []
    for local_coord, ( chunk_offset, chunk_size ) in zip( np.ndindex( *chunks_per_shard ), entries ):
        if chunk_offset == SHARD_EMPTY_CHUNK and chunk_size == SHARD_EMPTY_CHUNK:
            continue
        coord = [ shard * per_shard + local for shard, per_shard, local in zip( shard_coord, chunks_per_shard, local_coord ) ]
        # Inner chunks of edge shards may lie beyond the array
        if any( c >= g for c, g in zip( coord, grid ) ):
            continue
        key = '.'.join( str( c ) for c in coord ) or '0'
        references.append( ( key, [ url, offset + int( chunk_offset ), int( chunk_size ) ] ) )
    return references


def v3ChunkKeyToV2( chunk_key, chunk_key_encoding ):
    """Translate a chunk key of a zarr v3 array, relative to the array, to the dot-separated zarr v2 form.

    Args:
            str: Chunk key, e.g. 'c/0/1' or 'c.0.1' ('default' encoding) or '0/1' ('v2' encoding).
            dict: The 'chunk_key_encoding' of the zarr v3 array metadata.
    Returns:
            str: zarr v2 chunk key, e.g. '0.1'.
    """
    if chunk_key_encoding.get( 'name', 'default' ) == 'default':
        # 'c' followed by the separator, or just 'c' for a 0-d array
        chunk_key = chunk_key[1:].lstrip( './' ) or '0'
    return chunk_key.replace( posixpath.sep, '.' )
