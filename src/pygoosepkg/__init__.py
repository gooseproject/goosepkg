# goosepkg - a Python library for RPM Packagers
#
# Copyright (C) 2013 GoOSe Project
# Author(s):  Clint Savage <herlo@gooseproject.org>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

import pyrpkg
from pyrpkg import GitIgnore
import os
import re
import cli
import git
import stat
import pycurl
import hashlib
import platform


class goosepkgError(Exception):
    pass

class Commands(pyrpkg.Commands):

    def __init__(self, path, lookaside, lookasidehash, lookaside_host,
                lookaside_user, lookaside_remote_dir,
                gitbaseurl, anongiturl, branchre, kojiconfig,
                build_client, user=None, dist=None, target=None,
                quiet=False):
        """Init the object and some configuration details."""

        # We are subclassing to set kojiconfig to none, so that we can
        # make it a property to potentially use a secondary config
        super(Commands, self).__init__(path, lookaside, lookasidehash,
                                 '', gitbaseurl, anongiturl,
                                 branchre, kojiconfig, build_client, user,
                                 dist, target, quiet)

        # set the new values not in rpkg
        self.lookaside_host = lookaside_host
        self.lookaside_user = lookaside_user
        self.lookaside_remote_dir = lookaside_remote_dir

        # New data
        self.secondary_arch = {}

        # New properties
        self._kojiconfig = None
        self._cert_file = None
        self._ca_cert = None
        # Store this for later
        self._orig_kojiconfig = kojiconfig

    # Add new properties
    @property
    def kojiconfig(self):
        """This property ensures the kojiconfig attribute"""

        if not self._kojiconfig:
            self.load_kojiconfig()
        return self._kojiconfig

    @kojiconfig.setter
    def kojiconfig(self, value):
        self._kojiconfig = value

    def load_kojiconfig(self):
        """This loads the kojiconfig attribute

        This will either use the one passed in via arguments or a
        secondary arch config depending on the package
        """

        # We have to allow this to work, even if we don't have a package
        # we're working on, for things like gitbuildhash.
        try:
            null = self.module_name
        except:
            self._kojiconfig = self._orig_kojiconfig
            return
        for arch in self.secondary_arch.keys():
            if self.module_name in self.secondary_arch[arch]:
                self._kojiconfig = os.path.expanduser('~/.koji/%s-config' %
                                                      arch)
                return
        self._kojiconfig = self._orig_kojiconfig

    @property
    def cert_file(self):
        """This property ensures the cert_file attribute"""

        if not self._cert_file:
            self.load_cert_files()
        return self._cert_file

    @property
    def ca_cert(self):
        """This property ensures the ca_cert attribute"""

        if not self._ca_cert:
            self.load_cert_files()
        return self._ca_cert

    def load_cert_files(self):
        """This loads the cert_file attribute"""

        self._cert_file = os.path.expanduser('~/.koji/goose.cert')
        self._ca_cert = os.path.expanduser('~/.koji/goose-server-ca.cert')

    # Overloaded property loaders
    def load_rpmdefines(self):
        """Populate rpmdefines based on branch data"""

        # Determine runtime environment
        self._runtime_disttag = self._determine_runtime_env()

        # We only match the top level branch name exactly.
        # Anything else is too dangerous and --dist should be used
        if re.match(r'gl\d\.\d$', self.branch_merge):
            self._distval = self.branch_merge.split('gl')[1]
            self._distvar = 'goose'
            self.dist = 'gl%s' % self._distval
            self.mockconfig = 'goose-%s-%s' % (self._distval, self.localarch)
            self.override = 'gl%s-override' % self._distval
            self._distunset = 'rhel'
        # master
        elif re.match(r'master$', self.branch_merge):
        # If we don't match one of the above, punt
            raise pyrpkg.goosepkgError('GoOSe does not use the master branch'
                                   '\nPlease use \'goosepkg switch-branch\' or'
                                   '\nPlease specify with --dist')
        else:
            raise pyrpkg.goosepkgError('Could not find the dist from branch name '
                                   '%s\nPlease specify with --dist' %
                                   self.branch_merge)
        self._rpmdefines = ["--define '_sourcedir %s'" % self.path,
                            "--define '_specdir %s'" % self.path,
                            "--define '_builddir %s'" % self.path,
                            "--define '_srcrpmdir %s'" % self.path,
                            "--define '_rpmdir %s'" % self.path,
                            "--define 'dist .%s'" % self.dist,
                            "--define '%s %s'" % (self._distvar, self._distval),
                            "--define '%s %%{nil}'" % self._distunset,
                            "--define '%s 1'" % self.dist]
        if self._runtime_disttag:
            if self.dist != self._runtime_disttag:
                # This means that the runtime is known, and is different from
                # the target, so we need to unset the _runtime_disttag
                self._rpmdefines.append("--define '%s %%{nil}'" %
                                        self._runtime_disttag)

    def load_target(self):
        """This creates the target attribute based on branch merge"""

        if self.branch_merge == 'master':
            self._target = 'sketchy'
        else:
            self._target = '%s' % self.branch_merge

