/* Copyright 2026 oheco contributors. SPDX-License-Identifier: Apache-2.0 */
'use strict';

/**
 * Initialize only the identity and type consumed by NODERAWFS standard streams.
 * HarmonyOS statx can reject a live socket for which procfs still reports the
 * kernel socket inode. This is node metadata, never a replacement fs.Stats.
 */
module.exports = function standardStreamNode(fs, platform, fd, path, nodeOps) {
  try {
    const stat = fs.fstatSync(fd);
    return { id: stat.ino, mode: stat.mode, node_ops: nodeOps, path };
  } catch (error) {
    if (platform !== 'openharmony' || !Number.isInteger(fd) || fd < 0 || fd > 2 || error?.code !== 'EBADF') {
      throw error;
    }
    let target;
    try {
      target = fs.readlinkSync(`/proc/self/fd/${fd}`);
    } catch {
      throw error;
    }
    const socket = /^socket:\[(\d+)\]$/.exec(target);
    const inode = socket && Number(socket[1]);
    if (!socket || socket[0] !== target || !Number.isSafeInteger(inode) || inode <= 0) throw error;
    // S_IFSOCK is the observed type; no permission or timestamp is inferred.
    return { id: inode, mode: fs.constants.S_IFSOCK, node_ops: nodeOps, path };
  }
};
