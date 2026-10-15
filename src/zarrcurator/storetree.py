"""
This module contains helpers for walking the group hierarchy of a zarr store,
e.g. a store written from an xarray DataTree, with nested groups.
"""

#Standard modules
import json
import os
import posixpath


def isZarrGroupDir( path, fs=None ):
    """Check whether a directory is a zarr group.

    A zarr v2 group holds a '.zgroup' file, a zarr v3 group a 'zarr.json' file
    with node_type 'group'. Array directories and plain directories are not groups.

    Args:
            path[str]: Path of the directory.
            fs[object]: fsspec file system object for object stores, None for local stores.
    Returns:
            bool: True if the directory is a zarr group.
    """
    join = posixpath.join if fs is not None else os.path.join
    exists = fs.isfile if fs is not None else os.path.isfile
    if exists( join( path, '.zgroup' ) ):
        return True
    meta_path = join( path, 'zarr.json' )
    if not exists( meta_path ):
        return False
    try:
        if fs is not None:
            meta = json.loads( fs.cat_file( meta_path ) )
        else:
            with open( meta_path, 'rb' ) as f:
                meta = json.load( f )
    except ( OSError, ValueError ):
        return False
    return meta.get( 'node_type' ) == 'group'


def listArrayPaths( group ):
    """List the paths of all arrays in a zarr group and its sub groups.

    Works for zarr v2 and v3 groups, with or without consolidated metadata.

    Args:
            group[zarr.Group]: Opened zarr group, usually the root of the store.
    Returns:
            list[str]: Sorted array paths relative to the group, e.g. ['time', 'z2/ocean/sst'].
    """
    import zarr

    return sorted( path for path, node in group.members( max_depth=None ) if isinstance( node, zarr.Array ) )


def groupAncestors( path ):
    """List the groups enclosing a store member, from the root down.

    Args:
            path[str]: Path of the member relative to the store root, e.g. 'z2/ocean/sst'.
    Returns:
            list[str]: Group paths relative to the store root, '' being the root,
            e.g. ['', 'z2', 'z2/ocean'].
    """
    parts = path.replace( os.path.sep, '/' ).strip( '/' ).split( '/' )[:-1]
    return [ '/'.join( parts[:depth] ) for depth in range( len( parts ) + 1 ) ]


DIAG_METADATA_NAMES = { '.zgroup', '.zattrs', '.zarray', '.zmetadata', 'zarr.json' }
"""set: Names of the zarr metadata files recorded in a diagnosis."""

DIAG_GROUP_TOTAL = '__total__'
"""str: Key of the totals of a group in a nested diagnosis. Names starting with '__'
are reserved in zarr v3, so the key does not clash with an array or group name."""


def nestDiagReport( flatDiag ):
    """Nest a diagnosis keyed by entry path by its groups, as for the '.check' report.

    ``{store: {"z2/ocean/sst": {...}, "size": N, "count": N}}`` becomes
    ``{store: {"z2": {"ocean": {"sst": {...}}}, "size": N, "count": N}}``.
    Entries are marked with ``"type": "array"``, or ``"type": "file"`` for metadata
    files such as ``zarr.json``, and carry their ``path``; all other dicts are groups.
    Each group holds the totals of its entries and sub groups under ``"__total__"``,
    e.g. ``{"size": N, "count": N}``; the totals of each store (``size``, ``count``)
    stay at the store level.

    Args:
            flatDiag[dict]: Diagnosis keyed by store, then by entry path from the store root.
    Returns:
            dict: Diagnosis keyed by store, then nested by group.
    """

    nested = {}
    for store, entries in flatDiag.items():
        storeNode = nested[store] = {}
        for path, entry in entries.items():
            if not isinstance( entry, dict ):  # store totals
                storeNode[path] = entry
                continue
            parts = [ p for p in path.replace( os.path.sep, '/' ).split( '/' ) if p ]
            node = storeNode
            for group in parts[:-1]:
                node = node.setdefault( group, {} )
            entryType = 'file' if parts[-1] in DIAG_METADATA_NAMES else 'array'
            node[parts[-1]] = { 'type': entryType, 'path': '/'.join( parts ), **entry }
        for name, child in storeNode.items():
            if isinstance( child, dict ) and 'type' not in child:
                addGroupTotals( child )
    return nested


def addGroupTotals( group ):
    """Add the totals of a group of a nested diagnosis, including its sub groups.

    Args:
            group[dict]: Group of a nested diagnosis, updated in place.
    Returns:
            tuple: (size, count) of the group.
    """

    size, count = 0, 0
    for name, child in group.items():
        if not isinstance( child, dict ) or name == DIAG_GROUP_TOTAL:
            continue
        if 'type' in child:
            childSize, childCount = child.get( 'size', 0 ), child.get( 'count', 0 )
        else:
            childSize, childCount = addGroupTotals( child )
        size += childSize
        count += childCount
    # Put the totals first, so they lead the group in the written file
    members = { name: child for name, child in group.items() if name != DIAG_GROUP_TOTAL }
    group.clear()
    group[DIAG_GROUP_TOTAL] = { 'size': size, 'count': count }
    group.update( members )
    return size, count