#    #FIXME: need to load GoOSe certificates here.
#    def load_user(self):
#        """This sets the user attribute, based on the GoOSe SSL cert."""
#        try:
#            #self._user = fedora_cert.read_user_cert()
#            pass
#        except Exception, e:
#            self.log.debug('Could not read Fedora cert, falling back to '
#                           'default method: ' % e)
#            super(Commands, self).load_user()

    # Other overloaded functions
    def import_srpm(self, *args):
        return super(Commands, self).import_srpm(*args)

    def pull(self, *args, **kwargs):
        super(Commands, self).pull(*args, **kwargs)

    def push(self):
        super(Commands, self).push()

    def build(self, *args, **kwargs):
        return(super(Commands, self).build(*args, **kwargs))

    def _findmasterbranch(self):
        """Find the right "GoOSe" for master"""

        # If we already have a koji session, just get data from the source
        if self._kojisession:
            sketchytarget = self.kojisession.getBuildTarget('sketchy')
            desttag = sketchytarget['dest_tag_name']
            return desttag.replace('gl', '')

        # Create a list of "gooses"
        gooses = []

        # Create a regex to find branches that exactly match gl#.#.
        branchre = 'gl\d\.\d$'

        # Find the repo refs
        for ref in self.repo.refs:
            # Only find the remote refs
            if type(ref) == git.RemoteReference:
                # Search for branch name by splitting off the remote
                # part of the ref name and returning the rest.  This may
                # fail if somebody names a remote with / in the name...
                if re.match(branchre, ref.name.split('/', 1)[1]):
                    # Add just the simple f## part to the list
                    gooses.append(ref.name.split('/')[1])

        print("gooses: {0}".format(gooses))

        if gooses:
            # Sort the list
            gooses.sort()
            # Start with the last item, strip the f, add 1, return it.
            return(int(gooses[-1].strip('gl')) + 1)
        else:
            # We may not have GoOSes.  Find out what sketchy target does.
            try:
                rawhidetarget = self.anon_kojisession.getBuildTarget(
                                                              'sketchy')
            except:
                # We couldn't hit koji, bail.
                raise pyrpkg.goosepkgError('Unable to query koji to find sketchy \
                                       target')
            desttag = rawhidetarget['dest_tag_name']
            return desttag.replace('f', '')

    def _determine_runtime_env(self):
        """Need to know what the runtime env is, so we can unset anything
           conflicting
        """

        try:
           mydist = platform.linux_distribution()
        except:
           # This is marked as eventually being deprecated.
           try:
              mydist = platform.dist()
           except:
              runtime_os = 'unknown'
              runtime_version = '0'

        if mydist:
           runtime_os = mydist[0]
           runtime_version = mydist[1]
        else:
           runtime_os = 'unknown'
           runtime_version = '0'

        if runtime_os in ['redhat', 'centos']:
            return 'el%s' % runtime_version
        if runtime_os == 'goose':
            return 'gl%s' % runtime_version

        # fall through, return None
        return None

    def retire(self, message=None):
        """Delete all tracked files and commit a new dead.package file

        Use optional message in commit.

        Runs the commands and returns nothing
        """

        cmd = ['git']
        if self.quiet:
            cmd.append('--quiet')
        cmd.extend(['rm', '-rf', '.'])
        self._run_command(cmd, cwd=self.path)

        if not message:
            message = 'Package is retired'

        fd = open(os.path.join(self.path, 'dead.package'), 'w')
        fd.write(message + '\n')
        fd.close()

        cmd = ['git', 'add', os.path.join(self.path, 'dead.package')]
        self._run_command(cmd, cwd=self.path)

        self.commit(message=message)

    def update(self, template='bodhi.template', bugs=[]):
        """Submit an update to bodhi using the provided template."""

        # build up the bodhi arguments
        cmd = ['bodhi', '--new', '--release', self.branch_merge,
               '--file', 'bodhi.template', self.nvr, '--username',
               self.user]
        self._run_command(cmd, shell=True)

    def new_sources(self):
        # Check to see if the files passed exist
        for file in self.args.files:
            if not os.path.isfile(file):
                raise Exception('Path does not exist or is '
                                'not a file: %s' % file)
        #self.cmd.upload(self.args.files, replace=self.args.replace)
        self.log.info("Source upload succeeded. Don't forget to commit the "
                      "sources file")

    #TODO: Update to sha256sum hash
    def _hash_file(self, file, hashtype):
        """Return the hash of a file given a hash type"""

        try:
            sum = hashlib.new(hashtype)
        except ValueError:
            raise goosepkgError('Invalid hash type: %s' % hashtype)

        input = open(file, 'rb')
        # Loop through the file reading chunks at a time as to not
        # put the entire file in memory.  That would suck for DVDs
        while True:
            chunk = input.read(8192) # magic number!  Taking suggestions
            if not chunk:
                break # we're done with the file
            sum.update(chunk)
        input.close()
        return sum.hexdigest()

    def _do_rsync(self, file_hash, file):
        """Use curl manually to upload a file"""

        cmd = ["/usr/bin/rsync", "--progress", "-loDtRz", "-e", "ssh", file,
              "{0}@{1}:{2}/{3}/{4}/".format(self.lookaside_user,
              self.lookaside_host, self.lookaside_remote_dir,
              self.module_name, file_hash)]

