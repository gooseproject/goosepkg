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
import os
import cli
import git
import re
import pycurl
import platform

class Commands(pyrpkg.Commands):

    def __init__(self, path, lookaside, lookasidehash, lookaside_cgi,
                 gitbaseurl, anongiturl, branchre, kojiconfig,
                 build_client, user=None, dist=None, target=None,
                 quiet=False):
        """Init the object and some configuration details."""

        # We are subclassing to set kojiconfig to none, so that we can
        # make it a property to potentially use a secondary config
        super(Commands, self).__init__(path, lookaside, lookasidehash,
                                 lookaside_cgi, gitbaseurl, anongiturl,
                                 branchre, kojiconfig, build_client, user,
                                 dist, target, quiet)

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
            self._distval = self._findmasterbranch()
            self._distvar = 'goose'
            self.dist = 'gl%s' % self._distval
            self.mockconfig = 'goose-sketchy-%s' % self.localarch
            self.override = None
            self._distunset = 'rhel'
        # If we don't match one of the above, punt
        else:
            raise pyrpkg.rpkgError('Could not find the dist from branch name '
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
            self._target = 'rawhide'
        else:
            self._target = '%s-candidate' % self.branch_merge

    #FIXME: need to load GoOSe certificates here.
    def load_user(self):
        """This sets the user attribute, based on the GoOSe SSL cert."""
        try:
            #self._user = fedora_cert.read_user_cert()
            pass
        except Exception, e:
            self.log.debug('Could not read Fedora cert, falling back to '
                           'default method: ' % e)
            super(Commands, self).load_user()

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

        # Create a regex to find branches that exactly match f##.  Should not
        # catch branches such as gl6.0-updates
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
        if gooses:
            # Sort the list
            gooses.sort()
            # Start with the last item, strip the f, add 1, return it.
            return(int(gooses[-1].strip('f')) + 1)
        else:
            # We may not have GoOSes.  Find out what sketchy target does.
            try:
                rawhidetarget = self.anon_kojisession.getBuildTarget(
                                                              'sketchy')
            except:
                # We couldn't hit koji, bail.
                raise pyrpkg.rpkgError('Unable to query koji to find sketchy \
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
