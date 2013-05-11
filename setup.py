from setuptools import setup

setup(
    name = "goosepkg",
    version = "0.2",
    author = "Clint Savage",
    author_email = "herlo@gooseproject.org",
    description = ("GoOSe plugin to rpkg to manage "
                   "package sources in a git repository"),
    license = "GPLv2+",
    url = "https://github.com/gooseproject/goosepkg",
    package_dir = {'': 'src'},
    packages = ['pygoosepkg'],
    scripts = ['src/goosepkg'],
    data_files = [('/etc/goosepkg', ['src/goosepkg.conf']),]
)

# production directory
#    data_files = [('/etc/bash_completion.d', ['src/goosepkg.bash']),
#                  ('/etc/goosepkg', ['src/goosepkg.conf']),
#                 ]