#        cmd = ['curl', '--fail', '-o', '/dev/null', '--show-error',
#        '--progress-bar', '-F', 'name=%s' % self.module_name, '-F',
#        'md5sum=%s' % file_hash, '-F', 'file=@%s' % file]
#        if self.quiet:
#            cmd.append('-s')
#        cmd.append(self.lookaside_cgi)
        self._run_command(cmd)

    #TODO: write a test using ssh to verify the file exists or not
    def file_exists(self, pkg_name, filename, md5sum):
        """
        Return True if the given file exists in the lookaside cache, False
        if not.

        A goosepkgError will be thrown if the request looks bad or something
        goes wrong. (i.e. the lookaside URL cannot be reached, or the package
        named does not exist)
        """

#        # String buffer, used to receive output from the curl request:
#        buf = StringIO.StringIO()
#
#        # Setup the POST data for lookaside CGI request. The use of
#        # 'filename' here appears to be what differentiates this
#        # request from an actual file upload.
#        post_data = [
#                ('name', pkg_name),
#                ('md5sum', md5sum),
#                ('filename', filename)]
#
#        curl = self._create_curl()
#        curl.setopt(pycurl.WRITEFUNCTION, buf.write)
#        curl.setopt(pycurl.HTTPPOST, post_data)
#
#        try:
#            curl.perform()
#        except Exception, e:
#            raise goosepkgError('Lookaside failure: %s' % e)
#        curl.close()
#        output = buf.getvalue().strip()
#
#        # Lookaside CGI script returns these strings depending on whether
#        # or not the file exists:
#        if output == "Available":
#            return True
#        if output == "Missing":

        return False

        # Something unexpected happened, will trigger if the lookaside URL
        # cannot be reached, the package named does not exist, and probably
        # some other scenarios as well.
        raise goosepkgError("Error checking for %s at: %s" %
                (filename, self.lookaside_cgi))


    def upload(self, files, replace=False):
        """Upload source file(s) in the lookaside cache

        Can optionally replace the existing tracked sources
        """

        oldpath = os.getcwd()
        os.chdir(self.path)

        # Decide to overwrite or append to sources:
        if replace:
            sources = []
            sources_file = open('sources', 'w')
        else:
            sources = open('sources', 'r').readlines()
            sources_file = open('sources', 'a')

        # Will add new sources to .gitignore if they are not already there.
        gitignore = GitIgnore(os.path.join(self.path, '.gitignore'))

        uploaded = []
        for f in files:
            # TODO: Skip empty file needed?
            file_hash = self._hash_file(f, self.lookasidehash)
            self.log.info("Uploading: %s  %s" % (file_hash, f))
            file_basename = os.path.basename(f)
            if not "%s  %s\n" % (file_hash, file_basename) in sources:
                sources_file.write("%s  %s\n" % (file_hash, file_basename))

            # Add this file to .gitignore if it's not already there:
            if not gitignore.match(file_basename):
                gitignore.add('/%s' % file_basename)

            if self.file_exists(self.module_name, file_basename, file_hash):
                # Already uploaded, skip it:
                self.log.info("File already uploaded: %s" % file_basename)
            else:
                # Ensure the new file is readable:
                os.chmod(f, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                #lookaside.upload_file(self.module, f, file_hash)
                # For now don't use the pycurl upload function as it does
                # not produce any progress output.  Cheat and use curl
                # directly.
                self._do_rsync(file_hash, f)
                uploaded.append(file_basename)

        sources_file.close()

        # Write .gitignore with the new sources if anything changed:
        gitignore.write()

        rv = self.repo.index.add(['sources', '.gitignore'])

        # Change back to original working dir:
        os.chdir(oldpath)

        # Log some info
        self.log.info('Uploaded and added to .gitignore: %s' %
                      ' '.join(uploaded))
