# cli.py - a cli client class module for goosepkg
#
# Copyright (C) 2013 GoOSe Project
# Author(s): Clint Savage <herlo@gooseproject.org>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

from pyrpkg.cli import cliClient
import sys
import os
import logging
import getpass
import re
import textwrap
import hashlib


class goosepkgClient(cliClient):
    def __init__(self, config, name='goosepkg'):
        super(goosepkgClient, self).__init__(config, name)
        self.setup_goose_subparsers()

    def setup_goose_subparsers(self):
        """Register the goose specific targets"""
        # these functions are getting disabled since goosepkg
        # doesn't use them, even though rpkg apparently does.

        self.register_mock_config()
        self.register_new()
        self.register_tag()

        # register updated/new functions
        self.register_clone()
        self.register_upload()

    # Disable some registered commands from rpkg
    def register_mock_config(self):
        """Disable Mock Config creation"""
        pass

    def register_new(self):
        """Disable tracking since last tag"""
        pass

    def register_tag(self):
        """Disable tagging with goosepkg"""
        pass

    # Target registry goes here
    def register_clone(self):
        """Register the clone target and co alias"""

        clone_parser = self.subparsers.add_parser('clone',
                                         help = 'Clone and checkout a module',
                                         description = 'This command will \
                                         clone the named module from the \
                                         configured repository base URL.  \
                                         By default it will also checkout \
                                         the master branch for your working \
                                         copy.')
        # provide a convenient way to get to a specific branch
        clone_parser.add_argument('--branch', '-b',
                                  help = 'Check out a specific branch')
        # allow to clone without needing a account on the scm server
        clone_parser.add_argument('--anonymous', '-a',
                                  action = 'store_true',
                                  help = 'Check out a module anonymously')
        # store the module to be cloned
        clone_parser.add_argument('module', nargs = 1,
                                  help = 'Name of the module to clone')
        clone_parser.set_defaults(command = self.clone)

        # Add an alias for historical reasons
        co_parser = self.subparsers.add_parser('co', parents = [clone_parser],
                                          conflict_handler = 'resolve',
                                          help = 'Alias for clone',
                                          description = 'This command will \
                                          clone the named module from the \
                                          configured repository base URL.  \
                                          By default it will also checkout \
                                          the master branch for your working \
                                          copy.')
        co_parser.set_defaults(command = self.clone)

    # Target functions go here
    def clone(self):
        self.cmd.clone(self.args.module[0], branch=self.args.branch,
                       anon=self.args.anonymous)

if __name__ == '__main__':
    client = cliClient()
    client._do_imports()
    client.parse_cmdline()

    if not client.args.path:
        try:
            client.args.path = os.getcwd()
        except:
            print('Could not get current path, have you deleted it?')
            sys.exit(1)

    # setup the logger -- This logger will take things of INFO or DEBUG and
    # log it to stdout.  Anything above that (WARN, ERROR, CRITICAL) will go
    # to stderr.  Normal operation will show anything INFO and above.
    # Quiet hides INFO, while Verbose exposes DEBUG.  In all cases WARN or
    # higher are exposed (via stderr).
    log = client.site.log
    client.setupLogging(log)

    if client.args.v:
        log.setLevel(logging.DEBUG)
    elif client.args.q:
        log.setLevel(logging.WARNING)
    else:
        log.setLevel(logging.INFO)

    # Run the necessary command
    try:
        client.args.command()
    except KeyboardInterrupt:
        pass
