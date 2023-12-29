#!/usr/bin/env python

from __future__ import with_statement

import os
import sys
import errno

from fuse import FUSE, FuseOSError, Operations, fuse_get_context
from google.cloud import storage
import tempfile
import shutil
import sys
import signal

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'gcloud_key.json'

class Passthrough(Operations):
    def __init__(self, bucket_name):
        self.bucket_name = bucket_name
        self.root = ""
        self.storage_client = storage.Client()
        self.bucket = self.storage_client.bucket(bucket_name)

    # Helpers
    # =======

    def cloud_path(self, partial):
        return partial[1:]
        # if partial == "/":
        #     return ""
        # if '.' in partial:
        #     return partial[1:]
        # # if it is directory add '/' so during list blobs it list correctly
        # return partial[1:] + "/"
    
    def temp_path(self, partial):
        if partial.startswith("/"):
            partial = partial[1:]
        path = os.path.join(self.root, partial.split('/')[-1])
        return path

    # Filesystem methods
    # ==================

    def access(self, path, mode):
        print(">> access >> : ", path, mode)
        cloud_path = self.cloud_path(path)

        if(cloud_path == ""):
            return
        blob = self.bucket.blob(cloud_path)
        if(not blob.exists()):
            raise FuseOSError(errno.EACCES)

    def chmod(self, path, mode):
        print(">> chmod >> : ", path, mode)
        cloud_path = self.cloud_path(path)
        return os.chmod(cloud_path, mode)

    def chown(self, path, uid, gid):
        print(">> chown >> : ", path, uid, gid)
        cloud_path = self.cloud_path(path)
        return os.chown(cloud_path, uid, gid)

    def getattr(self, path, fh=None):
        print(">> getattr >> : ", path, fh)
        if self.root != "":
            st = os.lstat(self.temp_path(path))
            return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                                                        'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid', 'st_blocks'))
        
        cloud_path = self.cloud_path(path)
        if(cloud_path == ""):
            return {'st_atime' : 0, 'st_mode' : 16877}

        blob = self.bucket.blob(cloud_path)
        if(not blob.exists()):
            os.lstat(cloud_path)
        else:
            if '.' in cloud_path:
                blob = self.bucket.get_blob(cloud_path)
                return {'st_atime': blob.updated.timestamp(), 'st_ctime' : blob.updated.timestamp(), 'st_mtime': blob.updated.timestamp(), 
                'st_mode': 33188, 'st_size': blob.size}
            else:
                blob = self.bucket.get_blob(cloud_path)
                return {'st_atime': blob.updated.timestamp(), 'st_ctime' : blob.updated.timestamp(), 'st_mtime': blob.updated.timestamp(),
                 'st_mode': 16877, 'st_size': blob.size}

    def readdir(self, path, fh):
        print(">> readdir >> : ", path, fh)

        cloud_path = self.cloud_path(path)
        content = self.list_blobs_with_prefix(cloud_path)

        for value in content:
            yield value.split("/")[-1]

    def readlink(self, path):
        print(">> readlink >> : ", path)
        pathname = os.readlink(self.cloud_path(path))
        if pathname.startswith("/"):
            # Path name is absolute, sanitize it.
            return os.path.relpath(pathname, self.root)
        else:
            return pathname

    def mknod(self, path, mode, dev):
        print(">> mknod >> : ", path, mode, dev)
        return os.mknod(self.cloud_path(path), mode, dev)

    def rmdir(self, path):
        print(">> rmdir >> : ", path)
        cloud_path = self.cloud_path(path) + "/"
        blobs = self.storage_client.list_blobs(self.bucket_name, prefix=cloud_path)

        for blob in blobs:
            generation_match_precondition = blob.generation
            blob.delete(if_generation_match=generation_match_precondition)

        self.unlink(path)
        return

    def mkdir(self, path, mode):
        print(">> mkdir >> : ", path, mode)
        if('.' not in path):
            blob = self.bucket.blob(self.cloud_path(path))
            blob.upload_from_string("")
        return
        # return os.mkdir(self.cloud_path(path), mode)

    def statfs(self, path):
        print(">> statfs >> : ", path)
        cloud_path = self.cloud_path(path)
        stv = os.statvfs(cloud_path)
        return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
            'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag',
            'f_frsize', 'f_namemax'))

    def unlink(self, path):
        print(">> unlink >> : ", path)
        blob = self.bucket.blob(self.cloud_path(path))
        self.delete_blob(blob)
        return

    def symlink(self, name, target):
        print(">> symlink >> : ", name, target)
        return os.symlink(target, self.cloud_path(name))

    def rename(self, old, new):
        print(">> rename >> : ", old, new)

        blob = self.bucket.blob(self.cloud_path(old))
        blob_copy = self.bucket.copy_blob(blob, self.bucket, self.cloud_path(new), if_generation_match=0)
        self.delete_blob(blob)
        return
    
    def delete_blob(self, blob):
        blob.reload()
        generation_match_precondition = blob.generation
        blob.delete(if_generation_match=generation_match_precondition)

    def link(self, target, name):
        print(">> link >> : ", target, name)
        return os.link(self.cloud_path(name), self.cloud_path(target))

    def utimens(self, path, times=None):
        print(">> utimens >> : ", path, times)
        return
        # return os.utime(self.temp_path(path), times)

    # File methods
    # ============

    def open(self, path, flags):
        print(">> open >> : ", path, flags)
        self.root = tempfile.mkdtemp()
        temp_path = self.temp_path(path)

        blob = self.bucket.blob(self.cloud_path(path))
        blob.download_to_filename(temp_path)

        # return os.open(temp_path, flags)
        return os.open(temp_path, flags)

    def create(self, path, mode, fi=None):
        print(">> create >> : ", path, mode)
        uid, gid, pid = fuse_get_context()

        self.root = tempfile.mkdtemp()
        temp_path = self.temp_path(path)
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT, mode)
        os.chown(temp_path,uid,gid) #chown to context uid & gid
        return fd

    def read(self, path, length, offset, fh):
        print(">> read >> : ", path, length, offset, fh)
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, length)

    def write(self, path, buf, offset, fh):
        print(">> write >> : ", path, buf, offset, fh)
        os.lseek(fh, offset, os.SEEK_SET)
        return os.write(fh, buf)

    def truncate(self, path, length, fh=None):
        print(">> truncate >> : ", path, length)
        temp_path = self.temp_path(path)
        with open(temp_path, 'r+') as f:
            f.truncate(length)

    def flush(self, path, fh):
        print(">> flush >> : ", path, fh)
        return os.fsync(fh)

    def release(self, path, fh):
        print(">> release >> : ", path, fh)
        ans = os.close(fh)

        if('.' in path):
            blob = self.bucket.blob(self.cloud_path(path))
            generation_match_precondition = 0

            if(blob.exists()):
                generation_match_precondition = self.bucket.get_blob(self.cloud_path(path)).generation

            blob.upload_from_filename(self.temp_path(path), if_generation_match=generation_match_precondition)

        shutil.rmtree(self.root)
        self.root = ""
        return ans

    def fsync(self, path, fdatasync, fh):
        print(">> fsync >> : ", path, fdatasync, fh)
        return self.flush(path, fh)

    def list_blobs_with_prefix(self, prefix):
        content = []

        # if we specifies delimiter="/", in blobs it only stores file names and in blobs.prefixes it stores directory names
        if(prefix != ""):
            prefix += "/"
        blobs = self.storage_client.list_blobs(self.bucket_name, prefix=prefix, delimiter="/")
        for blob in blobs:
            content.append(blob.name)
        return content


def main(mountpoint, bucket_name):
    print("Started")
    def signal_handler(sig, frame):
        print('You pressed Ctrl+C!')
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    
    FUSE(Passthrough(bucket_name), mountpoint, nothreads=True, foreground=True, allow_other=False)


if __name__ == '__main__':
    main(sys.argv[2], sys.argv[1])


#  python3 hello.py /home/dhruv/ECC/Assignments/FileSystem/mount/ /home/dhruv/ECC/Assignments/FileSystem/temp/
#  python3 my_fs.py my-fs-ecc /home/dhruv/ECC/Assignments/FileSystem/temp/