def flattenDiagReport( nestedDiag ):
    """Flatten a diagnosis nested by group to one keyed by entry path.

    The inverse of nestDiagReport; a diagnosis that is already keyed by entry path
    (written by older versions) is returned unchanged.

    Args:
            nestedDiag[dict]: Diagnosis keyed by store, then nested by group.
    Returns:
            dict: Diagnosis keyed by store, then by entry path, e.g. ``z2/ocean/sst``.
    """

    def isEntry( node ):
        # Entries carry a 'type', entries of older flat files their size directly
        return 'type' in node or isinstance( node.get( 'size' ), ( int, float ) )

    flat = {}
    for store, storeNode in nestedDiag.items():
        storeFlat = flat[store] = {}

        def walk( node, prefix ):
            for name, child in node.items():
                if not isinstance( child, dict ) or name == DIAG_GROUP_TOTAL:
                    continue
                if isEntry( child ):
                    storeFlat[prefix + name] = { k: v for k, v in child.items() if k not in ( 'type', 'path' ) }
                else:
                    walk( child, f"{prefix}{name}/" )

        for name, value in storeNode.items():
            if not isinstance( value, dict ):  # store totals
                storeFlat[name] = value
        walk( storeNode, '' )
    return flat


def nestDistReport( flatDist, storePath ):
    """Nest the members of each subgroup of a distribution by their groups, as for the '.diag' file.

    The ``groupMembers`` of a subgroup, a list of ``[member, size]``, becomes a tree keyed by the
    path of each member from the store root, e.g. ``{"z2": {"ocean": {"sst": {...}}}}``. Members
    are given by their path from the store root or by absolute path (e.g. coordinate variables);
    a member that is the store itself (subgroup of type 'zarr') is keyed by the store name.
    Each member is marked with ``"type"`` ('store', 'array' or 'file') and carries its original
    name as ``path``, its ``size`` and its position in the list as ``index``, as the order of the
    members matters, e.g. the first member of a 'chunk' subgroup is the array to split. Each group
    holds the totals of its members under ``"__total__"``, e.g. ``{"size": N, "members": N}``.
    The other fields of the subgroups are kept as they are.

    Args:
            flatDist[dict]: Distribution keyed by frequency, then by subgroup, with the
                    subgroups as dictionaries (see subGroup_to_dict).
            storePath[str]: Path of the zarr store the members belong to.
    Returns:
            dict: Distribution with the members of each subgroup nested by group.
    """

    storePath = storePath.rstrip( '/' ).rstrip( os.path.sep )
    storeName = storePath.replace( os.path.sep, '/' ).split( '/' )[-1]

    def memberParts( member ):
        if member.rstrip( '/' ) == storePath:
            return [ storeName ], 'store'
        for prefix in ( storePath + '/', storePath + os.path.sep ):
            if member.startswith( prefix ):
                member = member[len( prefix ):]
                break
        parts = [ p for p in member.replace( os.path.sep, '/' ).split( '/' ) if p ]
        return parts, ( 'file' if parts[-1] in DIAG_METADATA_NAMES else 'array' )

    nested = {}
    for freq, subGroups in flatDist.items():
        nested[freq] = {}
        for subGroupID, subGroup in subGroups.items():
            tree = {}
            for index, ( member, size ) in enumerate( subGroup['groupMembers'] ):
                parts, memberType = memberParts( member )
                node = tree
                for group in parts[:-1]:
                    node = node.setdefault( group, {} )
                node[parts[-1]] = { 'type': memberType, 'path': member, 'size': size, 'index': index }
            for child in tree.values():
                if 'type' not in child:
                    addMemberTotals( child )
            nested[freq][subGroupID] = { **subGroup, 'groupMembers': tree }
    return nested


def addMemberTotals( group ):
    """Add the totals of a group of the members of a subgroup, including its sub groups.

    Args:
            group[dict]: Group of nested subgroup members, updated in place.
    Returns:
            tuple: (size, number of members) of the group.
    """

    size, members = 0, 0
    for name, child in group.items():
        if not isinstance( child, dict ) or name == DIAG_GROUP_TOTAL:
            continue
        if 'type' in child:
            childSize, childMembers = child.get( 'size', 0 ), 1
        else:
            childSize, childMembers = addMemberTotals( child )
        size += childSize
        members += childMembers
    # Put the totals first, so they lead the group in the written file
    others = { name: child for name, child in group.items() if name != DIAG_GROUP_TOTAL }
    group.clear()
    group[DIAG_GROUP_TOTAL] = { 'size': size, 'members': members }
    group.update( others )
    return size, members


def flattenDistReport( nestedDist ):
    """Flatten the members of each subgroup of a distribution nested by group.

    The inverse of nestDistReport: the ``groupMembers`` of each subgroup become the list of
    ``[member, size]`` in their original order. Subgroups whose members are already a list
    (written by older versions) are kept as they are.

    Args:
            nestedDist[dict]: Distribution with the members of each subgroup nested by group.
    Returns:
            dict: Distribution with the members of each subgroup as a list.
    """

    def leaves( node ):
        for name, child in node.items():
            if not isinstance( child, dict ) or name == DIAG_GROUP_TOTAL:
                continue
            if 'type' in child:
                yield child
            else:
                yield from leaves( child )

    flat = {}
    for freq, subGroups in nestedDist.items():
        flat[freq] = {}
        for subGroupID, subGroup in subGroups.items():
            members = subGroup.get( 'groupMembers' )
            if isinstance( members, dict ):
                ordered = sorted( leaves( members ), key=lambda leaf: leaf.get( 'index', 0 ) )
                members = [ [ leaf['path'], leaf['size'] ] for leaf in ordered ]
            flat[freq][subGroupID] = { **subGroup, 'groupMembers': members }
    return flat
