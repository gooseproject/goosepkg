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
        pass

    # Target registry goes here
    def register_retire(self):
        """Register the retire target"""

        retire_parser = self.subparsers.add_parser('retire',
                                              help='Retire a package',
                                              description='This command will \
                                              remove all files from the repo \
                                              and leave a dead.package file.')
        retire_parser.add_argument('-p', '--push',
                                   default=False,
                                   action='store_true',
                                   help='Push changes to remote repository')
        retire_parser.add_argument('msg',
                                   nargs='?',
                                   help='Message for retiring the package')
        retire_parser.set_defaults(command=self.retire)

    def register_tagrequest(self):
        """Register the tagrequest target"""

        tagrequest_parser = self.subparsers.add_parser('tag-request',
                                          help='Submit current build nvr '
                                          'as a releng tag request',
                                          description='This command \
                                          files a ticket with release \
                                          engineering, usually for a \
                                          buildroot override.  It will \
                                          discover the build n-v-r \
                                          automatically but can be \
                                          overridden.')
        tagrequest_parser.add_argument('--desc',
                                       help='Description of tag request')
        tagrequest_parser.add_argument('--build',
                                       help='Override the build n-v-r')
        tagrequest_parser.set_defaults(command=self.tagrequest)

    def register_update(self):
        update_parser = self.subparsers.add_parser('update',
                                          help='Submit last build as an '
                                          'update',
                                          description='This will create a \
                                          bodhi update request for the \
                                          current package n-v-r.')
        update_parser.set_defaults(command=self.update)

    # Target functions go here
    def retire(self):
        try:
            self.cmd.retire(self.args.msg)
        except Exception, e:
            self.log.error('Could not retire package: %s' % e)
            sys.exit(1)
        if self.args.push:
            self.push()

    def update(self):
        template = """\
[ %(nvr)s ]                                                                 

# bugfix, security, enhancement, newpackage (required)
type=

# testing, stable                                                           
request=testing

# Bug numbers: 1234,9876
bugs=%(bugs)s

# Description of your update                                                
notes=Here is where you give an explanation of your update.

# Enable request automation based on the stable/unstable karma thresholds
autokarma=True
stable_karma=3
unstable_karma=-3

# Automatically close bugs when this marked as stable
close_bugs=True

# Suggest that users restart after update
suggest_reboot=False
"""

        bodhi_args = {'nvr': self.cmd.nvr, 'bugs': ''}

        # Extract bug numbers from the latest changelog entry
        self.cmd.clog()
        clog = file('clog').read()
        bugs = re.findall(r'#([0-9]*)', clog)
        if bugs:
            bodhi_args['bugs'] = ','.join(bugs)

        template = textwrap.dedent(template) % bodhi_args

        # Calculate the hash of the unaltered template
        orig_hash = hashlib.new('sha1')
        orig_hash.update(template)
        orig_hash = orig_hash.hexdigest()

        # Write out the template
        out = file('bodhi.template', 'w')
        out.write(template)
        out.close()

        # Open the template in a text editor
        editor = os.getenv('EDITOR', 'vi')
        self.cmd._run_command([editor, 'bodhi.template'], shell=True)

        # Check to see if we got a template written out.  Bail otherwise
        if not os.path.isfile('bodhi.template'):
            self.log.error('No bodhi update details saved!')
            sys.exit(1)
        # If the template was changed, submit it to bodhi
        hash = self.cmd._hash_file('bodhi.template', 'sha1')
        if hash != orig_hash:
            try:
                self.cmd.update('bodhi.template')
            except Exception, e:
                self.log.error('Could not generate update request: %s' % e)
                sys.exit(1)
        else:
            self.log.info('Bodhi update aborted!')

        # Clean up
        os.unlink('bodhi.template')
        os.unlink('clog')

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
